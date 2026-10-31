from dev_storage_manager.i18n import tr
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from dev_storage_manager.detection.rules import CATEGORIES
from pathlib import Path
from dev_storage_manager.ui.formatting import format_size, exact_size
from dev_storage_manager.domain.coverage import Coverage, folder_coverage
from dev_storage_manager.ui.coverage_text import LABELS, coverage_note


class FolderModel(QAbstractTableModel):
    """Keep domain rows, create display values only for visible cells."""
    HEADERS = [tr('폴더 (하위 포함 · 행끼리 합산하지 마세요)'), tr('크기 (논리적)'), tr('파일 수'), tr('분류'), tr('분석 범위')]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folders = []
        self.root = None
        self.coverage = Coverage()

    def set_folders(self, folders, root=None):
        self.beginResetModel()
        self.folders = folders
        self.root = Path(root) if root else None
        self.coverage = Coverage()
        self.endResetModel()

    def set_result(self, result):
        self.beginResetModel()
        self.folders = result.folders
        self.root = Path(result.root)
        self.coverage = folder_coverage(result)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.folders)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 5

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.folders):
            return None
        folder = self.folders[index.row()]
        raw = (folder.path, folder.size, folder.files, CATEGORIES.get(folder.category, folder.category))
        if role == Qt.ItemDataRole.UserRole and index.column() < 4:
            return raw[index.column()]
        state = self.coverage.state(folder.path)
        values = (*raw, LABELS[state])
        if index.column() == 1:
            if role == Qt.ItemDataRole.DisplayRole:
                return format_size(folder.size) if state == "complete" else tr("확인 {size}").format(size=format_size(folder.size)) if folder.size else "—"
            if role == Qt.ItemDataRole.ToolTipRole:
                return tr("확인된 논리적 합계: ") + exact_size(folder.size) + "\n" + coverage_note(state)
        if index.column() == 2 and role == Qt.ItemDataRole.DisplayRole and state != "complete":
            return tr("확인 {count:,}").format(count=folder.files) if folder.files else "—"
        if index.column() == 2 and role == Qt.ItemDataRole.ToolTipRole and state != "complete":
            return tr("확인된 파일 수: {count:,} · 전체 파일 수는 미확인입니다.").format(count=folder.files)
        if index.column() == 4 and role == Qt.ItemDataRole.ToolTipRole:
            return coverage_note(state)
        if role == Qt.ItemDataRole.DisplayRole and index.column() == 0 and self.root:
            try:
                relative = Path(folder.path).relative_to(self.root)
                return tr("프로젝트 전체") if str(relative) == "." else str(relative)
            except ValueError:
                return folder.path
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.UserRole, Qt.ItemDataRole.ToolTipRole):
            return values[index.column()]
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in (1, 2):
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)
