"""Staged diagnostics use only newly generated fixtures; partial passes never authorize cleanup."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import py_compile
import subprocess
import tempfile
from threading import Event
from dev_storage_manager.cleanup.service import prepare, execute
from dev_storage_manager.i18n import tr
from dev_storage_manager.persistence.journal import Journal
from dev_storage_manager.platform.recycle import WindowsRecycle
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.cleanup.pytest_fixture import check_fixture


@dataclass
class Check:
    code: str
    label: str
    status: str
    detail: str


@dataclass
class Capability:
    ready: bool
    reason: str
    fixture: str = ""
    checks: list[Check] = field(default_factory=list)
    qualified_kinds: tuple[str, ...] = ()


def qualified_kinds(checks):
    states = {c.code: c.status for c in checks}
    core = (len(states) == len(checks) and "interrupted" not in states
            and all(states.get(code) == "passed" for code in ("boundary", "protection", "preservation")))
    return tuple(kind for kind, code in (("python-cache", "recycle"), ("pytest-cache", "pytest-recycle"))
                 if core and states.get(code) == "passed")


def qualify(base: Path, cancel: Event | None = None, progress=None) -> Capability:
    try:
        result = _qualify(base, cancel, progress)
    except Exception as exc:
        result = Capability(False, tr("환경 점검을 완료하지 못했습니다: ") + str(exc))
    try:
        base.mkdir(parents=True, exist_ok=True)
        report = {"schema": 2, "checked_at": datetime.now(timezone.utc).isoformat(),
                  "ready_in_that_session": result.ready, "reason": result.reason,
                  "fixture": result.fixture, "checks": [asdict(c) for c in result.checks], "qualified_kinds": list(result.qualified_kinds)}
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=base,
                                         prefix="result-", suffix=".json", delete=False) as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            temporary = stream.name
        os.replace(temporary, base / "last-result.json")
    except OSError as exc:
        return Capability(False, result.reason + "\n" + tr("환경 시험 기록 저장 실패: ") + str(exc), result.fixture, result.checks)
    return result


def load_report(base: Path) -> Capability | None:
    """Bounded diagnostics read; saved execution permission is never trusted."""
    try:
        with (base / "last-result.json").open("rb") as stream:
            data = stream.read(512 * 1024 + 1)
        if len(data) > 512 * 1024:
            return None
        report = json.loads(data)
        checks = [Check(str(c["code"]), str(c["label"]), str(c["status"]), str(c["detail"]))
                  for c in report.get("checks", [])[:20]]
        return Capability(False, tr("이전 점검 기록 · 이번 실행에서 다시 확인해야 정리를 사용할 수 있습니다.\n") + str(report["reason"]),
                          str(report.get("fixture", "")), checks)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return None


def _qualify(base: Path, cancel: Event | None = None, progress=None) -> Capability:
    cancel = cancel or Event()
    checks = []
    fixture = None
    link = None
    project = None

    def record(code, label, status, detail):
        checks.append(Check(code, label, status, detail))

    def phase(text):
        if progress:
            progress(text)

    def result():
        kinds = qualified_kinds(checks)
        passed = bool(kinds)
        reason = tr("기본 보호 점검을 통과했습니다. 유형별 휴지통 시험을 통과한 캐시만 개별 검증 후 실행할 수 있습니다.") if passed else tr("필수 환경 점검을 통과하지 못했습니다. 정리는 비활성 상태입니다.")
        details = "\n".join(f"{c.label}: {c.detail}" for c in checks if c.status != "passed")
        return Capability(passed, reason + ("\n" + details if details else ""), str(fixture or ""), checks, kinds)

    try:
        if os.name != "nt":
            return Capability(False, tr("휴지통 정리는 Windows 전용입니다."))
        if cancel.is_set():
            return Capability(False, tr("환경 시험이 취소되었습니다."))
        base.mkdir(parents=True, exist_ok=True)
        fixture = Path(tempfile.mkdtemp(prefix="qualification-", dir=base))
        project, outside = fixture / "project", fixture / "outside"
        project.mkdir()
        outside.mkdir()
        (outside / "must-not-scan.txt").write_bytes(b"outside-fixture")
        (project / ".git").mkdir()
        (project / ".git/must-keep").write_bytes(b"git-fixture")
        protected = project / "protected-app-data"
        protected.mkdir()
        (protected / "must-keep").write_bytes(b"protected-fixture")
        source = project / "fixture.py"
        source.write_bytes(b"qualification_fixture = 42\n")
        py_compile.compile(str(source), doraise=True)
        expected = source.stat().st_size + sum(p.stat().st_size for p in (project / "__pycache__").iterdir())
        link = project / "boundary-junction"
        phase(tr("1/5 · 임시 링크 경계 확인"))
        try:
            if cancel.is_set():
                raise ValueError(tr("환경 시험이 취소되었습니다."))
            if any(c in str(fixture) for c in '&|<>^%!"\r\n'):
                raise ValueError(tr("시험 경로에 명령 처리에 지원하지 않는 문자가 있습니다."))
            completed = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
                                       capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            if completed.returncode:
                raw = getattr(completed, "stderr", b"") or getattr(completed, "stdout", b"")
                try:
                    detail = raw.decode("utf-8").strip()
                except UnicodeDecodeError:
                    detail = raw.decode("mbcs", errors="replace").strip()
                raise ValueError(tr("junction 생성 실패 · 반환 코드 {code}: {detail}").format(code=completed.returncode, detail=detail))
            linked = scan(project, cancel, protected=[protected])
            if linked.status != "complete" or linked.size != expected or not any(i.path == str(link) for i in linked.issues):
                raise ValueError(tr("링크 바깥 집계 차단을 확인하지 못했습니다."))
            try:
                scan(link)
            except ValueError:
                pass
            else:
                raise ValueError(tr("링크를 루트로 등록하는 경로가 차단되지 않았습니다."))
            record("boundary", tr("링크 경계"), "passed", tr("바깥 경로 탐색과 링크 루트 등록을 차단했습니다."))
        except Exception as exc:
            record("boundary", tr("링크 경계"), "failed", str(exc))
        phase(tr("2/5 · 생성한 시험 원본과 보호 경로 확인"))
        scanned = scan(project, cancel, protected=[protected])
        protected_ok = scanned.status == "complete" and scanned.size == expected
        record("protection", tr("읽기 전용·보호 경로"), "passed" if protected_ok else "failed",
               tr(".git과 앱 데이터 시험 경로를 제외하고 원본·캐시만 집계했습니다.") if protected_ok else tr("시험 자료의 전체 집계를 확인하지 못했습니다."))
        phase(tr("3/5 · 생성한 시험 캐시만 휴지통 연동 확인"))
        if cancel.is_set() or not protected_ok:
            record("recycle", tr("휴지통 연동"), "skipped", tr("취소되었거나 원본 보호 점검을 통과하지 못했습니다."))
        else:
            journal = None
            try:
                candidate = next(c for c in scanned.candidates if c.kind == "python-cache")
                plan = prepare(scanned, candidate, cancel, protected=[protected])
                journal = Journal(fixture / "journal")
                execute([plan], journal, WindowsRecycle(), cancel, protected=[protected])
                rows = journal.history()
                if not rows or rows[0][3] != "succeeded":
                    raise ValueError(rows[0][4] if rows else tr("휴지통 작업 기록이 없습니다."))
                record("recycle", tr("휴지통 연동"), "passed", tr("시험 캐시의 휴지통 영수증과 원래 경로 소멸을 확인했습니다."))
            except Exception as exc:
                record("recycle", tr("휴지통 연동"), "failed", str(exc))
            finally:
                if journal:
                    journal.close()
        phase(tr("4/5 · 작업 후 시험 원본 보존 확인"))
        preserved = (source.read_bytes() == b"qualification_fixture = 42\n"
                     and (project / ".git/must-keep").read_bytes() == b"git-fixture"
                     and (protected / "must-keep").read_bytes() == b"protected-fixture"
                     and (outside / "must-not-scan.txt").read_bytes() == b"outside-fixture")
        record("preservation", tr("작업 후 원본 보존"), "passed" if preserved else "failed",
               tr("시험 소스·.git·보호 자료·바깥 자료가 보존되었습니다.") if preserved else tr("시험 원본 보존 확인에 실패했습니다."))
        phase(tr("5/5 · 생성한 pytest 테스트 캐시와 원본 보존 확인"))
        if cancel.is_set() or not protected_ok or not preserved:
            record("pytest-recycle", tr("pytest 테스트 캐시 휴지통"), "skipped", tr("취소 또는 원본 보호 점검 실패로 실행하지 않았습니다."))
        else:
            try:
                check_fixture(fixture, WindowsRecycle(), cancel)
                record("pytest-recycle", tr("pytest 테스트 캐시 휴지통"), "passed", tr("생성한 기본 캐시의 내용·휴지통 이동·원본 보존을 확인했습니다."))
            except Exception as exc:
                record("pytest-recycle", tr("pytest 테스트 캐시 휴지통"), "failed", str(exc))
        return result()
    except Exception as exc:
        record("interrupted", tr("점검 중단"), "failed", str(exc))
        return result()
    finally:
        # Remove the exact generated junction entry, never its destination.
        if link and os.path.lexists(link):
            if link.parent != project or link.name != "boundary-junction":
                raise ValueError(tr("시험 링크 경로 확인 실패"))
            os.rmdir(link)
