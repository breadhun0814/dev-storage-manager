"""Measure a real offscreen Qt review with owned synthetic metadata only."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QWidget
from dev_storage_manager.cleanup.review import Review, IncludedFile, MAX_REVIEW_FILES
from dev_storage_manager.domain.models import Candidate
from dev_storage_manager.ui.review_dialog import ReviewDialog, IncludedModel
from dev_storage_manager.ui.application import configure_font
from dev_storage_manager.ui.theme import STYLE


def settle(dialog, app):
    deadline = perf_counter() + 20
    while dialog.worker is not None or dialog.timer.isActive():
        if perf_counter() > deadline:
            raise RuntimeError("review benchmark timed out")
        loop = QEventLoop()
        QTimer.singleShot(5, loop.quit)
        loop.exec()
        app.processEvents()
    app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=MAX_REVIEW_FILES)
    args = parser.parse_args()
    if not 1 <= args.rows <= MAX_REVIEW_FILES:
        parser.error("rows exceeds the production review bound")
    app = QApplication([])
    configure_font(app)
    parent = QWidget()
    parent.setStyleSheet(STYLE)
    parent.resize(800, 600)
    root = r"C:\합성 검토 자료\후보 폴더"
    files = [IncludedFile(root + rf"\하위\파일 {n:05d}.bin", (args.rows - n) * 1024) for n in range(args.rows)]
    candidate = Candidate(root, "node-deps", sum(f.size for f in files), len(files), "합성 메타데이터", "실제 파일 아님", "실행 없음")
    review = Review(r"C:\합성 검토 자료", candidate, files, "fixture", [])
    calls = [0]
    original = IncludedModel.data
    def counted(self, *args, **kwargs):
        calls[0] += 1
        return original(self, *args, **kwargs)
    IncludedModel.data = counted
    tracemalloc.start()
    started = perf_counter()
    dialog = ReviewDialog(review, ["실제 이동을 하지 않는 합성 측정"], False, parent)
    dialog.show()
    settle(dialog, app)
    creation_seconds = perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    initial_calls = calls[0]
    started = perf_counter()
    dialog.search.setText(f"파일 {args.rows - 1:05d}")
    settle(dialog, app)
    search_seconds = perf_counter() - started
    work = ROOT / "work"
    work.mkdir(exist_ok=True)
    dialog.grab().save(str(work / "review-benchmark-800.png"))
    record = {"synthetic_rows": len(files), "initial_rows": args.rows, "search_rows": dialog.model.rowCount(),
              "dialog_size": [dialog.width(), dialog.height()], "creation_and_initial_sort_seconds": creation_seconds,
              "python_traced_peak_bytes": peak, "initial_model_data_calls": initial_calls,
              "search_with_200ms_debounce_seconds": search_seconds, "cleanup_enabled": dialog.run_button.isEnabled(),
              "scope": "Real offscreen Qt view/index worker; excludes fixture creation, native Qt/RSS, disk scanning and any filesystem move."}
    dialog.reject()
    settle(dialog, app)
    parent.close()
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
