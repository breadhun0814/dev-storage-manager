"""Compare folder-index work and GUI heartbeat on synthetic metadata only."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path
import sys
from time import perf_counter
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from PySide6.QtCore import QSortFilterProxyModel, Qt, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from dev_storage_manager.domain.models import Folder
from dev_storage_manager.ui.folder_model import FolderModel
from dev_storage_manager.ui.folder_proxy import FolderProxy


def pump(milliseconds=15):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def main():
    app = QApplication([])
    model = FolderModel()
    model.set_folders([Folder(f"C:/합성 폴더/자료 {n:06d} [1]", (n * 7919) % 100003, n) for n in range(100000)])
    legacy = QSortFilterProxyModel()
    legacy.setSourceModel(model)
    legacy.setSortRole(Qt.ItemDataRole.UserRole)
    legacy.setFilterRole(Qt.ItemDataRole.UserRole)
    legacy.setFilterKeyColumn(0)
    legacy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    proxy = FolderProxy()
    proxy.setSourceModel(model)
    timer = QTimer()
    timer.setInterval(5)
    gaps, last = [], [perf_counter()]
    def tick():
        current = perf_counter()
        gaps.append(current - last[0])
        last[0] = current
    timer.timeout.connect(tick)
    timer.start()
    measurements = {}
    legacy_order, legacy_matches = None, None
    same_order, same_matches = False, False
    for name, action, asynchronous in (
        ("legacy_numeric_sort", lambda: legacy.sort(1, Qt.SortOrder.DescendingOrder), False),
        ("legacy_literal_filter", lambda: legacy.setFilterFixedString("자료 099999 [1]"), False),
        ("async_numeric_sort", lambda: proxy.sort(1, Qt.SortOrder.DescendingOrder), True),
        ("async_literal_filter", lambda: proxy.setFilterFixedString("자료 099999 [1]"), True)):
        pump()
        gaps.clear()
        last[0] = perf_counter()
        started = perf_counter()
        action()
        if asynchronous:
            while proxy.worker is not None or proxy.timer.isActive():
                pump(5)
        app.processEvents()
        elapsed = perf_counter() - started
        tick()
        view = proxy if asynchronous else legacy
        measurements[name] = {"seconds": elapsed, "max_gui_heartbeat_gap_seconds": max(gaps),
                              "heartbeat_count": len(gaps), "returned_rows": view.rowCount()}
        if name == "legacy_numeric_sort":
            legacy_order = [legacy.mapToSource(legacy.index(row, 0)).row() for row in range(legacy.rowCount())]
        elif name == "legacy_literal_filter":
            legacy_matches = [legacy.mapToSource(legacy.index(row, 0)).row() for row in range(legacy.rowCount())]
        elif name == "async_numeric_sort":
            same_order = list(proxy.indices) == legacy_order
        elif name == "async_literal_filter":
            same_matches = list(proxy.indices) == legacy_matches
    # Separately measure Python index allocation; timing above has no tracer.
    proxy.setFilterFixedString("")
    while proxy.worker is not None or proxy.timer.isActive():
        pump(5)
    tracemalloc.start()
    proxy.sort(2, Qt.SortOrder.AscendingOrder)
    while proxy.worker is not None:
        pump(5)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    timer.stop()
    proxy.shutdown()
    if not same_order or not same_matches:
        raise RuntimeError("query result differs from the previous implementation")
    print(json.dumps({"synthetic_folders": model.rowCount(), "measurements": measurements,
                      "numeric_order_matches_legacy": same_order, "filter_matches_legacy": same_matches,
                      "async_index_python_traced_peak_bytes": peak,
                      "scope": "Bare Qt models/index workers, 5ms GUI timer. Search includes 200ms debounce. Excludes fixture creation, painting, native Qt/RSS, filesystem scan or cleanup."}, indent=2))


if __name__ == "__main__":
    main()
