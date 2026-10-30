import os
from pathlib import Path
from threading import Event

import pytest

from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.persistence.store import Store


def test_read_only_nested_unicode_and_git(tmp_path):
    root = tmp_path / "한글 프로젝트"
    child = root / "src" / "중첩"
    child.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / ".git" / "secret").write_bytes(b"protected")
    (root / "source.py").write_bytes(b"123")
    (child / "file.txt").write_bytes(b"45678")
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    result = scan(root)
    assert result.size == 8 and result.files == 2
    assert next(f for f in result.folders if f.path == str(root)).size == 8
    assert result.issues and result.status == "complete"
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}


def test_cancel(tmp_path):
    event = Event()
    event.set()
    result = scan(tmp_path, event)
    assert result.status == "cancelled"


def test_cancel_during_scan(tmp_path):
    for n in range(20):
        (tmp_path / str(n)).write_bytes(b"x")
    event = Event()
    result = scan(tmp_path, event, lambda *_: event.set())
    assert result.status == "cancelled" and result.files < 20


def test_protected(tmp_path):
    protected = tmp_path / "app"
    protected.mkdir()
    (protected / "db").write_bytes(b"secret")
    assert scan(tmp_path, protected=[protected]).size == 0
    with pytest.raises(ValueError):
        scan(protected, protected=[protected])


def test_read_failure_is_incomplete(tmp_path, monkeypatch):
    original = os.scandir
    child = tmp_path / "denied"
    child.mkdir()
    def denied(path):
        if Path(path) == child:
            raise PermissionError("시험 접근 거부")
        return original(path)
    monkeypatch.setattr(os, "scandir", denied)
    result = scan(tmp_path)
    assert result.status == "incomplete"
    assert result.issues[0].error


def test_symlink_boundary(tmp_path):
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "private").write_bytes(b"secret")
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS가 비관리자 심볼릭 링크 생성을 허용하지 않음")
    result = scan(root)
    assert result.size == 0 and result.issues
    with pytest.raises(ValueError):
        scan(root / "link")


def test_reparse_flag():
    from types import SimpleNamespace
    from dev_storage_manager.scanning.scanner import is_link
    assert is_link(SimpleNamespace(st_mode=0, st_file_attributes=0x400))


def test_git_root_rejected(tmp_path):
    root = tmp_path / ".git" / "objects"
    root.mkdir(parents=True)
    with pytest.raises(ValueError):
        scan(root)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction 시험")
def test_windows_junction_boundary(tmp_path):
    import subprocess
    root, outside = tmp_path / "project", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "private").write_bytes(b"secret")
    link = root / "junction"
    completed = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(outside)],
                               capture_output=True)
    if completed.returncode != 0:
        pytest.skip("실행 환경에서 junction 생성 거부: " + repr(completed.stderr))
    try:
        result = scan(root)
        assert result.size == 0 and result.issues
        with pytest.raises(ValueError):
            scan(link)
    finally:
        # Remove only the temporary junction entry, never its target.
        os.rmdir(link)


def test_store_restart_and_cancel(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    store = Store(tmp_path / "data")
    store.add(str(project))
    event = Event()
    event.set()
    store.save(scan(project, event))
    assert store.load(str(project)).status == "cancelled"
    store.status(str(project), "running")
    store.close()
    store = Store(tmp_path / "data")
    assert store.projects()[0][2] == "interrupted"
    store.remove(str(project))
    assert project.exists()
    store.close()
