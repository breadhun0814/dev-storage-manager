"""Change only the DACL of an owned disposable folder, then restore it."""
import os
import pytest
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.scanning.listing import list_directory

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows ACL 시험")


def test_real_directory_read_denial_is_incomplete(tmp_path):
    import ntsecuritycon
    import pywintypes
    import win32api
    import win32con
    import win32security
    denied = tmp_path / "owned-denied-fixture"
    denied.mkdir()
    source = denied / "must-stay.txt"
    source.write_bytes(b"owned ACL fixture")
    before = scan(tmp_path)
    original = win32security.GetFileSecurity(str(denied), win32security.DACL_SECURITY_INFORMATION)
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        owner = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    everyone = win32security.CreateWellKnownSid(win32security.WinWorldSid, None)
    acl = win32security.ACL()
    acl.AddAccessDeniedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_LIST_DIRECTORY, everyone)
    acl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, owner)
    restricted = win32security.SECURITY_DESCRIPTOR()
    restricted.SetSecurityDescriptorDacl(True, acl, False)
    applied = False
    try:
        try:
            win32security.SetFileSecurity(str(denied), win32security.DACL_SECURITY_INFORMATION, restricted)
            applied = True
        except pywintypes.error as exc:
            pytest.skip("실행 환경이 임시 DACL 변경을 거부함: " + str(exc))
        result = scan(tmp_path)
        assert result.status == "incomplete", result.issues
        assert any(issue.path == str(denied) and issue.error for issue in result.issues)
        from dev_storage_manager.ui.folder_model import FolderModel
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        model = FolderModel()
        model.set_result(result)
        row = next(n for n, folder in enumerate(model.folders) if folder.path == str(denied))
        assert model.data(model.index(row, 1)) == "—"
        assert model.data(model.index(row, 4)) == "읽기 실패 · 불완전"
        with pytest.raises(OSError):
            list_directory(before, denied)
    finally:
        if applied:
            win32security.SetFileSecurity(str(denied), win32security.DACL_SECURITY_INFORMATION, original)
    assert source.read_bytes() == b"owned ACL fixture"
    assert source in list(denied.iterdir())
