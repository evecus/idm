"""
Local Flask API server - receives download tasks from browser extension.
Runs on localhost:16800
"""
import threading
import uuid
import os
import re
from urllib.parse import urlparse, unquote
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allow browser extension to call

_engine = None
_config = None
_gui_callback = None  # Called when new task added, to refresh GUI


def init_server(engine, config, gui_callback=None):
    global _engine, _config, _gui_callback
    _engine = engine
    _config = config
    _gui_callback = gui_callback


def _should_capture(url: str, filename: str, size: int, site: str) -> tuple[bool, str]:
    """
    Returns (should_capture, reason).
    Applies user filter rules: file type, min size, site blacklist.
    """
    cfg = _config

    # Site blacklist
    blacklist = cfg.get("site_blacklist", [])
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    for blocked in blacklist:
        blocked = blocked.strip().lower()
        if blocked and (host == blocked or host.endswith("." + blocked)):
            return False, f"Site blocked: {host}"

    # File extension filter
    ext = ""
    if filename:
        ext = os.path.splitext(filename)[-1].lower().lstrip(".")
    if not ext:
        # Try to extract from URL path
        path = parsed.path
        ext = os.path.splitext(path)[-1].lower().lstrip(".")

    captured_types = cfg.get("captured_types", [
        "zip", "rar", "7z", "tar", "gz", "bz2",
        "exe", "msi", "dmg", "pkg", "deb", "rpm",
        "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm",
        "mp3", "flac", "wav", "aac", "ogg",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
        "iso", "img", "bin",
    ])
    if ext and captured_types and ext not in [t.lower() for t in captured_types]:
        return False, f"File type not captured: .{ext}"

    # Minimum size filter
    min_size_mb = cfg.get("min_size_mb", 0)
    if min_size_mb > 0 and size > 0:
        if size < min_size_mb * 1024 * 1024:
            return False, f"File too small: {size} bytes < {min_size_mb}MB"

    return True, ""


def _filename_from_url(url: str, content_disposition: str = "") -> str:
    """Extract filename from URL or Content-Disposition header."""
    if content_disposition:
        match = re.findall(r'filename\*?=["\']?(?:UTF-\d[\'"]*)?([^;\r\n"\']*)', content_disposition)
        if match:
            return unquote(match[0].strip())
    path = urlparse(url).path
    name = path.split("/")[-1]
    name = unquote(name)
    return name if name else "download"


@app.route("/ping", methods=["GET"])
def ping():
    """Health check - extension uses this to verify downloader is running."""
    return jsonify({"status": "ok", "version": "1.0.0"})


@app.route("/add", methods=["POST"])
def add_download():
    """Add a new download task from browser extension."""
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL required"}), 400

    filename = data.get("filename", "") or _filename_from_url(url, data.get("content_disposition", ""))
    size = data.get("size", 0)
    referrer = data.get("referrer", "")
    cookies = data.get("cookies", "")
    site = data.get("site", urlparse(url).netloc)

    should, reason = _should_capture(url, filename, size, site)
    if not should:
        return jsonify({"captured": False, "reason": reason}), 200

    from engine import DownloadTask
    task = DownloadTask(
        url=url,
        save_path=_config.get("save_path", os.path.expanduser("~/Downloads")),
        filename=filename,
        task_id=str(uuid.uuid4()),
        threads=_config.get("default_threads", 8),
        referrer=referrer,
        cookies=cookies,
    )

    _engine.add_task(task)

    if _gui_callback:
        _gui_callback(task)

    return jsonify({"captured": True, "task_id": task.task_id, "filename": filename})


@app.route("/add_video", methods=["POST"])
def add_video():
    """Add a video URL for yt-dlp extraction."""
    data = request.json or {}
    page_url = data.get("url", "").strip()
    if not page_url:
        return jsonify({"error": "URL required"}), 400

    # Send to GUI for yt-dlp handling
    if _gui_callback:
        _gui_callback(None, video_url=page_url)

    return jsonify({"captured": True, "message": "Video URL sent to downloader"})


@app.route("/status", methods=["GET"])
def status():
    """Return current download stats."""
    if not _engine:
        return jsonify({"error": "Engine not ready"}), 503
    stats = _engine.get_stats()
    tasks = []
    for t in list(_engine.tasks.values())[-20:]:  # last 20
        tasks.append({
            "id": t.task_id,
            "filename": t.filename,
            "status": t.status.value,
            "progress": round(t.progress, 1),
            "speed": t.speed,
            "eta": t.eta,
        })
    return jsonify({"stats": stats, "tasks": tasks})


@app.route("/config", methods=["GET"])
def get_config():
    """Return current filter config to extension."""
    return jsonify({
        "captured_types": _config.get("captured_types", []),
        "min_size_mb": _config.get("min_size_mb", 0),
        "site_blacklist": _config.get("site_blacklist", []),
    })


def run_server(host="127.0.0.1", port=16800):
    """Run Flask server in background thread."""
    t = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False, use_reloader=False),
        daemon=True
    )
    t.start()
    return t
