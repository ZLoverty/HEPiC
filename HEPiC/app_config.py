"""Application configuration and metadata helpers."""

from __future__ import annotations

import sys
from pathlib import Path


def find_app_file(filename: str, package_file: Path, compiled: bool = False) -> Path:
    """Find a bundled application file in source or compiled layouts.

    When running as an installed binary (PyInstaller or Nuitka), the file is
    stored under ~/.HEPiC/ so the user can edit it without admin rights.  On
    the very first launch the bundled default is copied there automatically.
    In development (plain source run) the source-tree file is used directly.
    """
    is_installed = compiled or hasattr(sys, "_MEIPASS")

    if is_installed:
        user_path = Path.home() / ".HEPiC" / filename
        if user_path.exists():
            return user_path

    # Locate the bundled default.
    candidates = [package_file.resolve().parent / filename]
    if hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates.extend([meipass / "HEPiC" / filename, meipass / filename])
    if compiled:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir / "HEPiC" / filename, exe_dir / filename])

    bundled = next((c for c in candidates if c.exists()), candidates[0])

    if is_installed:
        # First run: seed the user config from the bundled default.
        import shutil
        user_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled, user_path)
        return user_path

    return bundled


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
        QProgressBar {{
            background-color: {secondary_background_color};
            color: {foreground_color};
            border: 1px solid {secondary_background_color};
            border-radius: 6px;
            text-align: center;
            min-height: 28px;
            max-height: 28px;
            font-size: 12px;
        }}
        QProgressBar::chunk {{
            background-color: {secondary_foreground_color};
            border-radius: 5px;
        }}
        """
