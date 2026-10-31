"""Measure read-only history queries on owned synthetic SQLite metadata only."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from threading import Event, Timer
from time import perf_counter
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dev_storage_manager.persistence.journal import Journal, HistoryCancelled


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=20000)
    args = parser.parse_args()
    if not 1000 <= args.rows <= 1000000:
        parser.error("--rows must be between 1000 and 1000000")
    work = ROOT / "work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="history-benchmark-", dir=work) as temporary:
        directory = Path(temporary)
        journal = Journal(directory)
        with journal.db:
            journal.db.executemany("INSERT INTO cleanup_jobs VALUES (?,?,?,?,?)", (
                (str(n), "2026-01-01T00:00:00+09:00", "failed" if n % 10 == 0 else "succeeded", 100000, 100000)
                for n in range(args.rows)))
            journal.db.executemany("INSERT INTO cleanup_items VALUES (?,?,?,?,?,?,?)", (
                (str(n), f"C:/임시 측정/프로젝트 {n:06d}/__pycache__", 1024,
                 "failed" if n % 10 == 0 else "succeeded", "사용 중 [측정%_]" if n % 10 == 0 else "",
                 None if n % 10 == 0 else "fixture-receipt", "2026-01-01T00:00:00+09:00")
                for n in range(args.rows)))
        journal.close()
        file = directory / "analysis.sqlite3"
        before = hashlib.sha256(file.read_bytes()).digest()
        reader = Journal(directory, read_only=True)
        measurements = {}
        for name, options in (("first_page", {}), ("far_page", {"offset": args.rows - 200}),
                              ("path_search", {"query": f"프로젝트 {args.rows - 1:06d}"}),
                              ("reason_search", {"query": "[측정%_]"})):
            tracemalloc.start()
            started = perf_counter()
            page = reader.history_page(**options)
            elapsed = perf_counter() - started
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            measurements[name] = {"seconds": elapsed, "python_traced_peak_bytes": peak,
                                  "returned_rows": len(page.records), "matching_rows": page.total}
        tracemalloc.start()
        started = perf_counter()
        legacy_rows = reader.history(include_job_status=True)
        legacy_elapsed = perf_counter() - started
        _, legacy_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        measurements["legacy_all_rows"] = {"seconds": legacy_elapsed, "python_traced_peak_bytes": legacy_peak,
                                           "returned_rows": len(legacy_rows), "matching_rows": len(legacy_rows)}
        del legacy_rows
        cancel = Event()
        timer = Timer(0.01, cancel.set)
        statements = []
        reader.db.set_trace_callback(statements.append)
        started = perf_counter()
        timer.start()
        cancelled = False
        try:
            reader.history_page(query="nonexistent full-history search", cancel=cancel)
        except HistoryCancelled:
            cancelled = True
        finally:
            timer.cancel()
            timer.join()
        cancellation_seconds = perf_counter() - started
        reader.close()
        result = {"synthetic_rows": args.rows, "measurements": measurements,
                  "cancelled": cancelled, "cancellation_seconds": cancellation_seconds,
                  "count_query_started": any("SELECT COUNT(*)" in sql for sql in statements),
                  "database_unchanged": hashlib.sha256(file.read_bytes()).digest() == before,
                  "scope": "Queries with tracemalloc; excludes fixture creation, hashing, SQLite native/Qt/RSS and temporary cleanup. No real trash operations."}
    result["temporary_directory_removed"] = not directory.exists()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
