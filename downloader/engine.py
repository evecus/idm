"""
Multi-thread chunked download engine with resume support.
"""
import os
import threading
import time
import requests
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
from urllib.parse import urlparse, unquote


class TaskStatus(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    MERGING = "merging"


@dataclass
class ChunkInfo:
    index: int
    start: int
    end: int
    downloaded: int = 0
    done: bool = False


@dataclass
class DownloadTask:
    url: str
    save_path: str
    filename: str
    task_id: str
    threads: int = 8
    status: TaskStatus = TaskStatus.QUEUED
    total_size: int = 0
    downloaded: int = 0
    speed: float = 0.0
    eta: int = 0
    error_msg: str = ""
    referrer: str = ""
    cookies: str = ""
    chunks: list = field(default_factory=list)
    # callbacks
    on_progress: Optional[Callable] = field(default=None, repr=False)
    on_complete: Optional[Callable] = field(default=None, repr=False)
    on_error: Optional[Callable] = field(default=None, repr=False)

    _stop_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _pause_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        self._pause_event.set()  # not paused by default

    @property
    def progress(self) -> float:
        if self.total_size <= 0:
            return 0.0
        return min(100.0, self.downloaded / self.total_size * 100)

    @property
    def full_path(self) -> str:
        return os.path.join(self.save_path, self.filename)

    def pause(self):
        self._pause_event.clear()
        self.status = TaskStatus.PAUSED

    def resume(self):
        self._pause_event.set()
        self.status = TaskStatus.DOWNLOADING

    def stop(self):
        self._stop_event.set()
        self._pause_event.set()


class DownloadEngine:
    def __init__(self, config: dict):
        self.config = config
        self.tasks: dict[str, DownloadTask] = {}
        self._queue: list[str] = []
        self._active: set[str] = set()
        self._lock = threading.Lock()
        self._scheduler = threading.Thread(target=self._schedule_loop, daemon=True)
        self._scheduler.start()

    def _get_proxy(self) -> dict:
        if not self.config.get("use_system_proxy", True):
            return {}
        proxies = urllib.request.getproxies()
        result = {}
        if "http" in proxies:
            result["http"] = proxies["http"]
        if "https" in proxies:
            result["https"] = proxies["https"]
        return result

    def _get_session(self, task: DownloadTask) -> requests.Session:
        s = requests.Session()
        s.proxies = self._get_proxy()
        if task.referrer:
            s.headers["Referer"] = task.referrer
        if task.cookies:
            for kv in task.cookies.split(";"):
                kv = kv.strip()
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    s.cookies.set(k.strip(), v.strip())
        s.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        return s

    def add_task(self, task: DownloadTask):
        with self._lock:
            self.tasks[task.task_id] = task
            self._queue.append(task.task_id)

    def _schedule_loop(self):
        while True:
            time.sleep(0.5)
            with self._lock:
                max_concurrent = self.config.get("max_concurrent", 3)
                while self._queue and len(self._active) < max_concurrent:
                    tid = self._queue.pop(0)
                    task = self.tasks.get(tid)
                    if task and task.status == TaskStatus.QUEUED:
                        self._active.add(tid)
                        t = threading.Thread(target=self._run_task, args=(task,), daemon=True)
                        t.start()

    def _run_task(self, task: DownloadTask):
        try:
            task.status = TaskStatus.DOWNLOADING
            session = self._get_session(task)

            # HEAD request to get file info
            try:
                resp = session.head(task.url, timeout=15, allow_redirects=True)
                task.total_size = int(resp.headers.get("Content-Length", 0))
                accept_ranges = resp.headers.get("Accept-Ranges", "none")
                supports_range = accept_ranges.lower() != "none" and task.total_size > 0
            except Exception:
                supports_range = False
                task.total_size = 0

            os.makedirs(task.save_path, exist_ok=True)
            tmp_dir = os.path.join(task.save_path, f".{task.task_id}_parts")

            if supports_range and task.threads > 1:
                self._multi_thread_download(task, session, tmp_dir)
            else:
                self._single_thread_download(task, session)

        except Exception as e:
            task.status = TaskStatus.ERROR
            task.error_msg = str(e)
            if task.on_error:
                task.on_error(task, str(e))
        finally:
            with self._lock:
                self._active.discard(task.task_id)

    def _multi_thread_download(self, task: DownloadTask, session: requests.Session, tmp_dir: str):
        os.makedirs(tmp_dir, exist_ok=True)
        chunk_size = task.total_size // task.threads
        chunks = []
        for i in range(task.threads):
            start = i * chunk_size
            end = task.total_size - 1 if i == task.threads - 1 else (i + 1) * chunk_size - 1
            chunk = ChunkInfo(index=i, start=start, end=end)
            # resume: check existing part file
            part_path = os.path.join(tmp_dir, f"part_{i}")
            if os.path.exists(part_path):
                chunk.downloaded = os.path.getsize(part_path)
                if chunk.downloaded >= (end - start + 1):
                    chunk.done = True
            chunks.append(chunk)
        task.chunks = chunks

        threads = []
        for chunk in chunks:
            if not chunk.done:
                t = threading.Thread(
                    target=self._download_chunk,
                    args=(task, session, chunk, tmp_dir),
                    daemon=True
                )
                threads.append(t)

        speed_tracker = threading.Thread(target=self._track_speed, args=(task,), daemon=True)
        speed_tracker.start()

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if task._stop_event.is_set():
            task.status = TaskStatus.PAUSED
            return

        # Merge
        task.status = TaskStatus.MERGING
        final_path = task.full_path
        counter = 1
        base, ext = os.path.splitext(final_path)
        while os.path.exists(final_path):
            final_path = f"{base} ({counter}){ext}"
            counter += 1

        with open(final_path, "wb") as outf:
            for i in range(task.threads):
                part_path = os.path.join(tmp_dir, f"part_{i}")
                with open(part_path, "rb") as pf:
                    while True:
                        buf = pf.read(1024 * 1024)
                        if not buf:
                            break
                        outf.write(buf)
                os.remove(part_path)

        try:
            os.rmdir(tmp_dir)
        except Exception:
            pass

        task.filename = os.path.basename(final_path)
        task.status = TaskStatus.COMPLETED
        task.speed = 0
        task.eta = 0
        if task.on_complete:
            task.on_complete(task)

    def _download_chunk(self, task: DownloadTask, session: requests.Session, chunk: ChunkInfo, tmp_dir: str):
        part_path = os.path.join(tmp_dir, f"part_{chunk.index}")
        start = chunk.start + chunk.downloaded
        end = chunk.end
        retries = 0
        max_retries = 5

        while retries < max_retries:
            if task._stop_event.is_set():
                return
            task._pause_event.wait()
            try:
                headers = {"Range": f"bytes={start}-{end}"}
                resp = session.get(task.url, headers=headers, stream=True, timeout=30)
                with open(part_path, "ab") as f:
                    for data in resp.iter_content(chunk_size=65536):
                        if task._stop_event.is_set():
                            return
                        task._pause_event.wait()
                        if data:
                            f.write(data)
                            length = len(data)
                            chunk.downloaded += length
                            start += length
                            with task._lock:
                                task.downloaded += length
                chunk.done = True
                return
            except Exception as e:
                retries += 1
                time.sleep(2 ** retries)

        task._stop_event.set()
        task.status = TaskStatus.ERROR
        task.error_msg = f"Chunk {chunk.index} failed after {max_retries} retries"

    def _single_thread_download(self, task: DownloadTask, session: requests.Session):
        final_path = task.full_path
        counter = 1
        base, ext = os.path.splitext(final_path)
        while os.path.exists(final_path):
            final_path = f"{base} ({counter}){ext}"
            counter += 1

        speed_tracker = threading.Thread(target=self._track_speed, args=(task,), daemon=True)
        speed_tracker.start()

        with session.get(task.url, stream=True, timeout=30) as resp:
            task.total_size = int(resp.headers.get("Content-Length", 0))
            with open(final_path, "wb") as f:
                for data in resp.iter_content(chunk_size=65536):
                    if task._stop_event.is_set():
                        task.status = TaskStatus.PAUSED
                        return
                    task._pause_event.wait()
                    if data:
                        f.write(data)
                        with task._lock:
                            task.downloaded += len(data)
                        if task.on_progress:
                            task.on_progress(task)

        task.status = TaskStatus.COMPLETED
        task.speed = 0
        if task.on_complete:
            task.on_complete(task)

    def _track_speed(self, task: DownloadTask):
        prev = task.downloaded
        while task.status == TaskStatus.DOWNLOADING:
            time.sleep(1)
            current = task.downloaded
            task.speed = current - prev
            prev = current
            if task.speed > 0 and task.total_size > 0:
                remaining = task.total_size - task.downloaded
                task.eta = int(remaining / task.speed)
            if task.on_progress:
                task.on_progress(task)

    def pause_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if task:
            task.pause()

    def resume_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if task:
            if task.status == TaskStatus.PAUSED:
                task.resume()
                with self._lock:
                    self._queue.append(task_id)
                    task.status = TaskStatus.QUEUED

    def cancel_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if task:
            task.stop()
            task.status = TaskStatus.ERROR

    def get_stats(self) -> dict:
        tasks = list(self.tasks.values())
        return {
            "total": len(tasks),
            "active": len(self._active),
            "queued": len(self._queue),
            "completed": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            "error": sum(1 for t in tasks if t.status == TaskStatus.ERROR),
        }
