"""Validated cleanup pipeline with durable, fail-closed operation records."""
from dev_storage_manager.i18n import tr
from dataclasses import dataclass
from pathlib import Path
from threading import Event
import shutil

from dev_storage_manager.cleanup.policy import cache_proof
from dev_storage_manager.cleanup.review import Review, inspect, deduplicate_paths
from dev_storage_manager.domain.models import Result, Candidate
from dev_storage_manager.persistence.journal import Journal
from dev_storage_manager.platform.guard import directory_guard
from dev_storage_manager.platform.path_safety import native


@dataclass
class Plan:
    analysis: Result
    candidate: Candidate
    signature: str
    proof: dict[str, str]


def prepare(result: Result, candidate: Candidate, cancel=None, protected=None) -> Plan:
    review = inspect(result, candidate, cancel, protected=protected, require_supported=False)
    if review.blocked:
        raise ValueError("\n".join(review.blocked))
    proof = cache_proof(review, cancel)
    return Plan(result, candidate, review.signature, proof)


def verify(plan: Plan, cancel=None, protected=None):
    current = prepare(plan.analysis, plan.candidate, cancel, protected)
    if current.signature != plan.signature or current.proof != plan.proof:
        raise ValueError(tr('검토 이후 대상이 변경되었습니다. 다시 분석하고 검토하세요.'))


def free_space(root):
    try:
        with directory_guard(Path(root)):
            return shutil.disk_usage(native(root)).free
    except OSError:
        return None


def execute(plans: list[Plan], journal: Journal, backend, cancel: Event | None = None,
            protected=None):
    if not plans:
        raise ValueError(tr('선택한 정리 항목이 없습니다.'))
    cancel = cancel or Event()
    if len({p.analysis.root for p in plans}) != 1:
        raise ValueError(tr('한 작업에서는 하나의 등록 프로젝트만 처리합니다.'))
    paths = [p.candidate.path for p in plans]
    if len(deduplicate_paths(paths)) != len(paths):
        raise ValueError(tr('부모/자식 또는 중복 대상은 함께 실행할 수 없습니다.'))
    root = plans[0].analysis.root
    job = journal.begin([(p.candidate.path, p.candidate.size) for p in plans], free_space(root))
    outcomes = []
    try:
        for plan in plans:
            path = plan.candidate.path
            if cancel.is_set():
                journal.item(job, path, "cancelled", tr('실행 전에 사용자가 취소했습니다.'))
                outcomes.append("cancelled")
                continue
            # This commit must succeed before any request reaches the backend.
            journal.item(job, path, "running")
            attempted = False
            try:
                with directory_guard(Path(path).parent):
                    verify(plan, cancel, protected)
                    if cancel.is_set():
                        raise ValueError(tr('실행 직전에 취소되었습니다.'))
                    attempted = True
                    receipt = backend.move(Path(path), lambda: verify(plan, cancel, protected))
            except Exception as exc:
                # Cancellation before the OS request performed no move. Once
                # attempted, a missing original path is uncertainty, not success.
                import os
                status = ("cancelled" if cancel.is_set() and not attempted else
                          "unknown" if attempted and not os.path.lexists(native(path)) else "failed")
                journal.item(job, path, status, str(exc))
                outcomes.append(status)
            else:
                # Recording failure is not a backend failure: stop the entire job
                # rather than rewriting it and attempting more filesystem work.
                journal.item(job, path, "succeeded", destination=receipt.destination)
                outcomes.append("succeeded")
        status = outcomes[0] if len(set(outcomes)) == 1 else "partial"
        journal.finish(job, status, free_space(root))
    except Exception as exc:
        try:
            journal.interrupt(job, tr('작업 기록 오류로 중단되어 결과 미확정입니다. 원래 경로와 Windows 휴지통을 확인하세요. 상세: ') + str(exc))
        except Exception as recovery_error:
            raise RuntimeError(tr('작업이 중단되었으며 중단 상태도 저장하지 못했습니다. 추가 정리를 하지 말고 앱을 다시 시작해 이력을 확인하세요. 작업 오류: {p0} / 기록 오류: {p1}').format(p0=exc, p1=recovery_error)) from exc
        raise
    return job
