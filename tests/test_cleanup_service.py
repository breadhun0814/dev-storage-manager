import py_compile
from pathlib import Path
from threading import Event
import sqlite3

import pytest

from dev_storage_manager.cleanup.service import prepare, execute
from dev_storage_manager.persistence.journal import Journal
from dev_storage_manager.platform.recycle import Receipt
from dev_storage_manager.scanning.scanner import scan


def project(root):
    root.mkdir()
    for name in ("first", "second"):
        folder = root / name
        folder.mkdir()
        source = folder / "main.py"
        source.write_bytes(b"value = 1\n")
        py_compile.compile(str(source), doraise=True)
    result = scan(root)
    return [prepare(result, candidate) for candidate in result.candidates]


class FakeRecycle:
    """Moves fixtures to another temporary folder; never permanently deletes."""
    def __init__(self, destination):
        self.destination = destination
        self.destination.mkdir()

    def move(self, path, validate):
        validate()
        destination = self.destination / path.parent.name
        path.rename(destination)
        return Receipt(str(path), str(destination))


def test_partial_success_and_failure_preserve_sources(tmp_path):
    root = tmp_path / "project"
    plans = project(root)
    journal = Journal(tmp_path / "data")
    backend = FakeRecycle(tmp_path / "fake-bin")
    original_move = backend.move
    def partial(path, validate):
        if path.parent.name == "second":
            raise OSError("사용 중인 파일 시험")
        return original_move(path, validate)
    backend.move = partial
    execute(plans, journal, backend)
    statuses = {Path(row[1]).parent.name: row[3] for row in journal.history()}
    assert statuses == {"first": "succeeded", "second": "failed"}
    assert (root / "first/main.py").read_bytes() == b"value = 1\n"
    assert (root / "second/__pycache__").is_dir()
    assert (tmp_path / "fake-bin/first").is_dir()
    journal.close()


def test_modified_target_never_calls_backend(tmp_path):
    plans = project(tmp_path / "project")
    target = Path(plans[0].candidate.path)
    (target / "personal.txt").write_bytes(b"keep")
    class Forbidden:
        def move(self, *_):
            raise AssertionError("변경된 대상에 도달하면 안 됨")
    journal = Journal(tmp_path / "data")
    execute([plans[0]], journal, Forbidden())
    assert journal.history()[0][3] == "failed"
    assert (target / "personal.txt").read_bytes() == b"keep"
    journal.close()


def test_cancelled_before_execution(tmp_path):
    plans = project(tmp_path / "project")
    journal = Journal(tmp_path / "data")
    event = Event()
    event.set()
    execute(plans, journal, None, event)
    assert all(row[3] == "cancelled" for row in journal.history())
    assert all(Path(p.candidate.path).exists() for p in plans)
    journal.close()


@pytest.mark.parametrize("phase", ["running", "succeeded", "failed"])
def test_recording_failure_stops_remaining_operations(tmp_path, phase):
    plans = project(tmp_path / "project")
    directory = tmp_path / "data"
    journal = Journal(directory)
    journal.db.execute(f"""CREATE TRIGGER fixture_record_failure BEFORE UPDATE OF status ON cleanup_items
        WHEN NEW.status='{phase}' BEGIN SELECT RAISE(ABORT, 'fixture journal write failure'); END""")
    journal.db.commit()
    backend = FakeRecycle(tmp_path / "fake-bin")
    move = backend.move
    calls = []
    def observed(path, validate):
        calls.append(str(path))
        if phase == "failed":
            raise OSError("fixture backend failure")
        return move(path, validate)
    backend.move = observed
    with pytest.raises(sqlite3.IntegrityError, match="fixture journal"):
        execute(plans, journal, backend)
    assert calls == ([] if phase == "running" else [plans[0].candidate.path])
    rows = {row[1]: row for row in journal.history()}
    assert rows[plans[0].candidate.path][3] == ("cancelled" if phase == "running" else "unknown")
    assert rows[plans[1].candidate.path][3] == "cancelled"
    assert Path(plans[1].candidate.path).is_dir()
    assert Path(plans[0].candidate.path).exists() == (phase != "succeeded")
    assert journal.db.execute("SELECT status FROM cleanup_jobs").fetchone() == ("interrupted",)
    journal.close()
    journal = Journal(directory)
    journal.recover()
    assert journal.history() == list(rows.values())
    journal.close()
    for name in ("first", "second"):
        assert (tmp_path / "project" / name / "main.py").read_bytes() == b"value = 1\n"


def test_cancel_during_validation_never_calls_backend(tmp_path, monkeypatch):
    from dev_storage_manager.cleanup import service
    plans = project(tmp_path / "project")
    cancel = Event()
    def cancelled(*_):
        cancel.set()
        raise ValueError("fixture cancelled during proof")
    monkeypatch.setattr(service, "verify", cancelled)
    class Forbidden:
        calls = []
        def move(self, *args):
            self.calls.append(args)
    journal = Journal(tmp_path / "data")
    backend = Forbidden()
    execute(plans, journal, backend, cancel)
    assert not backend.calls
    assert all(row[3] == "cancelled" for row in journal.history())
    assert all(Path(p.candidate.path).is_dir() for p in plans)
    journal.close()


