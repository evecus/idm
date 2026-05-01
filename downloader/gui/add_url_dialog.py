"""
Add URL dialog - manual URL entry, yt-dlp video sniffing.
"""
import os
import threading
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSpinBox, QCheckBox, QProgressBar,
    QListWidget, QListWidgetItem, QGroupBox, QFileDialog,
    QTextEdit, QSplitter, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QFont
import config_manager


class SniffWorker(QThread):
    """Worker thread for yt-dlp video URL extraction."""
    formats_ready = pyqtSignal(list)   # list of format dicts
    error = pyqtSignal(str)

    def __init__(self, url: str, proxy: str = ""):
        super().__init__()
        self.url = url
        self.proxy = proxy

    def run(self):
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "listformats": False,
            }
            if self.proxy:
                ydl_opts["proxy"] = self.proxy

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)

            formats = []
            for f in info.get("formats", []):
                ext = f.get("ext", "")
                vcodec = f.get("vcodec", "none")
                acodec = f.get("acodec", "none")
                height = f.get("height")
                filesize = f.get("filesize") or f.get("filesize_approx", 0)
                note = f.get("format_note", "")

                if vcodec == "none" and acodec == "none":
                    continue

                label_parts = []
                if height:
                    label_parts.append(f"{height}p")
                if note:
                    label_parts.append(note)
                label_parts.append(ext.upper())
                if vcodec == "none":
                    label_parts.append("仅音频")
                elif acodec == "none":
                    label_parts.append("仅视频")
                if filesize:
                    label_parts.append(f"~{filesize // 1024 // 1024}MB")

                formats.append({
                    "format_id": f.get("format_id"),
                    "label": " · ".join(label_parts),
                    "url": f.get("url", ""),
                    "ext": ext,
                    "filesize": filesize,
                    "title": info.get("title", "video"),
                })

            # Best first
            formats = sorted(formats, key=lambda x: x.get("filesize", 0), reverse=True)
            self.formats_ready.emit(formats)

        except Exception as e:
            self.error.emit(str(e))


class AddUrlDialog(QDialog):
    task_added = pyqtSignal(dict)  # emit task info dict

    def __init__(self, url: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建下载任务")
        self.setMinimumSize(580, 380)
        self.cfg = config_manager.get()
        self._sniff_worker = None
        self._formats = []
        self._build_ui()
        if url:
            self.url_edit.setText(url)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # URL input
        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("下载链接:"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("粘贴直链或视频页面 URL...")
        url_row.addWidget(self.url_edit)
        self.btn_sniff = QPushButton("🔍 嗅探视频")
        self.btn_sniff.clicked.connect(self._sniff)
        url_row.addWidget(self.btn_sniff)
        layout.addLayout(url_row)

        # Video formats (hidden by default)
        self.format_grp = QGroupBox("检测到的视频格式（选择一个）")
        fmt_layout = QVBoxLayout(self.format_grp)
        self.format_list = QListWidget()
        self.format_list.setMaximumHeight(130)
        fmt_layout.addWidget(self.format_list)
        self.sniff_status = QLabel("")
        self.sniff_status.setStyleSheet("color: gray; font-size: 11px;")
        fmt_layout.addWidget(self.sniff_status)
        self.format_grp.setVisible(False)
        layout.addWidget(self.format_grp)

        # Save path
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("保存到:"))
        self.path_edit = QLineEdit(self.cfg.get("save_path", os.path.expanduser("~/Downloads")))
        path_row.addWidget(self.path_edit)
        btn_browse = QPushButton("...")
        btn_browse.setFixedWidth(32)
        btn_browse.clicked.connect(self._browse)
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        # Filename
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("文件名:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("留空自动从 URL 提取")
        name_row.addWidget(self.name_edit)
        layout.addLayout(name_row)

        # Options row
        opt_row = QHBoxLayout()
        opt_row.addWidget(QLabel("线程数:"))
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 32)
        self.threads_spin.setValue(self.cfg.get("default_threads", 8))
        opt_row.addWidget(self.threads_spin)
        opt_row.addSpacing(20)
        opt_row.addWidget(QLabel("Referrer:"))
        self.referrer_edit = QLineEdit()
        self.referrer_edit.setPlaceholderText("可选")
        opt_row.addWidget(self.referrer_edit)
        layout.addLayout(opt_row)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        self.btn_start = QPushButton("开始下载")
        self.btn_start.setDefault(True)
        self.btn_start.clicked.connect(self._start)
        btn_row.addWidget(self.btn_start)
        layout.addLayout(btn_row)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择保存目录", self.path_edit.text())
        if path:
            self.path_edit.setText(path)

    def _sniff(self):
        url = self.url_edit.text().strip()
        if not url:
            return

        self.btn_sniff.setEnabled(False)
        self.btn_sniff.setText("嗅探中...")
        self.format_grp.setVisible(True)
        self.format_list.clear()
        self.sniff_status.setText("正在分析页面，请稍候...")

        proxy = ""
        mode = self.cfg.get("proxy_mode", "system")
        if mode == "custom":
            proxy = self.cfg.get("custom_proxy", "")

        self._sniff_worker = SniffWorker(url, proxy)
        self._sniff_worker.formats_ready.connect(self._on_formats)
        self._sniff_worker.error.connect(self._on_sniff_error)
        self._sniff_worker.start()

    @pyqtSlot(list)
    def _on_formats(self, formats: list):
        self._formats = formats
        self.format_list.clear()
        for f in formats:
            item = QListWidgetItem(f["label"])
            item.setData(Qt.ItemDataRole.UserRole, f)
            self.format_list.addItem(item)
        if formats:
            self.format_list.setCurrentRow(0)
            self.sniff_status.setText(f"找到 {len(formats)} 个格式，选择后点击「开始下载」")
        else:
            self.sniff_status.setText("未找到可下载的视频格式")
        self.btn_sniff.setEnabled(True)
        self.btn_sniff.setText("🔍 嗅探视频")

    @pyqtSlot(str)
    def _on_sniff_error(self, msg: str):
        self.sniff_status.setText(f"嗅探失败: {msg}")
        self.btn_sniff.setEnabled(True)
        self.btn_sniff.setText("🔍 嗅探视频")

    def _start(self):
        # If format selected, use its URL
        if self._formats and self.format_list.currentItem():
            fmt = self.format_list.currentItem().data(Qt.ItemDataRole.UserRole)
            url = fmt["url"]
            filename = self.name_edit.text().strip() or f"{fmt['title']}.{fmt['ext']}"
        else:
            url = self.url_edit.text().strip()
            filename = self.name_edit.text().strip()

        if not url:
            return

        self.task_added.emit({
            "url": url,
            "save_path": self.path_edit.text().strip(),
            "filename": filename,
            "threads": self.threads_spin.value(),
            "referrer": self.referrer_edit.text().strip(),
        })
        self.accept()
