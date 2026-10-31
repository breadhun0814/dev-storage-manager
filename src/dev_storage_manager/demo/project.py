"""Create one fresh demonstration directory with exclusive, guarded writes."""
import importlib.util
import marshal
import os
from pathlib import Path
import struct
import tempfile
from threading import Event

from dev_storage_manager.i18n import tr
from dev_storage_manager.platform.guard import directory_guard
from dev_storage_manager.platform.paths import protected_paths
from dev_storage_manager.platform.path_safety import normalized, native
from dev_storage_manager.scanning.scanner import is_link, within

SOURCE = b"# Generated storage-manager demonstration. Never executed.\nVALUE = 42\n"
CONFIG = b'[project]\nname = "dev-storage-manager-demo"\nversion = "0.0.0"\n'
GIT_SENTINEL = b"Owned demonstration protection marker; not a real Git repository.\n"


class DemoCreationError(RuntimeError):
    def __init__(self, root, reason):
        self.root = root
        super().__init__(tr("시험 자료 생성을 완료하지 못했습니다: {reason}\n생성한 새 폴더: {path}\n남은 시험 자료는 자동 삭제하지 않습니다. 위치를 확인하세요.").format(reason=reason, path=root))


def create_demo(parent, cancel=None, protected=None):
    parent = normalized(parent)
    cancel = cancel or Event()
    protected = [normalized(p) for p in (protected_paths() if protected is None else protected)]
    if parent == Path(parent.anchor) or any(p.casefold() == ".git" for p in parent.parts):
        raise ValueError(tr("드라이브 루트나 .git 내부에는 시험 자료를 만들 수 없습니다."))
    if any(within(parent, p) for p in protected):
        raise ValueError(tr("앱 데이터·실행 환경·시스템 보호 폴더 밖의 시험 위치를 선택하세요."))
    for part in [*reversed(parent.parents), parent]:
        if is_link(os.lstat(native(part))):
            raise ValueError(tr("링크/reparse point가 포함된 위치에는 시험 자료를 만들 수 없습니다."))
    if cancel.is_set():
        raise ValueError(tr("시험 자료 생성이 취소되었습니다."))
    root = None
    try:
        with directory_guard(parent):
            root = normalized(tempfile.mkdtemp(prefix="DevStorageManager-시험-", dir=native(parent)))
            with directory_guard(root):
                def write(name, data):
                    if cancel.is_set():
                        raise ValueError(tr("시험 자료 생성이 취소되었습니다."))
                    with open(native(root / name), "xb") as file:
                        file.write(data)
                write("pyproject.toml", CONFIG)
                write("demo_owned.py", SOURCE)
                guide = tr("앱이 만든 시험 프로젝트입니다. 기존 프로젝트 파일은 복사하지 않았습니다.\n이 폴더의 __pycache__는 포함 파일 검토를 익히기 위한 정리 후보입니다.\n원본 demo_owned.py와 pyproject.toml, .git/KEEP.txt는 정리 대상이 아닙니다.\n정리는 일반 프로젝트와 같은 환경 시험·내용 검증·직접 확인을 통과해야 합니다.\n이 프로그램은 원본을 실행하거나 재설치 명령을 자동 실행하지 않습니다.\n휴지통 이동 후에는 결과와 이력을 확인하고 다시 분석하세요.\n복원은 Windows 휴지통에서 직접 하며 앱은 자동 복원/비우기를 제공하지 않습니다.\n시험 폴더를 목록에서 제거해도 실제 폴더는 남습니다.\n")
                write("시험 안내.txt", guide.encode("utf-8"))
                (root / ".git").mkdir()
                with directory_guard(root / ".git"):
                    write(".git/KEEP.txt", GIT_SENTINEL)
                (root / "__pycache__").mkdir()
                # PEP 552 checked-hash pyc. Only the app's fixed bytes are
                # compiled; no code object or user source is executed/loaded.
                code = compile(SOURCE, "demo_owned.py", "exec", dont_inherit=True, optimize=0)
                data = importlib.util.MAGIC_NUMBER + struct.pack("<I", 3) + importlib.util.source_hash(SOURCE) + marshal.dumps(code)
                cache_name = Path(importlib.util.cache_from_source("demo_owned.py")).name
                with directory_guard(root / "__pycache__"):
                    write("__pycache__/" + cache_name, data)
                if cancel.is_set():
                    raise ValueError(tr("시험 자료 생성이 취소되었습니다."))
        return root
    except Exception as exc:
        if root is not None:
            raise DemoCreationError(root, str(exc)) from exc
        raise
