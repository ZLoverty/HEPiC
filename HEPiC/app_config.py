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


def find_bundled_file(filename: str, package_file: Path, compiled: bool = False) -> Path:
    """Locate a read-only bundled resource, always from the shipped version.

    Unlike find_app_file, this never copies to ~/.HEPiC/, so an installed
    build always shows the changelog (or similar shipped content) that came
    with that build rather than a stale copy from a previous version.
    """
    candidates = [package_file.resolve().parent / filename]
    if hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates.extend([meipass / "HEPiC" / filename, meipass / filename])
    if compiled:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir / "HEPiC" / filename, exe_dir / filename])

    return next((c for c in candidates if c.exists()), candidates[0])


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
        /* QTabBar::tab intentionally has no rules here at all (not even
        background-color/:selected/:hover). Any box-model or background
        property on this selector makes QStyleSheetStyle own the tab's
        painting outright, bypassing _TopAlignedTabBarStyle.drawControl() in
        __main__.py. That broke icon centering before (CE_TabBarTabLabel got
        a lopsided icon with the padding/margin properties), and separately
        it made the selected/hover highlight never repaint on hover — Qt's
        own State_MouseOver tracking on the tab is fine, but QStyleSheetStyle's
        parallel hover bookkeeping for this vertical, custom-styled QTabBar
        never picked it up. The proxy style now paints the tab background
        itself using option.state directly, sidestepping that entirely. */
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
