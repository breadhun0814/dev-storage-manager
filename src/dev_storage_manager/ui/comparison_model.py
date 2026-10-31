from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from dev_storage_manager.i18n import tr
from dev_storage_manager.ui.formatting import format_size, exact_size


class ComparisonModel(QAbstractTableModel):
    HEADERS = [tr("경로"), tr("이전 크기"), tr("현재 크기"), tr("크기 차이"), tr("파일 수 차이")]

    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.rows = rows

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        values = (row.path, row.size_before, row.size_after, row.delta, row.files_after-row.files_before)
        if index.column() in (1, 2, 3):
            if role == Qt.ItemDataRole.DisplayRole:
                return format_size(values[index.column()])
            if role == Qt.ItemDataRole.ToolTipRole:
                return exact_size(values[index.column()])
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.UserRole, Qt.ItemDataRole.ToolTipRole):
            return values[index.column()]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)
