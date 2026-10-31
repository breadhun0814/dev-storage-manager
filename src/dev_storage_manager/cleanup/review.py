"""Read-only cleanup review. This module cannot move or delete files."""
from dev_storage_manager.i18n import tr
from dataclasses import dataclass, field
import os
import stat
from pathlib import Path
from threading import Event

from dev_storage_manager.domain.models import Result, Candidate
from dev_storage_manager.scanning.scanner import scan, is_link, within
from dev_storage_manager.platform.guard import directory_guard
from dev_storage_manager.platform.path_safety import normalized, native
from dev_storage_manager.scanning.fingerprint import identity, signature as make_signature

MAX_REVIEW_FILES = 50_000


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
    directories: list[str] = field(default_factory=list)


def inspect(result: Result, candidate: Candidate, cancel: Event | None = None,
            progress=None, protected=None, require_supported=True) -> Review:
    cancel = cancel or Event()
    root, target = Path(result.root), Path(candidate.path)
    if not within(target, root) or target == root:
        raise ValueError(tr('프로젝트 내부의 하위 후보만 검토할 수 있습니다.'))
    saved = next((f for f in result.folders if f.path == candidate.path), None)
    if not saved or candidate not in result.candidates:
        raise ValueError(tr('분석 결과에 없는 후보입니다.'))
    blocked = []
    if result.status != "complete":
        blocked.append(tr('완료된 전체 분석이 필요합니다. 취소/불완전 결과는 정리에 사용할 수 없습니다.'))
    if any(within(Path(i.path), target) or within(target, Path(i.path)) for i in result.issues):
        blocked.append(tr('후보 내부 또는 상위 경로에 제외/오류가 있습니다.'))
    current = scan(target, cancel, progress, protected)
    if current.status != "complete" or current.issues:
        blocked.append(tr('현재 후보를 완전하게 읽지 못했거나 링크/보호 항목이 있습니다.'))
    signature = current.folders[0].signature
    if not saved.signature or signature != saved.signature:
        blocked.append(tr('분석 이후 대상 식별 정보 또는 내용 목록이 변경되었습니다. 다시 분석하세요.'))
    included = []
    direct_proofs = {}
    limit_reached = False
    # Enumerate only already-scanned directories; recheck entries and boundary.
    for folder in current.folders:
        if cancel.is_set():
            blocked.append(tr('검토가 취소되었습니다.'))
            break
        path = Path(folder.path)
        try:
            directory_info = os.lstat(native(path))
            if is_link(directory_info):
                blocked.append(tr('검토 중 디렉터리가 링크로 변경되었습니다.'))
                continue
            with directory_guard(path), os.scandir(native(path)) as entries:
                current_entries = []
                for entry in entries:
                    if cancel.is_set():
                        break
                    info = entry.stat(follow_symlinks=False)
                    directory = stat.S_ISDIR(info.st_mode) and not is_link(info)
                    current_entries.append((entry.name, ("directory",) if directory else identity(info)))
                    if is_link(info):
                        blocked.append(tr('링크/reparse point가 포함되어 있습니다.'))
                    elif stat.S_ISREG(info.st_mode):
                        if len(included) >= MAX_REVIEW_FILES:
                            blocked.append(tr("포함 파일 표시 한도(50,000개)를 넘었습니다. 전체 목록을 검토하지 못했으므로 정리를 제한합니다."))
                            limit_reached = True
                            break
                        included.append(IncludedFile(str(normalized(entry.path)), info.st_size))
                direct_proofs[path] = make_signature(identity(directory_info), current_entries, [])
                current_entries.clear()
        except OSError as exc:
            blocked.append(tr('포함 항목 확인 실패: {p0}: {p1}').format(p0=path, p1=exc))
        if limit_reached:
            break
    if not cancel.is_set() and not limit_reached:
        children, root_proof = {}, None
        for folder in sorted(current.folders, key=lambda f: len(Path(f.path).parts), reverse=True):
            if cancel.is_set():
                break
            path = Path(folder.path)
            proof = make_signature((), [("direct", direct_proofs.get(path, "unvisited"))], children.get(path, []))
            if path == target:
                root_proof = proof
            else:
                children.setdefault(path.parent, []).append((path.name, proof))
        if (root_proof != signature or len(included) != current.files or
                sum(f.size for f in included) != current.size or
                len({Path(f.path) for f in included}) != len(included)):
            blocked.append(tr("포함 목록의 경로·식별 정보·파일 수·크기가 분석과 일치하지 않습니다. 다시 분석하고 검토하세요."))
    if cancel.is_set():
        blocked.append(tr('검토가 취소되었습니다.'))
    # Ensure enumeration has not changed metadata during review.
    if not cancel.is_set():
        after = scan(target, cancel, progress, protected)
        if after.status != "complete" or after.issues or after.folders[0].signature != signature:
            blocked.append(tr('검토 중 대상이 변경되었거나 읽기 오류가 발생했습니다.'))
    if require_supported and not candidate.cleanup_supported:
        blocked.append(tr('이 유형의 휴지통 이동은 아직 검증되지 않아 실행을 지원하지 않습니다.'))
    return Review(str(root), candidate, sorted(included, key=lambda f: f.path), signature,
                  list(dict.fromkeys(blocked)), [f.path for f in current.folders])


def deduplicate_paths(paths: list[str]) -> list[str]:
    selected: list[Path] = []
    for path in sorted({Path(os.path.abspath(p)) for p in paths}, key=lambda p: len(p.parts)):
        if not any(within(path, parent) for parent in selected):
            selected.append(path)
    return [str(p) for p in selected]
