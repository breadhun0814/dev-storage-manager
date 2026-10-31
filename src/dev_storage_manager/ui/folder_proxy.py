"""Compute folder filtering/sorting off the GUI thread; never read the disk."""
from threading import Event

from PySide6.QtCore import QAbstractProxyModel, QModelIndex, Qt, QThread, Signal, QTimer

from dev_storage_manager.detection.rules import CATEGORIES
from dev_storage_manager.ui.coverage_text import LABELS


class FolderIndexWorker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, folders, coverage, query, column, order, generation):
        super().__init__()
        self.folders, self.coverage = folders, coverage
        self.query, self.column, self.order, self.generation = query, column, order, generation
        self.cancel = Event()

    def run(self):
        try:
            query = self.query.casefold()
            rows = []
            for index, folder in enumerate(self.folders):
                if self.cancel.is_set():
                    return
                if query and query not in folder.path.casefold():
                    continue
                if self.column == 1:
                    key = folder.size
                elif self.column == 2:
                    key = folder.files
                elif self.column == 3:
                    key = CATEGORIES.get(folder.category, folder.category).casefold()
                elif self.column == 4:
                    key = LABELS[self.coverage.state(folder.path)]
                else:
                    key = folder.path.casefold() if self.column == 0 else index
                rows.append((key, index))
            if self.column >= 0:
                rows.sort(reverse=self.order == Qt.SortOrder.DescendingOrder)
            if self.cancel.is_set():
                return
            indices = [index for _, index in rows]
            reverse = {index: row for row, index in enumerate(indices)}
            if not self.cancel.is_set():
                self.result.emit((indices, reverse))
        except Exception as exc:
            if not self.cancel.is_set():
                self.failed.emit(str(exc))


class FolderProxy(QAbstractProxyModel):
    updated = Signal()
    idle = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.indices, self.reverse = range(0), None
        self.query, self.column, self.order = "", -1, Qt.SortOrder.AscendingOrder
        self.worker, self.error = None, ""
        self.generation, self.pending, self.closing = 0, False, False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.request)

    def setSourceModel(self, model):
        super().setSourceModel(model)
        if model is None:
            self.indices, self.reverse = range(0), None
            return
        model.modelAboutToBeReset.connect(self.source_resetting)
        model.modelReset.connect(self.source_reset)
        self.indices = range(model.rowCount())

    def source_resetting(self):
        self.generation += 1
        self.timer.stop()
        if self.worker:
            self.worker.cancel.set()
        self.beginResetModel()

    def source_reset(self):
        self.indices, self.reverse, self.error = range(self.sourceModel().rowCount()), None, ""
        self.endResetModel()
        self.request()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.indices)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() or self.sourceModel() is None else self.sourceModel().columnCount()

    def index(self, row, column, parent=QModelIndex()):
        return self.createIndex(row, column) if self.hasIndex(row, column, parent) else QModelIndex()

    def parent(self, index=QModelIndex()):
        return QModelIndex()

    def mapToSource(self, index):
        if not index.isValid() or not 0 <= index.row() < len(self.indices):
            return QModelIndex()
        return self.sourceModel().index(self.indices[index.row()], index.column())

    def mapFromSource(self, index):
        if not index.isValid():
            return QModelIndex()
        row = index.row() if self.reverse is None and index.row() < len(self.indices) else (self.reverse or {}).get(index.row(), -1)
        return self.index(row, index.column()) if row >= 0 else QModelIndex()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        source = self.mapToSource(index)
        return self.sourceModel().data(source, role) if source.isValid() else None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        return self.sourceModel().headerData(section, orientation, role)

    def setFilterFixedString(self, query):
        if query == self.query:
            return
        self.query = query
        self.pending = False
        if self.worker:
            self.worker.cancel.set()
        self.timer.start()
        self.updated.emit()

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        self.column, self.order = column, order
        self.request()

    def request(self):
        self.timer.stop()
        if self.closing:
            return
        if self.worker:
            self.pending = True
            self.worker.cancel.set()
            self.updated.emit()
            return
        self.pending, self.error = False, ""
        model = self.sourceModel()
        if model is None or not model.rowCount() or (not self.query and self.column < 0):
            self.beginResetModel()
            self.indices, self.reverse = range(model.rowCount() if model else 0), None
            self.endResetModel()
            self.updated.emit()
            return
        self.worker = FolderIndexWorker(model.folders, model.coverage, self.query, self.column, self.order, self.generation)
        self.worker.result.connect(self.ready)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finished)
        self.updated.emit()
        self.worker.start()

    def current_request(self):
        return (not self.closing and not self.pending and not self.timer.isActive() and self.worker is not None
                and self.worker.generation == self.generation and self.worker.query == self.query
                and self.worker.column == self.column and self.worker.order == self.order)

    def ready(self, packet):
        if self.current_request():
            self.beginResetModel()
            self.indices, self.reverse = packet
            self.endResetModel()
            self.updated.emit()

    def failed(self, message):
        if self.current_request():
            self.beginResetModel()
            self.indices, self.reverse, self.error = range(0), None, message
            self.endResetModel()
            self.updated.emit()

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        if self.pending and not self.closing:
            self.request()
        else:
            self.updated.emit()
            self.idle.emit()

    def shutdown(self):
        self.closing, self.pending = True, False
        self.timer.stop()
        if self.worker:
            self.worker.cancel.set()
