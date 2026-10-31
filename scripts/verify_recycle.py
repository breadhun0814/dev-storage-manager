"""Opt-in real recycle test. Creates and operates on disposable fixtures only.

The resulting cache remains in Windows Recycle Bin for manual restore checking.
No existing user project is accepted as input and the bin is never emptied.
"""
import json
import py_compile
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dev_storage_manager.cleanup.service import prepare, execute
from dev_storage_manager.persistence.journal import Journal
from dev_storage_manager.platform.recycle import WindowsRecycle
from dev_storage_manager.scanning.scanner import scan


def main():
    base = Path(__file__).resolve().parents[1] / "work"
    base.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="recycle-verification-", dir=base) as directory:
        root = Path(directory) / "한글 시험 프로젝트"
        root.mkdir()
        source = root / "fixture.py"
        source.write_bytes(b"disposable_fixture = 42\n")
        py_compile.compile(str(source), doraise=True)
        result = scan(root)
        plan = prepare(result, result.candidates[0])
        journal = Journal(Path(directory) / "journal")
        try:
            job = execute([plan], journal, WindowsRecycle())
            rows = journal.history()
            print(json.dumps({"job": job, "items": rows, "source_preserved": source.read_bytes() == b"disposable_fixture = 42\n"}, ensure_ascii=True))
            return 0 if rows[0][3] == "succeeded" else 1
        finally:
            journal.close()


if __name__ == "__main__":
    sys.exit(main())
