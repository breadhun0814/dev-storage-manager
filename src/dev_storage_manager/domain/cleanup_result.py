"""Recorded cleanup outcomes; no filesystem operations or UI dependencies."""
from dataclasses import dataclass


@dataclass
class JobResult:
    job: str
    created: str
    status: str
    free_before: int | None
    free_after: int | None
    counts: dict[str, int]
    moved_size: int
    total_size: int
    items: list[tuple]


@dataclass
class CleanupReport:
    project: str
    path: str
    job: str | None
    result: JobResult | None
    error: str = ""
