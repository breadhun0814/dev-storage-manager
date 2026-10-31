"""Virtual included-file view. Filtering never changes a cleanup plan."""
from pathlib import Path
from threading import Event

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QLineEdit,
    QTableView, QTabWidget, QWidget, QCheckBox, QPushButton, QDialogButtonBox,
    QHeaderView, QAbstractItemView)

from dev_storage_manager.i18n import tr
from dev_storage_manager.ui.formatting import format_size, exact_size


class IncludedModel(QAbstractTableModel):
    sort_requested = Signal(int, object)

    def __init__(self, review, parent=None):
        super().__init__(parent)
        self.files, self.root = review.files, Path(review.candidate.path)
        self.indices = range(len(self.files))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.indices)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 2

    def file_at(self, row):
        return self.files[self.indices[row]]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < self.rowCount():
            return None
        file = self.file_at(index.row())
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 1:
                return format_size(file.size)
            try:
                return str(Path(file.path).relative_to(self.root))
            except ValueError:
                return file.path
        if role == Qt.ItemDataRole.ToolTipRole:
            return exact_size(file.size) if index.column() == 1 else file.path
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 1:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return (tr("포함 파일 · 후보 안의 상대 경로"), tr("크기 (논리적)"))[section]
        return super().headerData(section, orientation, role)

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        self.sort_requested.emit(column, order)

    def set_indices(self, indices):
        self.beginResetModel()
        self.indices = indices
        self.endResetModel()


class IndexWorker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, files, query, column, order):
        super().__init__()
        self.files, self.query, self.column, self.order = files, query, column, order
        self.cancel = Event()

    def run(self):
        try:
            query = self.query.casefold()
            rows = []
            for index, file in enumerate(self.files):
                if self.cancel.is_set():
                    return
                if not query or query in file.path.casefold():
                    key = file.size if self.column == 1 else file.path.casefold()
                    rows.append((key, index))
            rows.sort(reverse=self.order == Qt.SortOrder.DescendingOrder)
            if not self.cancel.is_set():
                self.result.emit([index for _, index in rows])
        except Exception as exc:
            if not self.cancel.is_set():
                self.failed.emit(str(exc))


