import json
import pytest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from dev_storage_manager.cleanup import capability as module
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.ui.main_window import Window


@pytest.mark.parametrize("move_success", [False, True])
def test_junction_failure_still_diagnoses_owned_cache_but_cannot_approve(tmp_path, monkeypatch, move_success):
    import subprocess
    seen = []
    class Denied:
        def move(self, path, validate):
            validate()
            seen.append(path)
            assert path.name in {"__pycache__", ".pytest_cache"} and path.is_relative_to(tmp_path)
            if move_success:
                # Owned-path rename is a backend double, never a recycle claim.
                from dev_storage_manager.platform.recycle import Receipt
                receipt = path.with_name("fake-receipt-cache")
                path.rename(receipt)
                return Receipt(str(path), str(receipt))
            raise OSError("fixture: missing recycle flag")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stderr=b"fixture denied"))
    monkeypatch.setattr(module, "WindowsRecycle", Denied)
    phases = []
    result = module.qualify(tmp_path, progress=phases.append)
    assert not result.ready and not result.qualified_kinds and len(phases) == 5 and len(seen) == 2
    assert [(c.code, c.status) for c in result.checks] == [
        ("boundary", "failed"), ("protection", "passed"), ("recycle", "passed" if move_success else "failed"), ("preservation", "passed"),
        ("pytest-recycle", "passed" if move_success else "failed")]
    if not move_success:
        assert "missing recycle flag" in result.reason
    assert (Path(result.fixture) / "project/fixture.py").read_bytes() == b"qualification_fixture = 42\n"
    loaded = module.load_report(tmp_path)
    assert not loaded.ready and not loaded.qualified_kinds and len(loaded.checks) == 5


def test_saved_success_never_grants_new_session_approval_and_ui_shows_report(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "data")
    base = store.directory / "environment-tests"
    base.mkdir()
    (base / "last-result.json").write_text(json.dumps({
        "ready_in_that_session": True, "reason": "previous fixture success",
        "checks": [{"code": "recycle", "label": "fixture recycle", "status": "passed", "detail": "previous receipt"}]
    }), encoding="utf-8")
    window = Window(store)
    assert not window.cleanup_ready
    assert window.last_capability is not None and not window.last_capability.ready
    window.show_environment_report()
    assert "부분 통과" in window.environment_dialog.windowTitle()
    window.environment_dialog.reject()
    window.close()


def test_cancelled_check_does_not_start_shell_or_backend(tmp_path, monkeypatch):
    import subprocess
    def unexpected(*a, **k):
        raise AssertionError("Cancelled check must not start any operation")
    monkeypatch.setattr(subprocess, "run", unexpected)
    monkeypatch.setattr(module, "WindowsRecycle", unexpected)
    cancel = Event()
    cancel.set()
    result = module.qualify(tmp_path, cancel)
    assert not result.ready and not result.fixture


def test_invalid_or_oversize_report_is_ignored(tmp_path):
    path = tmp_path / "last-result.json"
    for data in (b"invalid", b"[]", b" " * (512 * 1024 + 1)):
        path.write_bytes(data)
        assert module.load_report(tmp_path) is None
