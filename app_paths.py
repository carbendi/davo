"""Writable per-user storage shared by source and packaged builds."""

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "SpeedEditorCustomizer"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SpeedEditorCustomizer"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "SpeedEditorCustomizer"


def legacy_config_file() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "config.json"
    return Path(__file__).resolve().parent / "config.json"
