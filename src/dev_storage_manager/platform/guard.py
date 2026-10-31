"""Windows directory handles prevent ancestor rename while enumerating a path.

No file contents are read. Every component is opened without following reparse
points and checked against its expected final path before traversal starts.
"""
from dev_storage_manager.i18n import tr
from contextlib import contextmanager
import os
from pathlib import Path
from dev_storage_manager.platform.path_safety import native


@contextmanager
def directory_guard(path: Path):
    if os.name != "nt":
        yield
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    get_attributes = kernel.GetFileInformationByHandleEx
    get_attributes.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    get_attributes.restype = wintypes.BOOL
    final_path = kernel.GetFinalPathNameByHandleW
    final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    final_path.restype = wintypes.DWORD
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL

    class AttributeTag(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]

    handles = []
    try:
        for part in [*reversed(path.parents), path]:
            # FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES, share READ|WRITE (deny DELETE), OPEN_EXISTING,
            # BACKUP_SEMANTICS | OPEN_REPARSE_POINT.
            handle = create(native(part), 0x81, 0x3, None, 3, 0x02200000, None)
            if handle == wintypes.HANDLE(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
            attributes = AttributeTag()
            if not get_attributes(handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes)):
                raise ctypes.WinError(ctypes.get_last_error())
            if attributes.attributes & 0x400:
                raise OSError(tr('링크/reparse point 경로는 탐색할 수 없습니다: ') + str(part))
            buffer = ctypes.create_unicode_buffer(32768)
            length = final_path(handle, buffer, len(buffer), 0)
            if not length or length >= len(buffer):
                raise OSError(tr('실제 경로 확인 실패: ') + str(part))
            actual = buffer.value
            if actual.startswith("\\\\?\\UNC\\"):
                actual = "\\\\" + actual[8:]
            elif actual.startswith("\\\\?\\"):
                actual = actual[4:]
            if os.path.normcase(os.path.normpath(actual)) != os.path.normcase(os.path.normpath(str(part))):
                raise OSError(tr('실제 경로가 요청 경로와 다릅니다: ') + str(part))
        yield
    finally:
        for handle in reversed(handles):
            close(handle)
