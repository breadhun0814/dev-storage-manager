"""Explicit recorded outcome, with no restore or permanent-delete actions."""
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton
from dev_storage_manager.i18n import tr
from dev_storage_manager.ui.formatting import exact_size


class CleanupResultDialog(QDialog):
    history_requested = Signal()
    rescan_requested = Signal()

    def __init__(self, report, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("정리 실행 결과"))
        self.setModal(True)
        self.resize(min(780, parent.width() - 24) if parent else 780,
                    min(560, parent.height() - 32) if parent else 560)
        layout = QVBoxLayout(self)
        statuses = {"succeeded": tr("휴지통 이동 확인"), "failed": tr("실패"), "unknown": tr("결과 미확정"),
                    "cancelled": tr("실행 전 취소"), "running": tr("완료 미확정"), "pending": tr("대기 기록"),
                    "partial": tr("항목별 결과가 다름"), "interrupted": tr("작업 중단 · 확인 필요")}
        result = report.result
        title = statuses.get(result.status, tr("결과 확인 필요")) if result else tr("결과 기록을 확인하지 못했습니다.")
        self.headline = QLabel(title)
        self.headline.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.headline)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        lines = [tr("원래 대상: ") + report.path, tr("작업 ID: ") + (report.job or tr("확인된 작업 ID 없음"))]
        if result:
            counts = " · ".join(statuses.get(s, s) + f" {n:,}" for s, n in result.counts.items())
            space = lambda value: exact_size(value) if value is not None else tr("관측 실패")
            lines.extend([tr("실행 시간: ") + result.created, counts,
                          tr("휴지통 이동을 확인한 논리적 크기: ") + exact_size(result.moved_size),
                          tr("전체 계획의 논리적 크기: ") + exact_size(result.total_size),
                          tr("관측한 디스크 여유 공간 — 실행 전: {before} / 실행 후: {after}").format(before=space(result.free_before), after=space(result.free_after)),
                          tr("휴지통을 비우지 않으므로 이동 크기만큼 즉시 여유 공간이 늘었다는 뜻이 아닙니다."), ""])
            for path, size, status, reason, receipt in result.items:
                lines.extend([path, statuses.get(status, status) + " · " + exact_size(size),
                              tr("실패 이유 / 결과: ") + (reason or tr("기록 없음")),
                              tr("확인된 휴지통 영수증: ") + (receipt or tr("없음")), ""])
            if len(result.items) < sum(result.counts.values()):
                lines.append(tr("처음 200개 대상만 표시합니다. 전체 대상은 이력에서 확인하세요."))
        else:
            lines.append(tr("결과를 읽지 못한 것은 성공·실패·원본 보존 또는 이력 없음을 증명하지 않습니다."))
        if report.error:
            lines.extend([tr("작업 / 기록 오류:"), report.error])
        lines.append(tr("미확정은 원래 경로와 Windows 휴지통을 확인하세요. 복원은 Windows 휴지통에서 직접 하며 앱은 자동 복원/비우기를 제공하지 않습니다. 최신 상태는 다시 분석하세요."))
        self.details.setPlainText("\n".join(lines))
        layout.addWidget(self.details, 1)
        actions = QHBoxLayout()
        self.history_button = QPushButton(tr("이 작업 이력 보기") if report.job else tr("전체 이력 보기"))
        self.history_button.clicked.connect(self.history_requested)
        self.rescan_button = QPushButton(tr("프로젝트 다시 분석"))
        self.rescan_button.clicked.connect(self.rescan_requested)
        close = QPushButton(tr("닫기"))
        close.clicked.connect(self.accept)
        for button in (self.history_button, self.rescan_button, close):
            actions.addWidget(button)
        layout.addLayout(actions)
