from dataclasses import dataclass, field


@dataclass
class Folder:
    path: str
    size: int = 0
    files: int = 0
    category: str = "unclassified"
    signature: str = ""


@dataclass
class ProjectEvidence:
    path: str
    kind: str
    markers: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    path: str
    kind: str
    size: int
    files: int
    evidence: str
    warning: str
    regeneration: str
    cleanup_supported: bool = False


@dataclass
class Issue:
    path: str
    reason: str
    error: bool = False


@dataclass
class Result:
    root: str
    status: str = "complete"
    folders: list[Folder] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    size: int = 0
    files: int = 0
    projects: list[ProjectEvidence] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
