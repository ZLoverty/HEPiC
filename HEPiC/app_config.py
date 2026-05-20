"""Application configuration and metadata helpers."""

from __future__ import annotations

import sys
from pathlib import Path


def find_app_file(filename: str, package_file: Path, compiled: bool = False) -> Path:
    """Find a bundled application file in source or compiled layouts."""
    candidates = [package_file.resolve().parent / filename]

    # PyInstaller: files land in sys._MEIPASS (_internal/ next to the exe)
    if hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates.extend([
            meipass / "HEPiC" / filename,
            meipass / filename,
        ])

    # Nuitka: files land next to the exe
    if compiled:
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            executable_dir / "HEPiC" / filename,
            executable_dir / filename,
        ])

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def load_config(config_file: Path) -> dict:
    import json

    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def build_main_window_stylesheet(
    background_color: str,
    foreground_color: str,
    secondary_background_color: str,
    secondary_foreground_color: str,
) -> str:
    return f"""
        QMainWindow, QWidget {{
            background-color: {background_color};
            color: {foreground_color};
        }}
        QPushButton {{
            background-color: {background_color};
            color: {foreground_color};
            border: 2px solid {secondary_foreground_color};
            border-radius: 10px;
            padding: 4px 10px;
        }}
        QPushButton:hover {{
            background-color: {secondary_foreground_color};
            color: {background_color};
        }}
        QPushButton:pressed {{
            background-color: {secondary_background_color};
        }}
        QPushButton:disabled {{
            background-color: #666666;
            color: #b0b0b0;
            border-color: #777777;
        }}
        QTextEdit, QPlainTextEdit {{
            background-color: "#2b2b2b";
            color: {foreground_color};
            border-radius: 10px;
            selection-background-color: {secondary_foreground_color};
            selection-color: {background_color};
        }}
        QTabWidget::pane {{
            border: 1px solid {secondary_background_color};
        }}
        QTabBar::tab {{
            background-color: {secondary_background_color};
            color: {foreground_color};
            padding: 6px 10px;
            margin: 1px;
        }}
        QTabBar::tab:selected {{
            background-color: {secondary_foreground_color};
            color: {background_color};
        }}
        """
