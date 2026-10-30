"""Read metadata only; never follow symbolic links or Windows reparse points."""
import os
import stat
import time
from pathlib import Path
from threading import Event
from collections.abc import Callable

from dev_storage_manager.domain.models import Folder, Issue, Result
from dev_storage_manager.detection.rules import Evidence, classify
from dev_storage_manager.scanning.fingerprint import identity, signature
from dev_storage_manager.platform.guard import directory_guard


def is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400
    )


def within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def scan(root: Path, cancel: Event | None = None,
         progress: Callable[[int, int, str], None] | None = None,
         protected: list[Path] | None = None, exclusions: list[str] | None = None) -> Result:
    root = Path(os.path.abspath(root))
    cancel = cancel or Event()
    protected = [Path(os.path.abspath(p)) for p in (protected or [])]
    # Validate every ancestor without resolve(), which would follow a junction.
    for p in [*reversed(root.parents), root]:
        if p.name.casefold() == ".git":
            raise ValueError(".git 내부는 분석할 수 없습니다.")
        if is_link(p.lstat()):
            raise ValueError("링크 또는 reparse point를 포함한 경로는 등록할 수 없습니다.")
    if root == Path(root.anchor) or not root.is_dir():
        raise ValueError("드라이브 루트가 아닌 프로젝트 폴더를 선택하세요.")
    if any(within(root, p) for p in protected):
        raise ValueError("앱 데이터·실행 환경·시스템 보호 경로는 분석할 수 없습니다.")
    result = Result(str(root))
    excluded = []
    for value in exclusions or []:
        item = Path(value)
        if item.is_absolute() or item.anchor or ".." in item.parts or not item.parts:
            raise ValueError("제외 경로는 프로젝트 내부 상대 경로여야 합니다.")
        excluded.append(root / item)
    result.exclusions = list(exclusions or [])
    evidence = Evidence()
    rows: dict[Path, Folder] = {root: Folder(str(root))}
    own: dict[Path, tuple] = {}
    entries_by_dir: dict[Path, list[tuple]] = {}
    children_by_dir: dict[Path, list[tuple]] = {}
    stack = [root]
    last_report = 0.0
    while stack:
        if cancel.is_set():
            result.status = "cancelled"
            break
        current = stack.pop()
        entries_by_dir[current] = []
        try:
            current_info = current.lstat()
            own[current] = identity(current_info)
            if is_link(current_info):
                result.issues.append(Issue(str(current), "탐색 전 링크로 변경되어 제외"))
                continue
            with directory_guard(current), os.scandir(current) as entries:
                for entry in entries:
                    if cancel.is_set():
                        result.status = "cancelled"
                        break
                    path = Path(entry.path)
                    if any(within(path, p) for p in excluded):
                        result.issues.append(Issue(str(path), "사용자 제외 목록"))
                        continue
                    if entry.name.casefold() == ".git" or any(within(path, p) for p in protected):
                        result.issues.append(Issue(str(path), "보호 경로 제외"))
                        continue
                    try:
                        info = entry.stat(follow_symlinks=False)
                        entries_by_dir[current].append((entry.name, identity(info)))
                        if is_link(info):
                            result.issues.append(Issue(str(path), "링크/reparse point 제외"))
                        elif stat.S_ISDIR(info.st_mode):
                            rows[path] = Folder(str(path))
                            stack.append(path)
                        elif stat.S_ISREG(info.st_mode):
                            evidence.file(current, entry.name)
                            rows[current].size += info.st_size
                            rows[current].files += 1
                            result.size += info.st_size
                            result.files += 1
                        else:
                            result.issues.append(Issue(str(path), "일반 파일이 아닌 항목 제외"))
                    except OSError as exc:
                        result.issues.append(Issue(str(path), str(exc), True))
                    now = time.monotonic()
                    if progress and now - last_report >= 0.15:
                        progress(result.files, result.size, str(current))
                        last_report = now
        except OSError as exc:
            result.issues.append(Issue(str(current), str(exc), True))
    for path in sorted(rows, key=lambda p: len(p.parts), reverse=True):
        rows[path].signature = signature(own.get(path, ()), entries_by_dir.get(path, []),
                                         children_by_dir.get(path, []))
        if path != root:
            children_by_dir.setdefault(path.parent, []).append((path.name, rows[path].signature))
            rows[path.parent].size += rows[path].size
            rows[path.parent].files += rows[path].files
    result.folders = list(rows.values())
    classify(result, evidence)
    if result.status != "cancelled" and any(i.error for i in result.issues):
        result.status = "incomplete"
    return result
