"""
Settings dialog - all user-configurable options.
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QListWidget, QListWidgetItem, QFileDialog,
    QGroupBox, QRadioButton, QButtonGroup, QTextEdit, QMessageBox,
    QGridLayout, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
import config_manager


class TagListWidget(QWidget):
    """Widget to display and edit a list of tags (file types, sites)."""
    changed = pyqtSignal(list)

    def __init__(self, items: list, placeholder: str = "", parent=None):
        super().__init__(parent)
        self._items = list(items)
        self.placeholder = placeholder
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.setMaximumHeight(130)
        layout.addWidget(self.list_widget)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText(self.placeholder)
        self.input.returnPressed.connect(self._add_item)
        row.addWidget(self.input)

        btn_add = QPushButton("添加")
        btn_add.setFixedWidth(60)
        btn_add.clicked.connect(self._add_item)
        row.addWidget(btn_add)

        btn_del = QPushButton("删除")
        btn_del.setFixedWidth(60)
        btn_del.clicked.connect(self._delete_selected)
        row.addWidget(btn_del)

        layout.addLayout(row)
        self._refresh()

    def _refresh(self):
        self.list_widget.clear()
        for item in self._items:
            self.list_widget.addItem(QListWidgetItem(item))

    def _add_item(self):
        text = self.input.text().strip().lower()
        if text and text not in self._items:
            self._items.append(text)
            self._refresh()
            self.changed.emit(self._items)
        self.input.clear()

    def _delete_selected(self):
        selected = [i.text() for i in self.list_widget.selectedItems()]
        self._items = [x for x in self._items if x not in selected]
        self._refresh()
        self.changed.emit(self._items)

    def get_items(self) -> list:
        return list(self._items)

    def set_items(self, items: list):
        self._items = list(items)
        self._refresh()


class SettingsDialog(QDialog):
    settings_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumSize(620, 520)
        self.cfg = dict(config_manager.get())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)

        tabs = QTabWidget()
        tabs.addTab(self._tab_download(), "下载")
        tabs.addTab(self._tab_capture(), "捕获过滤")
        tabs.addTab(self._tab_proxy(), "代理")
        tabs.addTab(self._tab_ui(), "界面")
        layout.addWidget(tabs)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_save = QPushButton("保存")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    # ── Tab: Download ──────────────────────────────────────────────
    def _tab_download(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)

        # Save path
        grp = QGroupBox("保存路径")
        grp_layout = QHBoxLayout(grp)
        self.save_path_edit = QLineEdit(self.cfg.get("save_path", ""))
        grp_layout.addWidget(self.save_path_edit)
        btn_browse = QPushButton("浏览...")
        btn_browse.setFixedWidth(70)
        btn_browse.clicked.connect(self._browse_path)
        grp_layout.addWidget(btn_browse)
        layout.addWidget(grp)

        # Thread settings
        grp2 = QGroupBox("下载线程")
        g2 = QGridLayout(grp2)
        g2.addWidget(QLabel("单任务分片线程数:"), 0, 0)
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 32)
        self.threads_spin.setValue(self.cfg.get("default_threads", 8))
        self.threads_spin.setSuffix(" 线程")
        g2.addWidget(self.threads_spin, 0, 1)

        g2.addWidget(QLabel("最大同时下载任务:"), 1, 0)
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(self.cfg.get("max_concurrent", 3))
        self.concurrent_spin.setSuffix(" 个")
        g2.addWidget(self.concurrent_spin, 1, 1)
        layout.addWidget(grp2)

        # Auto start
        self.auto_start_cb = QCheckBox("添加后自动开始下载")
        self.auto_start_cb.setChecked(self.cfg.get("auto_start_download", True))
        layout.addWidget(self.auto_start_cb)

        layout.addStretch()
        return w

    def _browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择保存目录", self.save_path_edit.text())
        if path:
            self.save_path_edit.setText(path)

    # ── Tab: Capture Filter ────────────────────────────────────────
    def _tab_capture(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        # File types
        grp1 = QGroupBox("捕获的文件类型（扩展名，不含点）")
        g1 = QVBoxLayout(grp1)
        self.type_list = TagListWidget(
            self.cfg.get("captured_types", []),
            placeholder="如: mp4  exe  zip（回车添加）"
        )
        g1.addWidget(self.type_list)
        hint = QLabel("留空 = 捕获所有类型")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        g1.addWidget(hint)
        layout.addWidget(grp1)

        # Min size
        grp2 = QGroupBox("最小文件大小过滤")
        g2 = QHBoxLayout(grp2)
        g2.addWidget(QLabel("仅捕获 ≥"))
        self.min_size_spin = QDoubleSpinBox()
        self.min_size_spin.setRange(0, 10240)
        self.min_size_spin.setDecimals(1)
        self.min_size_spin.setValue(self.cfg.get("min_size_mb", 1))
        self.min_size_spin.setSuffix(" MB")
        g2.addWidget(self.min_size_spin)
        g2.addWidget(QLabel("的文件（0 = 不限制）"))
        g2.addStretch()
        layout.addWidget(grp2)

        # Site blacklist
        grp3 = QGroupBox("站点黑名单（不捕获这些站点的下载）")
        g3 = QVBoxLayout(grp3)
        self.site_blacklist = TagListWidget(
            self.cfg.get("site_blacklist", []),
            placeholder="如: ads.example.com  cdn.badsite.com"
        )
        g3.addWidget(self.site_blacklist)
        layout.addWidget(grp3)

        layout.addStretch()
        return w

    # ── Tab: Proxy ─────────────────────────────────────────────────
    def _tab_proxy(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        grp = QGroupBox("代理设置")
        g = QVBoxLayout(grp)

        self.proxy_group = QButtonGroup(self)
        self.rb_system = QRadioButton("使用系统代理（推荐，自动读取 Windows 代理设置）")
        self.rb_custom = QRadioButton("使用自定义代理")
        self.rb_none = QRadioButton("不使用代理（直连）")

        self.proxy_group.addButton(self.rb_system, 0)
        self.proxy_group.addButton(self.rb_custom, 1)
        self.proxy_group.addButton(self.rb_none, 2)

        mode = self.cfg.get("proxy_mode", "system")
        if mode == "custom":
            self.rb_custom.setChecked(True)
        elif mode == "none":
            self.rb_none.setChecked(True)
        else:
            self.rb_system.setChecked(True)

        g.addWidget(self.rb_system)
        g.addWidget(self.rb_custom)

        proxy_row = QHBoxLayout()
        proxy_row.addSpacing(20)
        proxy_row.addWidget(QLabel("代理地址:"))
        self.proxy_edit = QLineEdit(self.cfg.get("custom_proxy", ""))
        self.proxy_edit.setPlaceholderText("http://127.0.0.1:7890")
        proxy_row.addWidget(self.proxy_edit)
        g.addLayout(proxy_row)

        g.addWidget(self.rb_none)
        layout.addWidget(grp)

        info = QLabel("系统代理模式下，会自动读取 Windows「网络和 Internet」→「代理」中的设置，\n与 Clash/V2Ray 等工具兼容。")
        info.setStyleSheet("color: #555; font-size: 11px; padding: 4px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()
        return w

    # ── Tab: UI ────────────────────────────────────────────────────
    def _tab_ui(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        self.start_min_cb = QCheckBox("启动时最小化到系统托盘")
        self.start_min_cb.setChecked(self.cfg.get("start_minimized", False))
        layout.addWidget(self.start_min_cb)

        self.tray_cb = QCheckBox("关闭窗口时最小化到系统托盘（不退出）")
        self.tray_cb.setChecked(self.cfg.get("minimize_to_tray", True))
        layout.addWidget(self.tray_cb)

        self.speed_title_cb = QCheckBox("在标题栏显示当前下载速度")
        self.speed_title_cb.setChecked(self.cfg.get("show_speed_in_title", True))
        layout.addWidget(self.speed_title_cb)

        self.sound_cb = QCheckBox("下载完成时播放提示音")
        self.sound_cb.setChecked(self.cfg.get("sound_on_complete", False))
        layout.addWidget(self.sound_cb)

        layout.addStretch()
        return w

    # ── Save ───────────────────────────────────────────────────────
    def _save(self):
        # Proxy mode
        if self.rb_custom.isChecked():
            proxy_mode = "custom"
        elif self.rb_none.isChecked():
            proxy_mode = "none"
        else:
            proxy_mode = "system"

        new_cfg = {
            "save_path": self.save_path_edit.text().strip() or os.path.expanduser("~/Downloads"),
            "default_threads": self.threads_spin.value(),
            "max_concurrent": self.concurrent_spin.value(),
            "auto_start_download": self.auto_start_cb.isChecked(),
            "captured_types": self.type_list.get_items(),
            "min_size_mb": self.min_size_spin.value(),
            "site_blacklist": self.site_blacklist.get_items(),
            "proxy_mode": proxy_mode,
            "custom_proxy": self.proxy_edit.text().strip(),
            "use_system_proxy": proxy_mode == "system",
            "start_minimized": self.start_min_cb.isChecked(),
            "minimize_to_tray": self.tray_cb.isChecked(),
            "show_speed_in_title": self.speed_title_cb.isChecked(),
            "sound_on_complete": self.sound_cb.isChecked(),
        }
        config_manager.save(new_cfg)
        self.settings_saved.emit(new_cfg)
        self.accept()
