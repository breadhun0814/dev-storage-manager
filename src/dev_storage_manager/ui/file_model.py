"""Bounded largest-file snapshot. Selection never authorizes file deletion."""
from pathlib import Path
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from dev_storage_manager.i18n import tr
from dev_storage_manager.ui.formatting import format_size, exact_size


class FileModel(QAbstractTableModel):
    HEADERS = [tr("파일 이름"), tr("프로젝트 안의 폴더"), tr("크기 (논리적)")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.files = []
        self.root = None

    def set_result(self, result):
        self.beginResetModel()
        self.files = result.largest_files if result else []
        self.root = Path(result.root) if result else None
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.files)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 3

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.files):
            return None
        record = self.files[index.row()]
        path = Path(record.path)
        try:
            parent = str(path.parent.relative_to(self.root))
        except (ValueError, TypeError):
            parent = str(path.parent)
        if role == Qt.ItemDataRole.DisplayRole:
            return (path.name, tr("프로젝트 바로 아래") if parent == "." else parent, format_size(record.size))[index.column()]
        if role == Qt.ItemDataRole.UserRole:
            return (record.path, parent, record.size)[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return exact_size(record.size) if index.column() == 2 else record.path
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 2:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)
