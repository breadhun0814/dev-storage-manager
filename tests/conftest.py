import pytest
from PySide6.QtCore import QEventLoop, QTimer


@pytest.fixture
def wait_for_idle():
    def wait(window, app):
        if window.worker is None:
            return
        loop = QEventLoop()
        window.worker.finished.connect(loop.quit)
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        app.processEvents()
        assert window.worker is None
    return wait


@pytest.fixture
def wait_for_history():
    def wait(window, app):
        from time import monotonic
        deadline = monotonic() + 10
        while window.history_worker is not None or window.history_search_timer.isActive():
            assert monotonic() < deadline, "history query timed out"
            loop = QEventLoop()
            QTimer.singleShot(5, loop.quit)
            loop.exec()
            app.processEvents()
    return wait
