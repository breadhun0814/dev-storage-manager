"""Pure metadata rules: no imports, installers or project code are executed."""
import fnmatch
import re
from pathlib import Path

from dev_storage_manager.domain.models import Candidate, ProjectEvidence, Result

LOCKS = {"package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb"}
PYTHON = {"pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "poetry.lock"}
GRADLE = {"build.gradle", "build.gradle.kts"}
CATEGORIES = {"unclassified": "미분류/개발 재료", "python-cache": "Python 캐시 후보",
              "pytest-cache": "pytest 캐시 후보", "python-environment": "Python 가상환경 후보",
              "node-dependencies": "JavaScript 의존성 후보", "maven-build": "Maven 빌드 후보",
              "gradle-build": "Gradle 빌드 후보"}


class Evidence:
    """Retain only relevant filenames; ordinary file lists are not persisted."""
    def __init__(self):
        self.markers: dict[Path, set[str]] = {}
        self.python_sources: set[tuple[Path, str]] = set()
        self.pyc_sources: dict[Path, set[str]] = {}

    def file(self, parent: Path, name: str):
        if name in PYTHON | LOCKS | GRADLE | {"package.json", "pom.xml", "pyvenv.cfg", "CACHEDIR.TAG", "README.md", ".gitignore"} or fnmatch.fnmatchcase(name, "requirements*.txt"):
            self.markers.setdefault(parent, set()).add(name)
        if name.endswith(".py"):
            self.python_sources.add((parent, name[:-3]))
        match = re.fullmatch(r"(.+)\.cpython-\d{2,3}(?:\.opt-\d+)?\.pyc", name)
        if parent.name == "__pycache__" and match:
            self.pyc_sources.setdefault(parent, set()).add(match[1])


def classify(result: Result, evidence: Evidence):
    markers = evidence.markers
    for path, names in markers.items():
        for kind, found in (
            ("Python", names & PYTHON | {n for n in names if fnmatch.fnmatchcase(n, "requirements*.txt")}),
            ("JavaScript", {"package.json"} if "package.json" in names else set()),
            ("Maven", names & {"pom.xml"}),
            ("Gradle", names & GRADLE),
        ):
            if found:
                result.projects.append(ProjectEvidence(str(path), kind, sorted(found)))
    project_paths = {Path(p.path) for p in result.projects}
    candidates: list[Candidate] = []
    for folder in sorted(result.folders, key=lambda f: len(Path(f.path).parts)):
        path = Path(folder.path)
        if path == Path(result.root):
            continue
        # A dependency's internal projects/caches are already part of its outer candidate.
        if any(Path(c.path) in path.parents for c in candidates):
            continue
        parent_names = markers.get(path.parent, set())
        names = markers.get(path, set())
        associated = any(p == path.parent or p in path.parents for p in project_paths)
        kind = reason = warning = regeneration = ""
        if path.name == "__pycache__":
            matched = sorted(n for n in evidence.pyc_sources.get(path, set())
                             if (path.parent, n) in evidence.python_sources)
            if matched:
                kind = "python-cache"
                reason = "CPython 캐시 파일명과 같은 위치의 .py 원본 확인: " + ", ".join(matched[:5])
                warning = "원본과 연결된 캐시 근거가 있으나 내부에 사용자 파일이 있을 수 있습니다. 정리 전 전체 포함 파일과 변경 여부 검증이 필요합니다."
                regeneration = "해당 Python 코드를 다음에 실행하면 캐시가 다시 생성될 수 있습니다. 앱은 프로젝트 코드를 실행하지 않습니다."
        elif path.name == ".pytest_cache" and associated and {"CACHEDIR.TAG", "README.md", ".gitignore"} <= names:
            kind = "pytest-cache"
            reason = "프로젝트 표식과 pytest 캐시 구성 표식(CACHEDIR.TAG, README.md, .gitignore) 확인. 내용 검증 전 후보입니다."
            warning = "마지막 실패/노드 ID 등 테스트 실행 정보가 사라질 수 있으며 사용자 추가 파일 여부 검토가 필요합니다."
            regeneration = "개발 환경에서 pytest를 다시 실행하면 생성됩니다. 앱은 명령을 자동 실행하지 않습니다."
        elif "pyvenv.cfg" in names and associated:
            kind = "python-environment"
            reason = "프로젝트 경계 내부의 pyvenv.cfg 일반 파일 확인"
            warning = "패키지와 가상환경 내부에 사용자 수정이 있을 수 있습니다. 정리 미지원입니다."
            regeneration = "Python 버전과 의존성 기록을 확인한 뒤 python -m venv 및 프로젝트 설치 절차를 사용하세요. 자동 실행하지 않습니다."
        elif path.name == "node_modules" and "package.json" in parent_names and parent_names & LOCKS:
            kind = "node-dependencies"
            reason = "직접 상위 package.json과 잠금 파일 확인: " + ", ".join(sorted(parent_names & LOCKS))
            warning = "패키지 내부 수정·로컬 의존성·네이티브 빌드가 있을 수 있습니다. 정리 미지원입니다."
            regeneration = "잠금 파일에 맞는 npm ci / pnpm install --frozen-lockfile / yarn 설치 절차를 검토하세요. 자동 실행하지 않습니다."
        elif path.name == "target" and "pom.xml" in parent_names:
            kind = "maven-build"
            reason = "직접 상위 pom.xml 확인; target 경로의 빌드 결과 후보"
            warning = "사용자가 보관한 파일이나 빌드 설정 변경이 있을 수 있습니다. 정리 미지원입니다."
            regeneration = "프로젝트의 JDK/Maven 환경과 빌드 문서를 확인하세요(예: mvn package). 자동 실행하지 않습니다."
        elif path.name == "build" and parent_names & GRADLE:
            kind = "gradle-build"
            reason = "직접 상위 Gradle 빌드 파일 확인: " + ", ".join(sorted(parent_names & GRADLE))
            warning = "사용자 파일 및 사용자 지정 산출물일 수 있습니다. 정리 미지원입니다."
            regeneration = "프로젝트의 JDK/Gradle 환경과 빌드 문서를 확인하세요(예: .\\gradlew.bat build). 자동 실행하지 않습니다."
        if kind:
            folder.category = kind
            candidates.append(Candidate(str(path), kind, folder.size, folder.files, reason, warning, regeneration))
    result.candidates = candidates
