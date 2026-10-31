"""COM protocol doubles only: never call the real Shell delete operation."""
import os
import sys
from types import SimpleNamespace
import pytest
from dev_storage_manager.platform.recycle import WindowsRecycle

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows 어댑터 시험")


def install_com(monkeypatch, path, flags=0x80, ignore_callback_error=False, post_flags=None,
                post_result=0, has_receipt=True, simulate_move=False, aborted=False):
    class Item:
        def __init__(self, value): self.value = value
        def GetDisplayName(self, _kind): return str(self.value)
    class Operation:
        def SetOperationFlags(self, value): self.options = value
        def DeleteItem(self, item, sink): self.item, self.sink = item, sink
        def PerformOperations(self):
            try:
                self.sink.PreDeleteItem(flags, self.item)
            except Exception:
                if not ignore_callback_error: raise
            if simulate_move:
                # Owned-fixture rename is a Shell protocol double, not a bin test.
                path.rename(path.parent / "fake-bin")
            # Deliberately emulate a misbehaving Shell that reports success
            # despite a failed callback; adapter must retain the veto.
            self.sink.PostDeleteItem(flags if post_flags is None else post_flags,
                                     self.item, post_result, Item(path.parent / "fake-bin") if has_receipt else None)
            return 0
        def GetAnyOperationsAborted(self): return aborted
    operation = Operation()
    shell = SimpleNamespace(CLSID_FileOperation=1, IID_IFileOperation=2, IID_IShellItem=4,
                            IID_IFileOperationProgressSink=3,
                            SHCreateItemFromParsingName=lambda value, *_: Item(value))
    shellcon = SimpleNamespace(TSF_DELETE_RECYCLE_IF_POSSIBLE=0x80,
                              FOFX_EARLYFAILURE=0x100000, FOF_NOCONFIRMATION=0x10,
                              FOF_NOERRORUI=0x400, FOF_SILENT=4)
    monkeypatch.setitem(sys.modules, "pythoncom", SimpleNamespace(
        CoInitialize=lambda: None, CoUninitialize=lambda: None, CLSCTX_ALL=23,
        CoCreateInstance=lambda *_: operation, WrapObject=lambda sink, *_: sink))
    monkeypatch.setitem(sys.modules, "win32com.shell", SimpleNamespace(shell=shell, shellcon=shellcon))
    monkeypatch.setitem(sys.modules, "win32com.server.exception", SimpleNamespace(
        COMException=lambda **kwargs: RuntimeError(kwargs["desc"])))
    monkeypatch.setitem(sys.modules, "send2trash.win.IFileOperationProgressSink", SimpleNamespace(
        FileOperationProgressSink=object))
    return operation


def test_missing_recycle_flag_blocks_before_validation(tmp_path, monkeypatch):
    target = tmp_path / "fixture"
    target.mkdir()
    install_com(monkeypatch, target, flags=0x202)
    validated = []
    with pytest.raises(OSError):
        WindowsRecycle().move(target, lambda: validated.append(True))
    assert not validated and target.is_dir()


def test_ignored_callback_veto_cannot_become_success(tmp_path, monkeypatch):
    target = tmp_path / "fixture"
    target.mkdir()
    install_com(monkeypatch, target, ignore_callback_error=True)
    def veto(): raise ValueError("fixture changed")
    with pytest.raises(OSError):
        WindowsRecycle().move(target, veto)
    assert target.is_dir()


@pytest.mark.parametrize("result", [0, 0x00270008])
def test_completed_folder_move_accepts_documented_status_with_all_proofs(tmp_path, monkeypatch, result):
    target = tmp_path / "fixture"
    target.mkdir()
    (target / "owned-cache").write_bytes(b"fixture content")
    install_com(monkeypatch, target, flags=0x282, post_result=result, simulate_move=True)
    validated = []
    receipt = WindowsRecycle().move(target, lambda: validated.append(True))
    assert validated == [True]
    assert receipt.destination == str(tmp_path / "fake-bin")
    assert not target.exists()
    assert (tmp_path / "fake-bin/owned-cache").read_bytes() == b"fixture content"


@pytest.mark.parametrize("result", [0x80004004, -2147467260, 0x0027000B, 0x00270005, 0x12345])
def test_pending_ignored_unknown_and_failed_results_are_not_completion(tmp_path, monkeypatch, result):
    target = tmp_path / "fixture"
    target.mkdir()
    install_com(monkeypatch, target, flags=0x282, post_result=result)
    with pytest.raises(OSError):
        WindowsRecycle().move(target, lambda: None)
    assert target.is_dir()


@pytest.mark.parametrize("has_receipt, simulate_move, aborted", [(False, False, False), (True, False, False), (True, True, True)])
def test_informational_status_alone_never_proves_success(tmp_path, monkeypatch, has_receipt, simulate_move, aborted):
    target = tmp_path / "fixture"
    target.mkdir()
    install_com(monkeypatch, target, flags=0x282, post_result=0x00270008,
                has_receipt=has_receipt, simulate_move=simulate_move, aborted=aborted)
    with pytest.raises(OSError):
        WindowsRecycle().move(target, lambda: None)


def test_postdelete_without_recycle_flag_cannot_become_success(tmp_path, monkeypatch):
    target = tmp_path / "fixture"
    target.mkdir()
    install_com(monkeypatch, target, post_flags=0x202)
    with pytest.raises(OSError, match="flags=0x202"):
        WindowsRecycle().move(target, lambda: None)
    assert target.is_dir()
