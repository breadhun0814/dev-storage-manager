"""Repeatable metadata benchmark against generated disposable data only."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
import tracemalloc
from threading import Event

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dev_storage_manager.scanning.scanner import scan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folders", type=int, default=100)
    parser.add_argument("--files-per-folder", type=int, default=200)
    args = parser.parse_args()
    if not 1 <= args.folders <= 1000 or not 1 <= args.files_per_folder <= 1000:
        parser.error("시험 데이터 한도: 폴더 1~1000, 폴더당 파일 1~1000")
    base = Path(__file__).resolve().parents[1] / "work"
    base.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scan-benchmark-", dir=base) as temporary:
        root = Path(temporary)
        for number in range(args.folders):
            folder = root / f"시험 폴더 {number:04}"
            folder.mkdir()
            for file in range(args.files_per_folder):
                (folder / f"file-{file:04}.txt").write_bytes(b"x" * 128)
        reports = []
        tracemalloc.start()
        start = time.perf_counter()
        result = scan(root, progress=lambda *args: reports.append(time.perf_counter()))
        elapsed = time.perf_counter() - start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if result.status != "complete" or result.issues or result.files != args.folders * args.files_per_folder:
            raise RuntimeError("생성한 시험 자료 전체의 정상 분석을 확인하지 못했습니다.")
        event = Event()
        start = time.perf_counter()
        partial = scan(root, event, lambda *_: event.set())
        cancelled_elapsed = time.perf_counter() - start
        print(json.dumps({"python": sys.version.split()[0], "status": result.status,
                          "issue_count": len(result.issues), "files": result.files,
                          "folders": len(result.folders), "logical_bytes": result.size,
                          "scan_seconds_with_tracemalloc": elapsed, "python_peak_traced_bytes": peak,
                          "progress_events": len(reports), "cancel_test_seconds": cancelled_elapsed,
                          "cancel_status": partial.status}, indent=2))


if __name__ == "__main__":
    main()
