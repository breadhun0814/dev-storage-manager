from dev_storage_manager.i18n import tr
from dataclasses import dataclass
from dev_storage_manager.domain.models import Result


@dataclass
class Difference:
    path: str
    size_before: int
    size_after: int
    files_before: int
    files_after: int

    @property
    def delta(self):
        return self.size_after - self.size_before


def compare(before: Result, after: Result) -> list[Difference]:
    if before.root != after.root or before.status != "complete" or after.status != "complete":
        raise ValueError(tr('같은 프로젝트의 완료된 결과 두 개가 필요합니다.'))
    if set(before.exclusions) != set(after.exclusions):
        raise ValueError(tr('제외 목록이 달라 직접 비교할 수 없습니다.'))
    if [(i.path, i.reason, i.error) for i in sorted(before.issues, key=lambda i: i.path)] != [
            (i.path, i.reason, i.error) for i in sorted(after.issues, key=lambda i: i.path)]:
        raise ValueError(tr('오류/제외 범위가 달라 직접 비교할 수 없습니다.'))
    previous = {f.path: f for f in before.folders}
    current = {f.path: f for f in after.folders}
    differences = []
    for path in sorted(previous.keys() | current.keys()):
        old, new = previous.get(path), current.get(path)
        difference = Difference(path, old.size if old else 0, new.size if new else 0,
                                old.files if old else 0, new.files if new else 0)
        if difference.size_before != difference.size_after or difference.files_before != difference.files_after:
            differences.append(difference)
    return differences
