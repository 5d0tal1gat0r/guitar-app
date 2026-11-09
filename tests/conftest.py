import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

_APP = None


@pytest.fixture(scope="session")
def app():
    """One QApplication for the whole run, kept alive until interpreter exit."""
    global _APP
    from PySide6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
    return _APP


@pytest.fixture(autouse=True)
def _delete_widgets(request):
    """Destroy every top-level widget a test created, while the app still exists."""
    yield
    if _APP is None:
        return
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
