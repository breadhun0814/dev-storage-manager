import sqlite3

import pytest

from dev_storage_manager.persistence.store import Store
from dev_storage_manager.scanning.scanner import scan


def test_old_schema_migration_and_summary(tmp_path):
    directory = tmp_path / "data"
    directory.mkdir()
    connection = sqlite3.connect(directory / "analysis.sqlite3")
    connection.execute("CREATE TABLE projects(path TEXT PRIMARY KEY, updated TEXT, status TEXT, result TEXT)")
    connection.commit()
    connection.close()
    store = Store(directory)
    root = tmp_path / "project"
    root.mkdir()
    (root / "source.py").write_bytes(b"12345")
    store.add(str(root))
    assert store.project_summaries()[0][3] is None
    store.save(scan(root))
    assert store.project_summaries()[0][3] == 5
    store.close()


def test_failed_save_rolls_back_previous_result_update(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    source = root / "source.py"
    source.write_bytes(b"1")
    store = Store(tmp_path / "data")
    store.add(str(root))
    store.save(scan(root))
    source.write_bytes(b"12345")
    store.db.execute("CREATE TRIGGER refuse_update BEFORE UPDATE ON projects BEGIN SELECT RAISE(ABORT,'disposable failure'); END")
    store.db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        store.save(scan(root))
    assert store.previous(str(root)) is None
    assert store.load(str(root)).size == 1
    assert source.read_bytes() == b"12345"
    store.close()
