"""
Configuration manager - persists settings to config.json
"""
import json
import os

DEFAULT_CONFIG = {
    # Download settings
    "save_path": os.path.expanduser("~/Downloads"),
    "default_threads": 8,
    "max_concurrent": 3,
    "use_system_proxy": True,
    "custom_proxy": "",          # e.g. "http://127.0.0.1:7890"
    "proxy_mode": "system",      # "system" | "custom" | "none"

    # Capture filter settings
    "captured_types": [
        "zip", "rar", "7z", "tar", "gz", "bz2",
        "exe", "msi", "dmg", "pkg", "deb", "rpm",
        "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm",
        "mp3", "flac", "wav", "aac", "ogg",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
        "iso", "img", "bin",
    ],
    "min_size_mb": 1,           # Only capture files >= 1MB
    "site_blacklist": [],       # e.g. ["example.com", "ads.com"]

    # Server
    "server_port": 16800,

    # UI
    "start_minimized": False,
    "minimize_to_tray": True,
    "show_speed_in_title": True,
    "auto_start_download": True,
    "sound_on_complete": False,
}

_config_path = os.path.join(os.path.dirname(__file__), "config.json")
_config = {}


def load() -> dict:
    global _config
    _config = dict(DEFAULT_CONFIG)
    if os.path.exists(_config_path):
        try:
            with open(_config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            _config.update(saved)
        except Exception:
            pass
    return _config


def save(cfg: dict):
    global _config
    _config.update(cfg)
    with open(_config_path, "w", encoding="utf-8") as f:
        json.dump(_config, f, indent=2, ensure_ascii=False)


def get() -> dict:
    if not _config:
        load()
    return _config


def set_value(key: str, value):
    _config[key] = value
    save(_config)
