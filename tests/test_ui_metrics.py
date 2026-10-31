import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from dev_storage_manager.domain.models import Result
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.ui.main_window import Window


def test_switching_to_unanalyzed_project_does_not_keep_previous_totals(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "분석할 프로젝트"
    root.mkdir()
    store = Store(tmp_path / "data")
    store.add(str(root))
    window = Window(store)
    window.display(Result(str(root), size=2048, files=8))
    assert window.metric_values[1].text() == "8"
    window.projects.selectRow(0)
    window.open_result()
    assert all(label.text() == "—" for label in window.metric_values)
    window.close()
