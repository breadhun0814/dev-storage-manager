"""In-app instructions using the actual Korean action names."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QPlainTextEdit, QPushButton
from dev_storage_manager.i18n import tr


class UsageHelp(QDialog):
    demo_requested = Signal()

    def __init__(self, parent=None, allow_demo=True):
        super().__init__(parent)
        self.setWindowTitle(tr("사용 방법 · 실제 폴더 분석과 정리"))
        self.resize(min(780, parent.width() - 24) if parent else 780, min(560, parent.height() - 32) if parent else 560)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        pages = [
            (tr("처음 사용"), tr("1. '폴더 추가'에서 분석할 프로젝트 폴더를 선택합니다.\n2. 위쪽 프로젝트 선택 칸에서 경로를 확인하고 '선택 프로젝트 분석'을 누릅니다.\n3. '폴더별 용량'과 '큰 파일'에서 실제 분석 결과를 봅니다. 파일 행 선택은 내용 확인용이며 삭제 선택이 아닙니다.\n4. '프로젝트·정리 후보' 탭에서 후보 또는 후보가 없는 이유를 확인합니다.\n5. 정리를 원하면 '관리 · 도구 → 정리 환경 확인'에서 앱이 만든 시험 자료로 환경을 확인합니다. 통과한 유형만 검토 후 실행할 수 있습니다.\n6. 후보 행을 한 번 선택하고 '② 포함 파일 검토'를 누릅니다. 전체 경로·포함 파일·근거·주의·재생성 조건을 확인합니다.\n7. 실행 가능한 유형에서만 직접 확인 체크 후 '③ 확인한 후보 폴더 1개를 휴지통으로 이동'을 누릅니다.\n8. 결과 창과 이력을 확인하고 '프로젝트 다시 분석'으로 최신 상태를 확인합니다.\n\n개인 자료로 처음 시험하기 어렵다면 아래 '시험 프로젝트 만들고 분석'을 사용하세요. 새 하위 폴더만 만들며 정리는 자동 실행하지 않습니다.")),
            (tr("후보 표가 비었을 때"), tr("후보가 없는 것은 선택하거나 정리할 항목이 없는 상태일 수 있습니다. 실제 프로젝트에 __pycache__를 직접 만들 필요는 없습니다.\n\n먼저 선택 경로와 분석 상태를 확인하세요. 취소/읽기 오류/제외 범위가 있으면 후보가 없다고 확정할 수 없습니다. '오류·제외 범위'를 확인하세요.\n\n분석이 완료되어도 현재 규칙에 맞는 캐시가 없을 수 있습니다. 폴더별 용량·큰 파일 목록은 계속 사용할 수 있습니다. 가상환경·node_modules·빌드 결과는 현재 검토 전용입니다.\n\n시험 프로젝트 기능은 선택한 상위 폴더에 새 이름의 폴더를 만들고, 고정 원본과 실제 Python 캐시를 생성하여 등록·분석합니다. 기존 파일을 복사하거나 덮어쓰지 않습니다. 시험 자료도 같은 보호/내용 검증/환경 시험/직접 확인을 적용하며 실행 자격을 우회하지 않습니다.\n\n생성 중 취소/실패하면 새 시험 폴더에 일부 자료가 남을 수 있으며 경로를 표시합니다. 자동 삭제하지 않습니다. 목록에서 제거해도 실제 폴더는 남습니다.")),
            (tr("휴지통·복원·한계"), tr("휴지통 이동을 확인한 논리적 파일 크기와 실제 관측한 디스크 여유 공간은 다른 값입니다. 휴지통을 비우지 않으므로 즉시 여유 공간이 늘었다고 보장하지 않습니다.\n\n실패/미확정은 성공이나 원본 보존을 단정할 수 없습니다. 원래 경로와 Windows 휴지통을 확인하세요. 기록 오류가 있었다면 추가 정리를 중단하고 저장 기능이 회복된 뒤 앱을 다시 시작해 이력을 확인하세요.\n\n복원하려면 Windows 휴지통을 직접 열고 원래 위치·삭제 시각을 확인한 뒤 '복원'을 선택합니다. 앱은 자동 복원/휴지통 비우기/영구 삭제를 제공하지 않습니다. 이미 비운 휴지통을 앱에서 복구할 수 없습니다.\n\n정리 시도 후 이전 후보는 재분석 전까지 사용할 수 없습니다. 환경 시험 통과는 모든 폴더의 삭제 가능성을 보장하지 않으며 각 후보를 실행 직전에 다시 검증합니다.\n\n이 앱은 로컬 시험 버전입니다. 깨끗한 Windows 설치·Windows 10·모든 DPI와 일부 정리 유형의 실제 복원 검증은 아직 완료하지 않았습니다."))]
        for name, text in pages:
            field = QPlainTextEdit(text)
            field.setReadOnly(True)
            tabs.addTab(field, name)
        layout.addWidget(tabs)
        actions = QHBoxLayout()
        demo = QPushButton(tr("시험 프로젝트 만들고 분석"))
        demo.setEnabled(allow_demo)
        if not allow_demo:
            demo.setToolTip(tr("진행 중인 작업이 끝난 뒤 시험 프로젝트를 만들 수 있습니다."))
        demo.clicked.connect(self.demo_requested)
        close = QPushButton(tr("닫기"))
        close.clicked.connect(self.accept)
        actions.addWidget(demo)
        actions.addWidget(close)
        layout.addLayout(actions)
