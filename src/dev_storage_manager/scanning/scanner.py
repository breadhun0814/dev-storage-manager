"""Read metadata only; never follow symbolic links or Windows reparse points."""
from dev_storage_manager.i18n import tr
import os
import stat
import time
import heapq
from pathlib import Path
from threading import Event
from collections.abc import Callable
from datetime import datetime, timezone

from dev_storage_manager.domain.models import Folder, Issue, Result, FileSummary
from dev_storage_manager.detection.rules import Evidence, classify
from dev_storage_manager.scanning.fingerprint import identity, signature
from dev_storage_manager.platform.guard import directory_guard
from dev_storage_manager.platform.path_safety import normalized, native


def is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400
    )


def within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def scan(root: Path, cancel: Event | None = None,
         progress: Callable[[int, int, str], None] | None = None,
         protected: list[Path] | None = None, exclusions: list[str] | None = None) -> Result:
    root = normalized(root)
    cancel = cancel or Event()
    protected = [normalized(p) for p in (protected or [])]
    # Validate every ancestor without resolve(), which would follow a junction.
    for p in [*reversed(root.parents), root]:
        if p.name.casefold() == ".git":
            raise ValueError(tr('.git 내부는 분석할 수 없습니다.'))
        root_info = os.lstat(native(p))
        if is_link(root_info):
            raise ValueError(tr('링크 또는 reparse point를 포함한 경로는 등록할 수 없습니다.'))
    if root == Path(root.anchor) or not stat.S_ISDIR(root_info.st_mode):
        raise ValueError(tr('드라이브 루트가 아닌 프로젝트 폴더를 선택하세요.'))
    if any(within(root, p) for p in protected):
        raise ValueError(tr('앱 데이터·실행 환경·시스템 보호 경로는 분석할 수 없습니다.'))
    result = Result(str(root), file_sample_available=True)
    largest_files = []
    started = time.perf_counter()
    result.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    excluded = []
    for value in exclusions or []:
        item = Path(value)
        if item.is_absolute() or item.anchor or ".." in item.parts or not item.parts:
            raise ValueError(tr('제외 경로는 프로젝트 내부 상대 경로여야 합니다.'))
        excluded.append(root / item)
    result.exclusions = list(exclusions or [])
    evidence = Evidence()
    rows: dict[Path, Folder] = {root: Folder(str(root))}
    own: dict[Path, tuple] = {}
    direct_signatures: dict[Path, str] = {}
    children_by_dir: dict[Path, list[tuple]] = {}
    stack = [root]
    last_report = 0.0
    while stack:
        if cancel.is_set():
            result.status = "cancelled"
            break
        current = stack.pop()
        current_entries = []
        try:
            current_info = os.lstat(native(current))
            own[current] = identity(current_info)
            if is_link(current_info):
                result.issues.append(Issue(str(current), tr('탐색 전 링크로 변경되어 제외')))
                continue
            with directory_guard(current), os.scandir(native(current)) as entries:
                for entry in entries:
                    if cancel.is_set():
                        result.status = "cancelled"
                        break
                    path = normalized(entry.path)
                    if any(within(path, p) for p in excluded):
                        result.issues.append(Issue(str(path), tr('사용자 제외 목록')))
                        continue
                    if entry.name.casefold() == ".git" or any(within(path, p) for p in protected):
                        result.issues.append(Issue(str(path), tr('보호 경로 제외')))
                        continue
                    try:
                        info = entry.stat(follow_symlinks=False)
                        # Windows directory enumeration may return stale child
                        # directory timestamps. Its full identity is included by
                        # the child's own lstat + subtree signature instead.
                        is_directory = stat.S_ISDIR(info.st_mode) and not is_link(info)
                        current_entries.append((entry.name, ("directory",) if is_directory else identity(info)))
                        if is_link(info):
                            result.issues.append(Issue(str(path), tr('링크/reparse point 제외')))
                        elif stat.S_ISDIR(info.st_mode):
                            rows[path] = Folder(str(path))
                            stack.append(path)
                        elif stat.S_ISREG(info.st_mode):
                            evidence.file(current, entry.name)
                            rows[current].size += info.st_size
                            rows[current].files += 1
                            result.size += info.st_size
                            result.files += 1
                            item = (info.st_size, str(path))
                            if len(largest_files) < result.file_sample_limit:
                                heapq.heappush(largest_files, item)
                            elif item > largest_files[0]:
                                heapq.heapreplace(largest_files, item)
                        else:
                            result.issues.append(Issue(str(path), tr('일반 파일이 아닌 항목 제외')))
                    except OSError as exc:
                        result.issues.append(Issue(str(path), str(exc), True))
                    now = time.monotonic()
                    if progress and now - last_report >= 0.15:
                        progress(result.files, result.size, str(current))
                        last_report = now
        except OSError as exc:
            result.issues.append(Issue(str(current), str(exc), True))
        direct_signatures[current] = signature(own.get(current, ()), current_entries, [])
        evidence.finish_directory(current, current / "__pycache__" in rows)
    for path in sorted(rows, key=lambda p: len(p.parts), reverse=True):
        rows[path].signature = signature((), [("direct", direct_signatures.get(path, "unvisited"))],
                                         children_by_dir.get(path, []))
        if path != root:
            children_by_dir.setdefault(path.parent, []).append((path.name, rows[path].signature))
            rows[path.parent].size += rows[path].size
            rows[path.parent].files += rows[path].files
    result.folders = list(rows.values())
    result.largest_files = [FileSummary(path, size) for size, path in sorted(largest_files, reverse=True)]
    classify(result, evidence)
    if result.status != "cancelled" and any(i.error for i in result.issues):
        result.status = "incomplete"
    result.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result.elapsed_seconds = time.perf_counter() - started
    return result
