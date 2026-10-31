"""Read current direct children within a registered analysis boundary only."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import stat
from threading import Event
from dev_storage_manager.domain.models import Result
from dev_storage_manager.i18n import tr
from dev_storage_manager.platform.guard import directory_guard
from dev_storage_manager.platform.path_safety import normalized, native
from dev_storage_manager.scanning.scanner import is_link, within

MAX_DIRECTORY_ENTRIES = 5000


@dataclass
class Entry:
    path: str
    name: str
    kind: str
    size: int | None = None
    navigable: bool = False
    note: str = ""


@dataclass
class Listing:
    root: str
    path: str
    entries: list[Entry] = field(default_factory=list)
    status: str = "complete"
    error: str = ""
    truncated: bool = False


def list_directory(result: Result, target, cancel: Event | None = None, protected=None, exclusions=None):
    cancel = cancel or Event()
    root, target = normalized(result.root), normalized(target)
    folders = {normalized(folder.path) for folder in result.folders}
    if root == Path(root.anchor) or not within(target, root) or target not in folders:
        raise ValueError(tr("현재 등록 프로젝트의 분석 결과에 포함된 폴더만 열 수 있습니다. 다시 분석하세요."))
    protected = [normalized(p) for p in protected or []]
    excluded = []
    for value in result.exclusions if exclusions is None else exclusions:
        relative = Path(value)
        if relative.is_absolute() or relative.anchor or ".." in relative.parts or not relative.parts:
            raise ValueError(tr("제외 경로는 프로젝트 내부 상대 경로여야 합니다."))
        excluded.append(root / relative)

    def restricted(path):
        if any(p.name.casefold() == ".git" for p in [path, *path.parents]):
            return tr(".git 보호 경로 · 열지 않음")
        if any(within(path, p) for p in protected):
            return tr("앱 데이터·실행 환경 등 보호 경로 · 열지 않음")
        if any(within(path, p) for p in excluded):
            return tr("사용자 제외 경로 · 열지 않음")
        return ""

    reason = restricted(target)
    if reason:
        raise ValueError(reason)
    listing = Listing(str(root), str(target))
    if cancel.is_set():
        listing.status = "cancelled"
        return listing
    # The guard opens every component without following reparse points and
    # holds ancestor handles while the iterator is active.
    with directory_guard(target):
        info = os.lstat(native(target))
        if is_link(info) or not stat.S_ISDIR(info.st_mode):
            raise ValueError(tr("링크이거나 폴더가 아닌 경로는 열 수 없습니다."))
        try:
            with os.scandir(native(target)) as children:
                for child in children:
                    if cancel.is_set():
                        listing.status = "cancelled"
                        break
                    if len(listing.entries) >= MAX_DIRECTORY_ENTRIES:
                        listing.truncated = True
                        if listing.status == "complete":
                            listing.status = "limited"
                        break
                    path = normalized(child.path)
                    reason = restricted(path)
                    if reason:
                        listing.entries.append(Entry(str(path), child.name, "blocked", note=reason))
                        continue
                    try:
                        metadata = child.stat(follow_symlinks=False)
                        if is_link(metadata):
                            row = Entry(str(path), child.name, "link", note=tr("링크/reparse point · 따라가지 않음"))
                        elif stat.S_ISDIR(metadata.st_mode):
                            known = path in folders
                            row = Entry(str(path), child.name, "folder", navigable=known,
                                        note=tr("하위 포함 용량은 분석 결과에서 확인") if known else tr("분석에 없는 새 폴더 · 다시 분석한 뒤 열 수 있음"))
                        elif stat.S_ISREG(metadata.st_mode):
                            row = Entry(str(path), child.name, "file", metadata.st_size, note=tr("현재 논리적 크기 · 삭제 선택 아님"))
                        else:
                            row = Entry(str(path), child.name, "blocked", note=tr("일반 파일·폴더가 아닌 항목 · 열지 않음"))
                    except OSError as exc:
                        listing.status = "incomplete"
                        row = Entry(str(path), child.name, "error", note=str(exc))
                    listing.entries.append(row)
        except OSError as exc:
            listing.status = "incomplete"
            listing.error = str(exc)
    listing.entries.sort(key=lambda e: (e.kind != "folder", e.name.casefold(), e.name))
    if cancel.is_set():
        listing.status = "cancelled"
    return listing