class ReviewDialog(QDialog):
    def __init__(self, review, reasons, can_execute, parent=None):
        super().__init__(parent)
        self.worker = None
        self.can_execute, self._view_failed = can_execute, False
        self._pending = False
        self._done_code = None
        self.column, self.order = 0, Qt.SortOrder.AscendingOrder
        self.setWindowTitle(tr("정리 검토 · 후보 폴더 전체"))
        self.setModal(True)
        self.resize(min(860, max(500, parent.width() - 24)) if parent else 860,
                    min(640, max(460, parent.height() - 32)) if parent else 640)
        layout = QVBoxLayout(self)
        self.target = QPlainTextEdit(review.candidate.path)
        self.target.setReadOnly(True)
        self.target.setMaximumHeight(65)
        layout.addWidget(QLabel(tr("정리 대상 폴더 · 전체 경로")))
        layout.addWidget(self.target)
        partial = bool(review.blocked)
        self.scope = QLabel(tr("확인한 목록: {count:,}개 · {size}{partial}").format(count=len(review.files), size=exact_size(sum(f.size for f in review.files)), partial=tr(" · 전체 목록/실행 조건 미확인") if partial else ""))
        self.scope.setWordWrap(True)
        layout.addWidget(self.scope)
        self.tabs = QTabWidget()
        files_page = QWidget()
        file_layout = QVBoxLayout(files_page)
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setMaxLength(512)
        self.search.setPlaceholderText(tr("확인한 포함 파일에서 이름·경로 검색"))
        file_layout.addWidget(self.search)
        self.count = QLabel()
        self.count.setTextFormat(Qt.TextFormat.PlainText)
        file_layout.addWidget(self.count)
        self.table = QTableView()
        self.model = IncludedModel(review, self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 130)
        self.table.horizontalHeader().setSortIndicator(0, self.order)
        self.table.setSortingEnabled(True)
        file_layout.addWidget(self.table, 1)
        self.selection = QPlainTextEdit()
        self.selection.setReadOnly(True)
        self.selection.setMaximumHeight(65)
        self.selection.setPlaceholderText(tr("행을 선택하면 전체 경로와 정확한 크기를 확인할 수 있습니다."))
        file_layout.addWidget(self.selection)
        self.tabs.addTab(files_page, tr("포함 파일"))
        self.conditions = QPlainTextEdit()
        self.conditions.setReadOnly(True)
        self.conditions.setPlainText(tr("분류 근거: {evidence}\n\n주의: {warning}\n\n재생성 조건: {regeneration}\n\n실행 조건:\n{reasons}\n\n논리적 파일 크기는 실제 디스크 사용량과 다를 수 있습니다. 휴지통 이동이 즉시 여유 공간 증가를 의미하지 않습니다.").format(evidence=review.candidate.evidence, warning=review.candidate.warning, regeneration=review.candidate.regeneration, reasons="\n".join(reasons) if reasons else tr("개별 검증 통과. 실행 직전에 다시 검증합니다.")))
        self.tabs.addTab(self.conditions, tr("근거·주의·실행 조건"))
        layout.addWidget(self.tabs, 1)
        hint = QLabel(tr("검색·파일 행 선택은 내용 확인용입니다. 이동 대상은 위의 후보 폴더 전체이며 개별 파일 선택 삭제가 아닙니다."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.confirmed = QCheckBox(tr("대상 폴더 전체와 재생성 조건을 확인했습니다."))
        self.confirmed.setChecked(False)
        self.confirmed.setEnabled(can_execute)
        layout.addWidget(self.confirmed)
        self.run_button = QPushButton(tr("③ 확인한 후보 폴더 1개를 휴지통으로 이동"))
        self.run_button.setObjectName("primary")
        self.run_button.setEnabled(False)
        self.confirmed.toggled.connect(lambda checked: self.run_button.setEnabled(checked and can_execute and not self._view_failed))
        if not can_execute:
            blocked = QLabel(tr("실행 제한 · '근거·주의·실행 조건' 탭에서 이유를 확인하세요."))
            blocked.setWordWrap(True)
            layout.addWidget(blocked)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("닫기"))
        buttons.rejected.connect(self.reject)
        actions = QHBoxLayout()
        actions.addWidget(self.run_button, 1)
        actions.addWidget(buttons)
        layout.addLayout(actions)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.request_indices)
        self.search.textChanged.connect(self.search_changed)
        self.model.sort_requested.connect(self.sort_changed)
        self.table.selectionModel().currentChanged.connect(self.selected)
        self.update_count()
        self.request_indices()

    def update_count(self):
        self.count.setText(tr("표시 {shown:,}개 / 확인한 목록 {total:,}개 · 검색은 실행 대상을 바꾸지 않습니다.").format(shown=self.model.rowCount(), total=len(self.model.files)))

    def selected(self, current, previous):
        if current.isValid():
            file = self.model.file_at(current.row())
            self.selection.setPlainText(file.path + "\n" + exact_size(file.size))
        else:
            self.selection.clear()

    def sort_changed(self, column, order):
        self.column, self.order = column, order
        self.request_indices()

    def search_changed(self):
        self._pending = False
        if self.worker:
            self.worker.cancel.set()
        self.count.setText(tr("검색 중… 실행 대상은 후보 폴더 전체입니다."))
        self.timer.start()

    def request_indices(self):
        self.timer.stop()
        if self._done_code is not None:
            return
        if self.worker:
            self._pending = True
            self.worker.cancel.set()
            return
        self._pending = False
        worker = IndexWorker(self.model.files, self.search.text(), self.column, self.order)
        self.worker = worker
        self.count.setText(tr("목록 검색·정렬 중…"))
        worker.result.connect(self.indices_ready)
        worker.failed.connect(self.indices_failed)
        worker.finished.connect(self.indices_finished)
        worker.start()

    def indices_ready(self, indices):
        if self._pending or self._done_code is not None or self.timer.isActive():
            return
        self.model.set_indices(indices)
        if self._view_failed:
            self.confirmed.setChecked(False)
        self._view_failed = False
        self.confirmed.setEnabled(self.can_execute)
        self.table.clearSelection()
        self.selection.clear()
        self.update_count()

    def indices_failed(self, message):
        if self._pending or self._done_code is not None or self.timer.isActive():
            return
        self._view_failed = True
        self.confirmed.setChecked(False)
        self.confirmed.setEnabled(False)
        self.run_button.setEnabled(False)
        self.count.setText(tr("목록 표시 실패: ") + message)

    def indices_finished(self):
        self.worker.deleteLater()
        self.worker = None
        if self._done_code is not None:
            super().done(self._done_code)
        elif self._pending:
            self.request_indices()

    def done(self, result):
        self.timer.stop()
        if self.worker:
            self._done_code = result
            self._pending = False
            self.worker.cancel.set()
            self.setEnabled(False)
        else:
            super().done(result)
