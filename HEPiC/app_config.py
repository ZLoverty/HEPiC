"""Application configuration and metadata helpers."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, packages_distributions, version
from pathlib import Path


def get_package_info(import_name: str) -> tuple[str, str]:
    """Return distribution name and version for a package import name."""
    dist_names = packages_distributions().get(import_name, [])
    dist_name = dist_names[0] if dist_names else import_name

    try:
        dist_version = version(dist_name)
    except PackageNotFoundError:
        dist_version = "unknown"

    return dist_name, dist_version


def find_app_file(filename: str, package_file: Path, compiled: bool = False) -> Path:
    """Find a bundled application file in source or compiled layouts."""
    candidates = [package_file.resolve().parent / filename]

    if compiled:
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                executable_dir / filename,
                executable_dir / "HEPiC" / filename,
            ]
        )

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
