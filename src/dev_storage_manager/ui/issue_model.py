from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from dev_storage_manager.i18n import tr


class IssueModel(QAbstractTableModel):
    HEADERS = [tr("읽기 실패 / 제외 경로"), tr("상태"), tr("이유")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.issues = []

    def set_issues(self, issues):
        self.beginResetModel()
        self.issues = issues
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.issues)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 3

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.issues):
            return None
        issue = self.issues[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return (issue.path, tr("읽기 오류") if issue.error else tr("제외"), issue.reason)[index.column()]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)
