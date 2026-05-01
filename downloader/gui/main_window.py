"""
Main window - functional download manager UI with task list, toolbar, status bar.
"""
import os
import sys
import subprocess
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QLabel, QPushButton, QStatusBar, QMenu, QSystemTrayIcon,
    QApplication, QAbstractItemView, QFrame, QSplitter,
    QMessageBox, QStyle
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot, QSize
from PyQt6.QtGui import QAction, QIcon, QFont, QColor, QBrush, QPalette

import config_manager
from engine import DownloadTask, TaskStatus
from gui.settings_dialog import SettingsDialog
from gui.add_url_dialog import AddUrlDialog


COLORS = {
    TaskStatus.QUEUED:      "#6c757d",
    TaskStatus.DOWNLOADING: "#0d6efd",
    TaskStatus.PAUSED:      "#fd7e14",
    TaskStatus.COMPLETED:   "#198754",
    TaskStatus.ERROR:       "#dc3545",
    TaskStatus.MERGING:     "#6f42c1",
}

STATUS_TEXT = {
    TaskStatus.QUEUED:      "排队中",
    TaskStatus.DOWNLOADING: "下载中",
    TaskStatus.PAUSED:      "已暂停",
    TaskStatus.COMPLETED:   "已完成",
    TaskStatus.ERROR:       "出错",
    TaskStatus.MERGING:     "合并中",
}

COL_FILENAME = 0
COL_SIZE     = 1
COL_PROGRESS = 2
COL_SPEED    = 3
COL_ETA      = 4
COL_STATUS   = 5
COL_THREADS  = 6


def fmt_size(b: int) -> str:
    if b <= 0:
        return "—"
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def fmt_speed(bps: float) -> str:
    return fmt_size(int(bps)) + "/s" if bps > 0 else "—"


def fmt_eta(sec: int) -> str:
    if sec <= 0:
        return "—"
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m {sec % 60}s"
    return f"{sec // 3600}h {(sec % 3600) // 60}m"


class ProgressDelegate:
    """Inline progress bar in table cell."""
    pass


