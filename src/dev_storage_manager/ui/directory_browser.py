"""Read-only folder contents UI. Never opens or deletes a file."""
from pathlib import Path
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QSortFilterProxyModel, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
                              QLabel, QTableView, QHeaderView, QAbstractItemView, QDialogButtonBox, QPlainTextEdit)
from dev_storage_manager.i18n import tr
from dev_storage_manager.scanning.listing import list_directory, MAX_DIRECTORY_ENTRIES
from dev_storage_manager.ui.formatting import format_size, exact_size
from threading import Event


class ListingWorker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, result, target, protected, exclusions):
        super().__init__()
        self.analysis, self.target = result, target
        self.protected, self.exclusions = protected, exclusions
        self.cancel = Event()

    def run(self):
        try:
            self.result.emit(list_directory(self.analysis, self.target, self.cancel, self.protected, self.exclusions))
        except Exception as exc:
            self.failed.emit(str(exc))


class EntryModel(QAbstractTableModel):
    HEADERS = [tr("이름"), tr("종류"), tr("파일 크기"), tr("상태 / 안내")]
    KINDS = {"folder": tr("폴더"), "file": tr("파일"), "blocked": tr("보호·제외"), "link": tr("링크"), "error": tr("읽기 실패")}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []

    def set_entries(self, entries):
        self.beginResetModel()
        self.entries = entries
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.entries):
            return None
        row = self.entries[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return (row.name, self.KINDS.get(row.kind, row.kind), format_size(row.size) if row.size is not None else "—", row.note)[index.column()]
        if role == Qt.ItemDataRole.UserRole:
            return (row.path, row.kind, row.size if row.size is not None else -1, row.note)[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return exact_size(row.size) if index.column() == 2 and row.size is not None else row.path + "\n" + row.note
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)


class DirectoryBrowser(QDialog):
    open_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root, self.path, self.busy = Path(root), Path(root), False
        self.setWindowTitle(tr("폴더 내용 확인 · 읽기 전용"))
        self.setModal(True)
        self.resize(min(900, parent.width()-32) if parent else 900,
                    min(620, parent.height()-40) if parent else 620)
        layout = QVBoxLayout(self)
        actions = QHBoxLayout()
        self.up = QPushButton(tr("상위 폴더"))
        self.up.clicked.connect(lambda: self.open_requested.emit(str(self.path.parent)) if self.path != self.root else None)
        actions.addWidget(self.up)
        self.home = QPushButton(tr("프로젝트 처음"))
        self.home.clicked.connect(lambda: self.open_requested.emit(str(self.root)))
        actions.addWidget(self.home)
        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        actions.addWidget(self.path_field, 1)
        self.refresh_button = QPushButton(tr("새로 읽기"))
        self.refresh_button.clicked.connect(lambda: self.open_requested.emit(str(self.path)))
        actions.addWidget(self.refresh_button)
        layout.addLayout(actions)
        self.status = QLabel(tr("폴더를 읽고 있습니다."))
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("현재 표시 목록에서 이름·경로 검색"))
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.model = EntryModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterRole(Qt.ItemDataRole.UserRole)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.proxy.setFilterKeyColumn(0)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search.textChanged.connect(self.filter_entries)
        self.filter_status = QLabel()
        layout.addWidget(self.filter_status)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 95)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 265)
        self.table.doubleClicked.connect(lambda index: self.open_selected())
        self.table.selectionModel().currentChanged.connect(self.selection_changed)
        layout.addWidget(self.table)
        self.selected = QPlainTextEdit()
        self.selected.setReadOnly(True)
        self.selected.setMaximumHeight(85)
        self.selected.setPlainText(tr("행을 선택하면 전체 경로를 확인합니다. 파일을 실행하거나 삭제하지 않습니다."))
        layout.addWidget(self.selected)
        controls = QHBoxLayout()
        self.open_button = QPushButton(tr("선택한 하위 폴더 열기"))
        self.open_button.clicked.connect(self.open_selected)
        self.open_button.setEnabled(False)
        controls.addWidget(self.open_button)
        self.cancel_button = QPushButton(tr("목록 읽기 취소"))
        self.cancel_button.clicked.connect(self.request_cancel)
        controls.addWidget(self.cancel_button)
        layout.addLayout(controls)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText(tr("닫기"))
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.finished.connect(lambda _: self.cancel_requested.emit() if self.busy else None)

    def request_cancel(self):
        if self.busy:
            self.status.setText(tr("취소 요청 중 · 현재 파일 시스템 호출이 끝나면 중단합니다."))
            self.cancel_button.setEnabled(False)
            self.cancel_requested.emit()

    def set_loading(self, path):
        self.busy = True
        if self.path != Path(path):
            self.search.clear()
        self.path = Path(path)
        self.path_field.setText(str(path))
        self.path_field.setCursorPosition(0)
        self.status.setText(tr("현재 폴더의 바로 아래 항목을 읽고 있습니다. 원본은 변경하지 않습니다."))
        self.model.set_entries([])
        self.filter_entries()
        self.selected.setPlainText(tr("목록을 읽는 동안 기다리거나 취소할 수 있습니다."))
        self.up.setEnabled(False)
        self.home.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

    def show_listing(self, listing):
        self.busy = False
        self.model.set_entries(listing.entries)
        self.filter_entries()
        states = {"complete": tr("현재 폴더 목록"), "limited": tr("표시 한도 도달 · 전체 목록 아님"),
                  "incomplete": tr("읽기 실패 포함 · 불완전 목록"), "cancelled": tr("취소 · 부분 목록")}
        self.status.setText(tr("{state} · {count:,}개 표시 · 최대 {limit:,}개\n분석 이후 달라졌을 수 있습니다. 폴더의 하위 포함 크기는 분석 표에서 확인하세요.").format(state=states.get(listing.status, listing.status), count=len(listing.entries), limit=MAX_DIRECTORY_ENTRIES)
                            + ("\n" + tr("표시 한도 때문에 일부 항목은 표시하지 않았습니다.") if listing.truncated else "")
                            + ("\n" + listing.error if listing.error else ""))
        self.selected.setPlainText(tr("파일 선택은 전체 경로 확인용입니다. 폴더만 더블클릭하거나 아래 버튼으로 열 수 있습니다."))
        self.up.setEnabled(self.path != self.root)
        self.home.setEnabled(self.path != self.root)
        self.refresh_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def show_error(self, message):
        self.busy = False
        self.status.setText(tr("폴더를 읽지 못했습니다: ") + message)
        self.model.set_entries([])
        self.filter_entries()
        self.up.setEnabled(self.root in self.path.parents)
        self.home.setEnabled(self.path != self.root)
        self.refresh_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def current_entry(self):
        index = self.table.currentIndex()
        row = self.proxy.mapToSource(index).row() if index.isValid() else -1
        return self.model.entries[row] if 0 <= row < len(self.model.entries) else None

    def filter_entries(self):
        self.proxy.setFilterFixedString(self.search.text())
        self.filter_status.setText(tr("현재 표시 {shown:,}개 / 읽은 목록 {total:,}개").format(shown=self.proxy.rowCount(), total=self.model.rowCount()))

    def selection_changed(self, index, previous):
        entry = self.current_entry()
        self.open_button.setEnabled(not self.busy and entry is not None and entry.navigable)
        if entry:
            self.selected.setPlainText(entry.path + "\n" + (exact_size(entry.size) if entry.size is not None else entry.note))

    def open_selected(self):
        entry = self.current_entry()
        if not self.busy and entry and entry.navigable:
            self.open_requested.emit(entry.path)
