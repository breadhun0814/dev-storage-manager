"""Read-only cleanup review. This module cannot move or delete files."""
from dataclasses import dataclass
import os
import stat
from pathlib import Path
from threading import Event

from dev_storage_manager.domain.models import Result, Candidate
from dev_storage_manager.scanning.scanner import scan, is_link, within
from dev_storage_manager.platform.guard import directory_guard


@dataclass
class IncludedFile:
    path: str
    size: int


@dataclass
class Review:
    root: str
    candidate: Candidate
    files: list[IncludedFile]
    signature: str
    blocked: list[str]


def inspect(result: Result, candidate: Candidate, cancel: Event | None = None,
            progress=None, protected=None) -> Review:
    cancel = cancel or Event()
    root, target = Path(result.root), Path(candidate.path)
    if not within(target, root) or target == root:
        raise ValueError("프로젝트 내부의 하위 후보만 검토할 수 있습니다.")
    saved = next((f for f in result.folders if f.path == candidate.path), None)
    if not saved or candidate not in result.candidates:
        raise ValueError("분석 결과에 없는 후보입니다.")
    blocked = []
    if result.status != "complete":
        blocked.append("완료된 전체 분석이 필요합니다. 취소/불완전 결과는 정리에 사용할 수 없습니다.")
    if any(within(Path(i.path), target) or within(target, Path(i.path)) for i in result.issues):
        blocked.append("후보 내부 또는 상위 경로에 제외/오류가 있습니다.")
    current = scan(target, cancel, progress, protected)
    if current.status != "complete" or current.issues:
        blocked.append("현재 후보를 완전하게 읽지 못했거나 링크/보호 항목이 있습니다.")
    signature = current.folders[0].signature
    if not saved.signature or signature != saved.signature:
        blocked.append("분석 이후 대상 식별 정보 또는 내용 목록이 변경되었습니다. 다시 분석하세요.")
    included = []
    # Enumerate only already-scanned directories; recheck entries and boundary.
    for folder in current.folders:
        if cancel.is_set():
            blocked.append("검토가 취소되었습니다.")
            break
        path = Path(folder.path)
        try:
            if is_link(path.lstat()):
                blocked.append("검토 중 디렉터리가 링크로 변경되었습니다.")
                continue
            with directory_guard(path), os.scandir(path) as entries:
                for entry in entries:
                    if cancel.is_set():
                        break
                    info = entry.stat(follow_symlinks=False)
                    if is_link(info):
                        blocked.append("링크/reparse point가 포함되어 있습니다.")
                    elif stat.S_ISREG(info.st_mode):
                        included.append(IncludedFile(entry.path, info.st_size))
        except OSError as exc:
            blocked.append(f"포함 항목 확인 실패: {path}: {exc}")
    if cancel.is_set():
        blocked.append("검토가 취소되었습니다.")
    # Ensure enumeration has not changed metadata during review.
    if not cancel.is_set():
        after = scan(target, cancel, progress, protected)
        if after.status != "complete" or after.issues or after.folders[0].signature != signature:
            blocked.append("검토 중 대상이 변경되었거나 읽기 오류가 발생했습니다.")
    if not candidate.cleanup_supported:
        blocked.append("이 유형의 휴지통 이동은 아직 검증되지 않아 실행을 지원하지 않습니다.")
    return Review(str(root), candidate, sorted(included, key=lambda f: f.path), signature,
                  list(dict.fromkeys(blocked)))


def deduplicate_paths(paths: list[str]) -> list[str]:
    selected: list[Path] = []
    for path in sorted({Path(os.path.abspath(p)) for p in paths}, key=lambda p: len(p.parts)):
        if not any(within(path, parent) for parent in selected):
            selected.append(path)
    return [str(p) for p in selected]
