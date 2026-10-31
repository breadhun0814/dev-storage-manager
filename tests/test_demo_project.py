import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import importlib.util
from pathlib import Path
import py_compile
from threading import Event

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from dev_storage_manager.demo.project import create_demo, DemoCreationError, SOURCE, CONFIG, GIT_SENTINEL
from dev_storage_manager.cleanup.service import prepare, execute
from dev_storage_manager.persistence.journal import Journal
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.platform.recycle import Receipt
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.ui.main_window import Window


def test_fresh_demo_is_real_detectable_and_matches_stdlib_pyc(tmp_path):
    personal = tmp_path / "기존 파일.txt"
    personal.write_bytes(b"keep")
    first = create_demo(tmp_path)
    second = create_demo(tmp_path)
    assert first != second and first.parent == tmp_path
    assert personal.read_bytes() == b"keep"
    assert (first / "demo_owned.py").read_bytes() == SOURCE
    assert (first / "pyproject.toml").read_bytes() == CONFIG
    assert (first / ".git/KEEP.txt").read_bytes() == GIT_SENTINEL
    result = scan(first)
    assert result.status == "complete" and result.files == 4
    assert len(result.candidates) == 1 and result.candidates[0].kind == "python-cache"
    candidate = result.candidates[0]
    plan = prepare(result, candidate)
    assert plan.proof
    cache = first / "__pycache__" / Path(importlib.util.cache_from_source("demo_owned.py")).name
    oracle = tmp_path / "oracle.pyc"
    py_compile.compile(str(first / "demo_owned.py"), cfile=str(oracle), dfile="demo_owned.py", doraise=True,
                       invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH, optimize=0)
    assert cache.read_bytes() == oracle.read_bytes()
    originals = {p: p.read_bytes() for p in (first / "demo_owned.py", first / "pyproject.toml", first / ".git/KEEP.txt")}
    class OwnedBackend:
        def move(self, path, validate):
            validate()
            destination = tmp_path / "fixture-bin"
            path.rename(destination)
            return Receipt(str(path), str(destination))
    journal = Journal(tmp_path / "data")
    execute([plan], journal, OwnedBackend())
    assert journal.history()[0][3] == "succeeded"
    journal.close()
    assert all(p.read_bytes() == data for p, data in originals.items())


def test_protected_git_and_cancelled_parents_are_not_written(tmp_path):
    protected = tmp_path / "protected"
    protected.mkdir()
    with pytest.raises(ValueError, match="보호"):
        create_demo(protected, protected=[protected])
    assert not list(protected.iterdir())
    git = tmp_path / ".git"
    git.mkdir()
    with pytest.raises(ValueError, match=".git"):
        create_demo(git)
    assert not list(git.iterdir())
    cancel = Event()
    cancel.set()
    before = list(tmp_path.iterdir())
    with pytest.raises(ValueError, match="취소"):
        create_demo(tmp_path, cancel)
    assert list(tmp_path.iterdir()) == before


def test_demo_compilation_analysis_and_proof_never_execute_source(tmp_path, monkeypatch):
    from dev_storage_manager.demo import project
    sentinel = b"raise RuntimeError('owned fixture must never execute')\n"
    monkeypatch.setattr(project, "SOURCE", sentinel)
    root = create_demo(tmp_path)
    assert (root / "demo_owned.py").read_bytes() == sentinel
    result = scan(root)
    assert prepare(result, result.candidates[0]).proof


def test_reparse_boundary_stops_before_creating_child(tmp_path, monkeypatch):
    from dev_storage_manager.demo import project
    monkeypatch.setattr(project, "is_link", lambda info: True)
    with pytest.raises(ValueError, match="reparse"):
        create_demo(tmp_path)
    assert not list(tmp_path.iterdir())


def test_partial_creation_does_not_remove_or_overwrite_files(tmp_path, monkeypatch):
    from dev_storage_manager.demo import project
    personal = tmp_path / "keep.txt"
    personal.write_bytes(b"personal fixture")
    actual_open = open
    def failure(path, mode):
        if str(path).endswith("demo_owned.py"):
            raise OSError("fixture write failure")
        return actual_open(path, mode)
    monkeypatch.setattr(project, "open", failure, raising=False)
    with pytest.raises(DemoCreationError, match="fixture write failure") as error:
        create_demo(tmp_path)
    assert error.value.root.is_dir()
    assert (error.value.root / "pyproject.toml").read_bytes() == CONFIG
    assert str(error.value.root) in str(error.value)
    assert personal.read_bytes() == b"personal fixture"


def test_cancel_after_first_write_leaves_only_new_partial_material(tmp_path, monkeypatch):
    from dev_storage_manager.demo import project
    event = Event()
    original_open = open
    class CancelWriter:
        def __init__(self, file):
            self.file = file
        def __enter__(self):
            return self
        def write(self, data):
            self.file.write(data)
            event.set()
        def __exit__(self, *args):
            self.file.close()
    def cancel_open(path, mode):
        return CancelWriter(original_open(path, mode))
    monkeypatch.setattr(project, "open", cancel_open, raising=False)
    with pytest.raises(DemoCreationError, match="취소") as error:
        create_demo(tmp_path, event)
    assert list(error.value.root.iterdir()) == [error.value.root / "pyproject.toml"]
    assert (error.value.root / "pyproject.toml").read_bytes() == CONFIG


def test_demo_ui_creates_registers_analyzes_without_selecting_or_approving(tmp_path, monkeypatch, wait_for_idle, wait_for_history):
    import dev_storage_manager.ui.main_window as ui
    app = QApplication.instance() or QApplication([])
    parent = tmp_path / "시험 공간"
    parent.mkdir()
    (parent / "keep.txt").write_bytes(b"existing fixture")
    window = Window(Store(tmp_path / "data"))
    monkeypatch.setattr(ui.QFileDialog, "getExistingDirectory", lambda *args: str(parent))
    window.start_demo_project()
    wait_for_idle(window, app)
    assert window.current_result.status == "complete"
    root = Path(window.current_result.root)
    assert root.parent == parent and window.selected() == str(root)
    assert window.candidates.topLevelItemCount() == 1 and window.candidates.currentItem() is None
    assert not window.cleanup_ready and not window.review_button.isEnabled()
    item = window.candidates.topLevelItem(0)
    assert item.data(0, Qt.ItemDataRole.UserRole).kind == "python-cache"
    window.candidates.setCurrentItem(item)
    window.start_review()
    wait_for_idle(window, app)
    assert not window.review_dialog.confirmed.isEnabled()
    assert not window.review_dialog.run_button.isEnabled()
    assert "환경" in window.review_dialog.conditions.toPlainText() or "정리 실행 전" in window.review_dialog.conditions.toPlainText()
    window.review_dialog.reject()
    assert (parent / "keep.txt").read_bytes() == b"existing fixture"
    assert (root / ".git/KEEP.txt").read_bytes() == GIT_SENTINEL
    wait_for_history(window, app)
    window.close()
