"""Strict Windows recycle-only adapter using Send2Trash's COM sink base.

Unlike the library's compatibility dispatcher, no legacy/permanent-delete path
is available. UI execution requires session qualification and per-target review.
"""
from dev_storage_manager.i18n import tr
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from dev_storage_manager.platform.path_safety import native

# sherrors.h: COPYENGINE_S_DONT_PROCESS_CHILDREN is a success/informational
# result used when the directory itself was recycled. Do not accept every
# positive HRESULT: pending/ignored statuses do not prove a completed move.
RECYCLED_ITEM_RESULTS = frozenset({0, 0x00270008})


@dataclass
class Receipt:
    path: str
    destination: str


class WindowsRecycle:
    def move(self, path: Path, validate):
        if os.name != "nt" or sys.getwindowsversion().major < 10:
            raise RuntimeError(tr('이 휴지통 연동은 Windows 10 이상 전용이며 현재 Windows 10 지원은 미검증입니다.'))
        import ctypes
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(Path(path.anchor)))
        if drive_type != 3 or str(path).startswith("\\\\"):
            raise ValueError(tr('정리는 로컬 고정 드라이브에서만 지원합니다. 네트워크/이동식 드라이브는 미지원입니다.'))
        import pythoncom
        from win32com.shell import shell, shellcon
        from send2trash.win.IFileOperationProgressSink import FileOperationProgressSink
        from win32com.server.exception import COMException

        expected = os.path.normcase(os.path.abspath(path))
        receipts = []
        failures = []

        class Sink(FileOperationProgressSink):
            def PreDeleteItem(self, flags, item):
                actual = os.path.normcase(os.path.abspath(item.GetDisplayName(0x80058000))) # SIGDN_FILESYSPATH
                if actual != expected or not flags & shellcon.TSF_DELETE_RECYCLE_IF_POSSIBLE:
                    message = tr('휴지통 이동으로 확인되지 않은 작업 차단: flags={p0:#x}, path={p1}, expected={p2}').format(p0=flags, p1=actual, p2=expected)
                    failures.append(message)
                    raise COMException(desc=message, scode=-2147467260)
                try:
                    validate()
                except Exception as exc:
                    failures.append(str(exc))
                    raise COMException(desc=str(exc), scode=-2147467260) from exc
                return 0

            def PostDeleteItem(self, flags, item, result, newly_created):
                actual = os.path.normcase(os.path.abspath(item.GetDisplayName(0x80058000)))
                if actual != expected or not flags & shellcon.TSF_DELETE_RECYCLE_IF_POSSIBLE or (result & 0xFFFFFFFF) not in RECYCLED_ITEM_RESULTS or not newly_created:
                    failures.append(tr('휴지통 이동 결과를 확인하지 못했습니다: ') +
                                    f"flags={flags:#x}, result={result & 0xFFFFFFFF:#x}, receipt={bool(newly_created)}, path={actual}")
                    return -2147467260
                receipts.append(Receipt(str(path), newly_created.GetDisplayName(0x80058000)))
                return 0

        pythoncom.CoInitialize()
        try:
            operation = pythoncom.CoCreateInstance(shell.CLSID_FileOperation, None,
                                                    pythoncom.CLSCTX_ALL, shell.IID_IFileOperation)
            # FOFX_RECYCLEONDELETE | FOFX_ADDUNDORECORD | FOFX_EARLYFAILURE,
            # and no UI or confirmation dialogs. Never fall back to DeleteFile.
            operation.SetOperationFlags(0x00080000 | 0x20000000 | shellcon.FOFX_EARLYFAILURE |
                                         shellcon.FOF_NOCONFIRMATION | shellcon.FOF_NOERRORUI | shellcon.FOF_SILENT)
            sink = pythoncom.WrapObject(Sink(), shell.IID_IFileOperationProgressSink)
            item = shell.SHCreateItemFromParsingName(str(path), None, shell.IID_IShellItem)
            operation.DeleteItem(item, sink)
            try:
                result = operation.PerformOperations()
            except Exception as exc:
                raise OSError("; ".join(failures) or str(exc)) from exc
            if failures or result or operation.GetAnyOperationsAborted() or len(receipts) != 1:
                raise OSError(tr('휴지통 작업 실패/취소 또는 결과 미확정') + (": " + "; ".join(failures) if failures else ""))
            if os.path.lexists(native(path)):
                raise OSError(tr('원래 경로가 남아 있어 성공으로 처리할 수 없습니다.'))
            return receipts[0]
        finally:
            pythoncom.CoUninitialize()
