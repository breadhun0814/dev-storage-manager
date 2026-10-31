"""Derive scope from existing result metadata, without filesystem access."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Coverage:
    default: str = "complete"
    overrides: dict[Path, str] = field(default_factory=dict)

    def state(self, path):
        return self.overrides.get(Path(path), self.default) if self.overrides else self.default


def folder_coverage(result):
    if result.status == "cancelled":
        # Legacy snapshots do not record which queued directories were visited.
        return Coverage("cancelled")
    if result.status not in {"complete", "incomplete"}:
        return Coverage("unknown")
    root = Path(result.root)
    errors = [issue for issue in result.issues if issue.error]
    if result.status == "incomplete" and not errors:
        return Coverage("incomplete")
    if any(root != Path(i.path) and root not in Path(i.path).parents for i in errors):
        return Coverage("incomplete")
    coverage = Coverage()
    priority = {"complete": 0, "excluded": 1, "incomplete": 2}
    for issue in result.issues:
        path = Path(issue.path)
        state = "incomplete" if issue.error else "excluded"
        if path != root and root not in path.parents:
            continue
        for current in (path, *path.parents):
            if priority[coverage.overrides.get(current, "complete")] >= priority[state]:
                break
            coverage.overrides[current] = state
            if current == root:
                break
    return coverage