def test_cancel_after_request_does_not_claim_no_move(tmp_path):
    plans = project(tmp_path / "project")
    cancel = Event()
    backend = FakeRecycle(tmp_path / "fake-bin")
    move = backend.move
    calls = []
    def uncertain(path, validate):
        calls.append(str(path))
        move(path, validate)
        cancel.set()
        raise OSError("fixture cancellation with lost response")
    backend.move = uncertain
    journal = Journal(tmp_path / "data")
    execute(plans, journal, backend, cancel)
    rows = {row[1]: row for row in journal.history()}
    assert calls == [plans[0].candidate.path]
    assert rows[plans[0].candidate.path][3] == "unknown"
    assert rows[plans[1].candidate.path][3] == "cancelled"
    assert Path(plans[1].candidate.path).is_dir()
    journal.close()


def test_final_job_write_failure_preserves_confirmed_move(tmp_path):
    plans = project(tmp_path / "project")[:1]
    journal = Journal(tmp_path / "data")
    journal.db.execute("""CREATE TRIGGER fixture_finish_failure BEFORE UPDATE OF status ON cleanup_jobs
        WHEN NEW.status='succeeded' BEGIN SELECT RAISE(ABORT, 'fixture finish failure'); END""")
    journal.db.commit()
    with pytest.raises(sqlite3.IntegrityError, match="fixture finish"):
        execute(plans, journal, FakeRecycle(tmp_path / "fake-bin"))
    assert journal.history()[0][3] == "succeeded"
    assert journal.history()[0][5]
    assert journal.db.execute("SELECT status FROM cleanup_jobs").fetchone() == ("interrupted",)
    assert journal.history()[0][7] is None
    journal.close()


def test_failed_interruption_record_is_recovered_after_restart(tmp_path):
    plans = project(tmp_path / "project")
    directory = tmp_path / "data"
    journal = Journal(directory)
    backend = FakeRecycle(tmp_path / "fake-bin")
    move = backend.move
    calls = []
    def loss_of_recording(path, validate):
        calls.append(str(path))
        receipt = move(path, validate)
        journal.db.execute("""CREATE TRIGGER fixture_all_updates_fail BEFORE UPDATE ON cleanup_items
            BEGIN SELECT RAISE(ABORT, 'fixture persistent write failure'); END""")
        journal.db.commit()
        return receipt
    backend.move = loss_of_recording
    with pytest.raises(RuntimeError, match="중단 상태도 저장하지 못했습니다"):
        execute(plans, journal, backend)
    assert calls == [plans[0].candidate.path]
    assert Path(plans[1].candidate.path).is_dir()
    assert not Path(plans[0].candidate.path).exists()
    journal.close()
    journal = Journal(directory)
    assert {row[3] for row in journal.history()} == {"running", "pending"}
    # Remove the injected fault to model storage becoming writable again.
    journal.db.execute("DROP TRIGGER fixture_all_updates_fail")
    journal.db.commit()
    journal.recover()
    rows = {row[1]: row for row in journal.history()}
    assert rows[plans[0].candidate.path][3] == "unknown"
    assert rows[plans[1].candidate.path][3] == "cancelled"
    assert (tmp_path / "fake-bin" / Path(plans[0].candidate.path).parent.name).is_dir()
    journal.close()


def test_no_success_when_backend_result_uncertain(tmp_path):
    plans = project(tmp_path / "project")
    journal = Journal(tmp_path / "data")
    backend = FakeRecycle(tmp_path / "fake-bin")
    original_move = backend.move
    def uncertain(path, validate):
        original_move(path, validate)
        raise OSError("응답 유실")
    backend.move = uncertain
    execute([plans[0]], journal, backend)
    assert journal.history()[0][3] == "unknown"
    journal.close()


def test_empty_custom_subdirectory_blocks_cleanup(tmp_path):
    plans = project(tmp_path / "project")
    (Path(plans[0].candidate.path) / "personal-empty-folder").mkdir()
    result = scan(tmp_path / "project")
    with pytest.raises(ValueError, match="하위 폴더"):
        prepare(result, next(c for c in result.candidates if c.path == plans[0].candidate.path))


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows 파일 공유 잠금 시험")
def test_locked_file_is_recorded_as_failure_without_backend(tmp_path):
    import ctypes
    from ctypes import wintypes
    plans = project(tmp_path / "project")
    target = Path(plans[0].candidate.path)
    file = next(target.iterdir())
    original = file.read_bytes()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = create(str(file), 0x80000000, 0, None, 3, 0, None)
    assert handle != wintypes.HANDLE(-1).value
    called = []
    class Forbidden:
        def move(self, *_):
            called.append(True)
            raise AssertionError("잠금 대상에 도달하면 안 됨")
    journal = Journal(tmp_path / "data")
    try:
        execute([plans[0]], journal, Forbidden())
        assert journal.history()[0][3] == "failed"
        assert journal.history()[0][4]
        assert not called
    finally:
        kernel.CloseHandle(handle)
        journal.close()
    assert file.read_bytes() == original
