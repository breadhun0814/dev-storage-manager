"""Independent, cancellable read-only history queries."""
from threading import Event

from PySide6.QtCore import QThread, Signal

from dev_storage_manager.persistence.journal import Journal, HistoryCancelled


class HistoryWorker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, directory, offset=0, anchor=None, query="", job=None):
        super().__init__()
        self.directory, self.offset, self.anchor, self.query = directory, offset, anchor, query
        self.cancel = Event()
        self.job = job

    def run(self):
        journal = None
        try:
            if self.cancel.is_set():
                return
            journal = Journal(self.directory, read_only=True)
            page = journal.history_page(offset=self.offset, anchor=self.anchor, query=self.query, cancel=self.cancel, job=self.job)
            if not self.cancel.is_set():
                self.result.emit(page)
        except HistoryCancelled:
            pass
        except Exception as exc:
            if not self.cancel.is_set():
                self.failed.emit(str(exc))
        finally:
            if journal:
                journal.close()
