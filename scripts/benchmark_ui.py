"""Synthetic result-model rendering benchmark; no personal data is opened."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PySide6.QtWidgets import QApplication, QTabWidget
from dev_storage_manager.domain.models import Result, Folder
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.ui.main_window import Window


def main():
    app = QApplication([])
    work = Path(__file__).resolve().parents[1] / "work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ui-benchmark-", dir=work) as directory:
        window = Window(Store(Path(directory)))
        # Measure the actual folder view, not the initially selected candidates tab.
        window.findChild(QTabWidget).setCurrentIndex(1)
        window.show()
        app.processEvents()
        result = Result("C:/synthetic-fixture", folders=[Folder(f"C:/synthetic-fixture/{n:06}", n*10, n) for n in range(100000)])
        tracemalloc.start()
        start = time.perf_counter()
        window.display(result)
        app.processEvents()
        elapsed = time.perf_counter() - start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(json.dumps({"synthetic_folders": window.folder_proxy.rowCount(), "display_seconds": elapsed,
                          "python_peak_additional_traced_bytes": peak}, indent=2))
        window.close()


if __name__ == "__main__":
    main()
