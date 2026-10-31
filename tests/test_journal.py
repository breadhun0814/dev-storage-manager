from dev_storage_manager.persistence.journal import Journal
from dev_storage_manager.persistence.journal import JournalError
import sqlite3
import pytest


def test_partial_failure_and_restart_unknown(tmp_path):
    journal = Journal(tmp_path)
    job = journal.begin([("a", 10), ("b", 20), ("c", 30)], 100)
    journal.item(job, "a", "running")
    journal.item(job, "a", "succeeded", destination="recycle/a")
    journal.item(job, "b", "running")
    journal.close()
    journal = Journal(tmp_path)
    journal.recover()
    rows = {row[1]: row for row in journal.history()}
    assert rows["a"][3] == "succeeded"
    assert rows["b"][3] == "unknown" and "미확정" in rows["b"][4]
    assert rows["c"][3] == "cancelled"
    assert rows["b"][7] is None
    journal.close()


def test_failed_is_not_success_and_free_space_is_separate(tmp_path):
    journal = Journal(tmp_path)
    job = journal.begin([("a", 10000)], 10)
    journal.item(job, "a", "running")
    journal.item(job, "a", "failed", "사용 중")
    journal.finish(job, "failed", 8)
    row = journal.history()[0]
    assert row[2] == 10000 and row[3] == "failed" and row[6:8] == (10, 8)
    journal.close()


def test_missing_record_and_premature_success_are_rejected(tmp_path):
    journal = Journal(tmp_path)
    job = journal.begin([("fixture", 10)], None)
    with pytest.raises(JournalError):
        journal.item(job, "missing", "running")
    with pytest.raises(JournalError):
        journal.item(job, "fixture", "succeeded", destination="fixture-bin")
    with pytest.raises(JournalError):
        journal.finish(job, "succeeded", None)
    journal.item(job, "fixture", "running")
    with pytest.raises(JournalError):
        journal.item(job, "fixture", "succeeded")
    journal.item(job, "fixture", "failed", "fixture failure")
    with pytest.raises(JournalError):
        journal.finish(job, "succeeded", None)
    journal.finish(job, "failed", None)
    with pytest.raises(JournalError):
        journal.item(job, "fixture", "succeeded", destination="fixture-bin")
    assert journal.history()[0][3] == "failed"
    journal.close()


def test_restart_recovery_is_atomic_and_idempotent(tmp_path):
    journal = Journal(tmp_path)
    job = journal.begin([("a", 10), ("b", 20)], None)
    journal.item(job, "a", "running")
    journal.db.execute("""CREATE TRIGGER fixture_recovery_failure BEFORE UPDATE OF status ON cleanup_items
        WHEN NEW.status='cancelled' BEGIN SELECT RAISE(ABORT, 'fixture recovery failure'); END""")
    journal.db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        journal.recover()
    assert [row[3] for row in journal.history()] == ["running", "pending"]
    assert journal.db.execute("SELECT status FROM cleanup_jobs").fetchone() == ("running",)
    journal.db.execute("DROP TRIGGER fixture_recovery_failure")
    journal.db.commit()
    journal.close()
    journal = Journal(tmp_path)
    journal.recover()
    before = journal.history()
    assert [row[3] for row in before] == ["unknown", "cancelled"]
    journal.recover()
    assert journal.history() == before
    journal.close()
