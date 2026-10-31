"""Save a language choice for the next launch; do not change active workers."""
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QMessageBox, QVBoxLayout
from dev_storage_manager.i18n import LANGUAGES, tr


class LanguageDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(tr("표시 언어 / Language"))
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        label = QLabel(tr("앱 표시 언어를 선택하세요. 저장 후 앱을 다시 실행하면 적용됩니다."))
        label.setWordWrap(True)
        layout.addWidget(label)
        self.languages = QComboBox()
        for code, name in LANGUAGES.items():
            self.languages.addItem(name, code)
        self.languages.setCurrentIndex(self.languages.findData(store.language()))
        layout.addWidget(self.languages)
        hint = QLabel(tr("번역이 없는 문구는 영어로 표시합니다. 파일 이름·경로와 기존 기록은 원문을 유지합니다."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("저장"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("취소"))
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        try:
            self.store.set_language(self.languages.currentData())
        except Exception as exc:
            QMessageBox.warning(self, tr("언어 저장 실패"), str(exc))
            return
        QMessageBox.information(self, tr("언어 설정 저장됨"), tr("언어 설정을 저장했습니다. 앱을 닫고 다시 실행하세요. 진행 중 작업은 자동 종료하지 않습니다."))
        self.accept()
