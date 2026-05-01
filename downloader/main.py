"""
IDM Clone - Multi-thread download manager
Entry point: starts Flask server + PyQt6 GUI
"""
import sys
import os

# Allow importing from downloader/
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

import config_manager
from engine import DownloadEngine
from server import init_server, run_server
from gui.main_window import MainWindow


def main():
    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("IDM Clone")
    app.setOrganizationName("IDMClone")

    # Load config
    cfg = config_manager.load()

    # Start download engine
    engine = DownloadEngine(cfg)

    # Start main window
    window = MainWindow(engine, app)

    # Start Flask server for browser extension
    def gui_callback(task=None, video_url=""):
        window.add_task_from_extension(task=task, video_url=video_url)

    init_server(engine, cfg, gui_callback)
    port = cfg.get("server_port", 16800)
    run_server(port=port)

    # Show window
    if cfg.get("start_minimized", False):
        window.hide()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
