import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Provide a QApplication instance for tests that need Qt."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