class MainWindow(QMainWindow):
    def __init__(self, engine, app_instance):
        super().__init__()
        self.engine = engine
        self.app = app_instance
        self.cfg = config_manager.get()
        self._task_rows: dict[str, int] = {}  # task_id -> row index

        self.setWindowTitle("IDM Clone — 多线程下载器")
        self.setMinimumSize(900, 560)
        self.resize(1100, 650)

        self._build_ui()
        self._setup_tray()
        self._setup_refresh_timer()

    # ── UI Build ───────────────────────────────────────────────────
    def _build_ui(self):
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._apply_style()

    def _build_toolbar(self):
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        def act(label, slot, shortcut=None, tip=""):
            a = QAction(label, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(shortcut)
            if tip:
                a.setToolTip(tip)
            tb.addAction(a)
            return a

        act("➕ 新建下载", self._new_download, "Ctrl+N", "添加新下载任务")
        tb.addSeparator()
        act("▶ 开始", self._resume_selected, tip="继续选中任务")
        act("⏸ 暂停", self._pause_selected, tip="暂停选中任务")
        act("✖ 取消", self._cancel_selected, tip="取消并删除选中任务")
        tb.addSeparator()
        act("📁 打开文件夹", self._open_folder, tip="打开选中任务的保存目录")
        tb.addSeparator()
        act("⚙ 设置", self._open_settings, "Ctrl+,")

    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Filter tabs
        filter_row = QHBoxLayout()
        self._filter_btns = {}
        for label in ["全部", "下载中", "已完成", "已暂停", "出错"]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda checked, l=label: self._set_filter(l))
            filter_row.addWidget(btn)
            self._filter_btns[label] = btn
        self._filter_btns["全部"].setChecked(True)
        filter_row.addStretch()
        layout.addLayout(filter_row)
        self._current_filter = "全部"

        # Table
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["文件名", "大小", "进度", "速度", "剩余时间", "状态", "线程"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(COL_PROGRESS, 160)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._open_file)
        layout.addWidget(self.table)

    def _build_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.lbl_status = QLabel("就绪")
        self.lbl_server = QLabel("🟢 插件服务: 16800")
        self.lbl_server.setStyleSheet("color: #198754;")
        self.status_bar.addWidget(self.lbl_status)
        self.status_bar.addPermanentWidget(self.lbl_server)

    def _apply_style(self):
        self.setStyleSheet("""
        QMainWindow { background: #f8f9fa; }
        QToolBar { background: #ffffff; border-bottom: 1px solid #dee2e6; padding: 2px 4px; spacing: 4px; }
        QToolBar QToolButton {
            padding: 4px 10px; border-radius: 4px; font-size: 13px;
            border: 1px solid transparent;
        }
        QToolBar QToolButton:hover { background: #e9ecef; border-color: #ced4da; }
        QToolBar QToolButton:pressed { background: #dee2e6; }
        QTableWidget {
            background: #ffffff; gridline-color: #e9ecef;
            border: 1px solid #dee2e6; border-radius: 4px;
            font-size: 13px;
        }
        QTableWidget::item { padding: 4px 6px; }
        QTableWidget::item:selected { background: #cfe2ff; color: #000; }
        QTableWidget::item:alternate { background: #f8f9fa; }
        QHeaderView::section {
            background: #f1f3f5; border: none;
            border-right: 1px solid #dee2e6; border-bottom: 1px solid #dee2e6;
            padding: 4px 8px; font-weight: 600; font-size: 12px;
        }
        QPushButton[checkable="true"] {
            background: #fff; border: 1px solid #dee2e6;
            border-radius: 4px; padding: 2px 10px; font-size: 12px;
        }
        QPushButton[checkable="true"]:checked {
            background: #0d6efd; color: white; border-color: #0d6efd;
        }
        QStatusBar { background: #f1f3f5; border-top: 1px solid #dee2e6; font-size: 12px; }
        """)

    # ── Tray ───────────────────────────────────────────────────────
    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        self.tray.setIcon(icon)
        self.tray.setToolTip("IDM Clone")
        tray_menu = QMenu()
        tray_menu.addAction("显示", self.show)
        tray_menu.addAction("新建下载", self._new_download)
        tray_menu.addSeparator()
        tray_menu.addAction("退出", self._quit)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.activateWindow()

    def closeEvent(self, event):
        if self.cfg.get("minimize_to_tray", True) and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
        else:
            self._quit()

    def _quit(self):
        QApplication.quit()

    # ── Timer & Refresh ────────────────────────────────────────────
    def _setup_refresh_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_table)
        self.timer.start(800)

    def _refresh_table(self):
        total_speed = 0.0
        active_count = 0

        for task in list(self.engine.tasks.values()):
            total_speed += task.speed
            if task.status == TaskStatus.DOWNLOADING:
                active_count += 1
            self._update_or_add_row(task)

        # Status bar
        self.lbl_status.setText(
            f"活跃: {active_count}  |  总速度: {fmt_speed(total_speed)}"
        )

        # Window title
        if self.cfg.get("show_speed_in_title", True) and total_speed > 0:
            self.setWindowTitle(f"IDM Clone — {fmt_speed(total_speed)}")
        else:
            self.setWindowTitle("IDM Clone — 多线程下载器")

    def _update_or_add_row(self, task: DownloadTask):
        if task.task_id not in self._task_rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._task_rows[task.task_id] = row
            # Progress bar widget in cell
            pb = QProgressBar()
            pb.setRange(0, 100)
            pb.setTextVisible(True)
            pb.setFixedHeight(18)
            self.table.setCellWidget(row, COL_PROGRESS, pb)
            # Store task_id in row
            self.table.setItem(row, COL_FILENAME, QTableWidgetItem(task.filename))
            self.table.item(row, COL_FILENAME).setData(Qt.ItemDataRole.UserRole, task.task_id)

        row = self._task_rows[task.task_id]

        self.table.item(row, COL_FILENAME).setText(task.filename)

        size_item = self.table.item(row, COL_SIZE)
        if not size_item:
            size_item = QTableWidgetItem()
            self.table.setItem(row, COL_SIZE, size_item)
        size_item.setText(fmt_size(task.total_size))

        pb: QProgressBar = self.table.cellWidget(row, COL_PROGRESS)
        if pb:
            pb.setValue(int(task.progress))
            pb.setFormat(f"{task.progress:.1f}%")

        def set_cell(col, text, color=None):
            item = self.table.item(row, col)
            if not item:
                item = QTableWidgetItem()
                self.table.setItem(row, col, item)
            item.setText(text)
            if color:
                item.setForeground(QBrush(QColor(color)))

        set_cell(COL_SPEED, fmt_speed(task.speed))
        set_cell(COL_ETA, fmt_eta(task.eta))
        status_color = COLORS.get(task.status, "#333")
        set_cell(COL_STATUS, STATUS_TEXT.get(task.status, ""), status_color)
        set_cell(COL_THREADS, str(task.threads))

    # ── Actions ────────────────────────────────────────────────────
    def _new_download(self, url: str = ""):
        dlg = AddUrlDialog(url=url, parent=self)
        dlg.task_added.connect(self._add_task_from_dialog)
        dlg.exec()

    @pyqtSlot(dict)
    def _add_task_from_dialog(self, info: dict):
        import uuid
        from engine import DownloadTask
        task = DownloadTask(
            url=info["url"],
            save_path=info.get("save_path", self.cfg.get("save_path", os.path.expanduser("~/Downloads"))),
            filename=info.get("filename", ""),
            task_id=str(uuid.uuid4()),
            threads=info.get("threads", self.cfg.get("default_threads", 8)),
            referrer=info.get("referrer", ""),
        )
        task.on_progress = lambda t: None  # handled by timer
        task.on_complete = self._on_task_complete
        task.on_error = self._on_task_error
        self.engine.add_task(task)

    def add_task_from_extension(self, task: DownloadTask = None, video_url: str = ""):
        """Called by server when extension sends a new download."""
        if video_url:
            self._new_download(url=video_url)
            return
        if task:
            task.on_complete = self._on_task_complete
            task.on_error = self._on_task_error

    def _on_task_complete(self, task: DownloadTask):
        if self.cfg.get("sound_on_complete", False):
            import winsound
            try:
                winsound.MessageBeep(winsound.MB_OK)
            except Exception:
                pass

    def _on_task_error(self, task: DownloadTask, msg: str):
        pass  # shown in table

    def _selected_tasks(self) -> list[DownloadTask]:
        rows = {i.row() for i in self.table.selectedIndexes()}
        tasks = []
        for task_id, row in self._task_rows.items():
            if row in rows:
                task = self.engine.tasks.get(task_id)
                if task:
                    tasks.append(task)
        return tasks

    def _pause_selected(self):
        for t in self._selected_tasks():
            self.engine.pause_task(t.task_id)

    def _resume_selected(self):
        for t in self._selected_tasks():
            self.engine.resume_task(t.task_id)

    def _cancel_selected(self):
        tasks = self._selected_tasks()
        if not tasks:
            return
        for t in tasks:
            self.engine.cancel_task(t.task_id)

    def _open_folder(self):
        for t in self._selected_tasks():
            path = t.save_path
            if os.path.exists(path):
                if sys.platform == "win32":
                    subprocess.Popen(f'explorer "{path}"')
            break

    def _open_file(self, index):
        row = index.row()
        for task_id, r in self._task_rows.items():
            if r == row:
                task = self.engine.tasks.get(task_id)
                if task and task.status == TaskStatus.COMPLETED:
                    fpath = task.full_path
                    if os.path.exists(fpath):
                        if sys.platform == "win32":
                            os.startfile(fpath)
                break

    def _context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("▶ 开始/继续", self._resume_selected)
        menu.addAction("⏸ 暂停", self._pause_selected)
        menu.addAction("✖ 取消", self._cancel_selected)
        menu.addSeparator()
        menu.addAction("📁 打开所在文件夹", self._open_folder)
        menu.addAction("🔗 复制链接", self._copy_url)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _copy_url(self):
        for t in self._selected_tasks():
            QApplication.clipboard().setText(t.url)
            break

    def _set_filter(self, label: str):
        for lbl, btn in self._filter_btns.items():
            btn.setChecked(lbl == label)
        self._current_filter = label
        # Filter rows
        filter_map = {
            "全部": None,
            "下载中": TaskStatus.DOWNLOADING,
            "已完成": TaskStatus.COMPLETED,
            "已暂停": TaskStatus.PAUSED,
            "出错": TaskStatus.ERROR,
        }
        target = filter_map.get(label)
        for task_id, row in self._task_rows.items():
            task = self.engine.tasks.get(task_id)
            if task:
                hide = target is not None and task.status != target
                self.table.setRowHidden(row, hide)

    def _open_settings(self):
        dlg = SettingsDialog(parent=self)
        dlg.settings_saved.connect(self._on_settings_saved)
        dlg.exec()

    @pyqtSlot(dict)
    def _on_settings_saved(self, new_cfg: dict):
        self.cfg.update(new_cfg)
        self.engine.config.update(new_cfg)
