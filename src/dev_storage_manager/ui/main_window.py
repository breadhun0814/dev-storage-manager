from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QTabWidget, QHeaderView, QAbstractItemView,
    QPlainTextEdit, QInputDialog, QDialog, QDialogButtonBox)

from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.platform.paths import protected_paths
from dev_storage_manager.ui.strings import TITLE, STATUS, NOTICE
from dev_storage_manager.detection.rules import CATEGORIES
from dev_storage_manager.cleanup.review import inspect


def size_text(value):
    return f"{value:,} B ({value / 1024**2:,.2f} MiB)"


class Worker(QThread):
    progress = Signal(int, object, str)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, path, exclusions=None):
        super().__init__()
        self.path = path
        self.cancel = Event()
        self.exclusions = exclusions or []

    def run(self):
        try:
            self.result.emit(scan(Path(self.path), self.cancel, self.progress.emit, protected_paths(), self.exclusions))
        except Exception as exc:
            self.failed.emit(str(exc))


class ReviewWorker(QThread):
    progress = Signal(int, object, str)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, result, candidate):
        super().__init__()
        self.analysis, self.candidate = result, candidate
        self.cancel = Event()

    def run(self):
        try:
            self.result.emit(inspect(self.analysis, self.candidate, self.cancel,
                                     self.progress.emit, protected_paths()))
        except Exception as exc:
            self.failed.emit(str(exc))


class Window(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store, self.worker, self.active_path = store, None, None
        self.setWindowTitle(TITLE)
        self.resize(1150, 780)
        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        layout.addWidget(QLabel("프로젝트를 등록하고 분석하세요. 모든 분석은 읽기 전용입니다."))
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        self.add = QPushButton("폴더 추가")
        self.start = QPushButton("선택 프로젝트 분석")
        self.remove = QPushButton("목록에서 제거")
        self.exclude = QPushButton("분석 제외 목록")
        self.stop = QPushButton("분석 취소")
        self.stop.setEnabled(False)
        cleanup = QPushButton("휴지통으로 이동 · 준비 중")
        cleanup.setEnabled(False)
        for button in (self.add, self.start, self.remove, self.exclude, self.stop, cleanup):
            buttons.addWidget(button)
        self.projects = QTableWidget(0, 4)
        self.projects.setHorizontalHeaderLabels(["프로젝트", "경로", "마지막 분석", "상태"])
        self.projects.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.projects.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.projects.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.projects.setColumnWidth(0, 170)
        self.projects.setColumnWidth(2, 190)
        self.projects.setColumnWidth(3, 240)
        self.projects.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.projects.setMaximumHeight(220)
        layout.addWidget(self.projects)
        self.summary = QLabel("아직 분석 결과가 없습니다.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        notice = QLabel(NOTICE)
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.search = QLineEdit()
        self.search.setPlaceholderText("폴더 경로 검색 (표시만 필터링)")
        layout.addWidget(self.search)
        tabs = QTabWidget()
        self.folders = QTreeWidget()
        self.folders.setHeaderLabels(["폴더 (하위 항목 포함 · 행끼리 합산하지 마세요)", "논리적 바이트", "파일 수"])
        self.folders.setSortingEnabled(True)
        self.folders.setColumnWidth(0, 700)
        self.issues = QTreeWidget()
        self.issues.setHeaderLabels(["읽기 실패 / 제외 경로", "이유"])
        self.issues.setColumnWidth(0, 600)
        self.candidates = QTreeWidget()
        self.candidates.setHeaderLabels(["정리 후보 (자동 선택 없음)", "분류", "논리적 바이트", "지원 상태"])
        self.candidates.setColumnWidth(0, 520)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("후보를 선택하면 근거·주의사항·재생성 조건을 표시합니다. 아직 정리 실행은 지원하지 않습니다.")
        candidate_page = QWidget()
        candidate_layout = QVBoxLayout(candidate_page)
        candidate_layout.addWidget(self.candidates)
        self.review_button = QPushButton("선택 후보의 포함 파일·변경 여부 검토")
        candidate_layout.addWidget(self.review_button)
        self.review_button.clicked.connect(self.start_review)
        candidate_layout.addWidget(self.details)
        tabs.addTab(candidate_page, "프로젝트·정리 후보")
        tabs.addTab(self.folders, "폴더별 용량")
        tabs.addTab(self.issues, "오류·제외 범위")
        layout.addWidget(tabs)
        self.add.clicked.connect(self.add_project)
        self.start.clicked.connect(self.start_scan)
        self.remove.clicked.connect(self.remove_project)
        self.exclude.clicked.connect(self.edit_exclusions)
        self.candidates.currentItemChanged.connect(self.candidate_selected)
        self.stop.clicked.connect(self.cancel_scan)
        self.projects.itemSelectionChanged.connect(self.open_result)
        self.search.textChanged.connect(self.filter_rows)
        self.refresh()

    def selected(self):
        row = self.projects.currentRow()
        return self.projects.item(row, 1).text() if row >= 0 else None

    def refresh(self, select=None):
        self.projects.setRowCount(0)
        for path, updated, status in self.store.projects():
            row = self.projects.rowCount()
            self.projects.insertRow(row)
            for col, value in enumerate((Path(path).name, path, updated or "—", STATUS.get(status, status))):
                self.projects.setItem(row, col, QTableWidgetItem(value))
            if path == select:
                self.projects.selectRow(row)

    def add_project(self):
        folder = QFileDialog.getExistingDirectory(self, "프로젝트 폴더 선택")
        if folder:
            path = str(Path(folder).absolute())
            self.store.add(path)
            self.refresh(path)

    def remove_project(self):
        path = self.selected()
        if path:
            self.store.remove(path)
            self.refresh()
            self.folders.clear()
            self.issues.clear()
            self.summary.setText("목록에서 제거했습니다. 실제 폴더는 변경하지 않았습니다.")

    def start_scan(self):
        path = self.selected()
        if not path or self.worker:
            return
        self.active_path = path
        self.store.status(path, "running")
        self.refresh(path)
        self.set_busy(True)
        self.worker = Worker(path, self.store.exclusions(path))
        self.worker.progress.connect(self.show_progress)
        self.worker.result.connect(self.scan_result)
        self.worker.failed.connect(self.scan_failed)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def set_busy(self, busy):
        for widget in (self.add, self.start, self.remove, self.exclude, self.projects, self.review_button):
            widget.setEnabled(not busy)
        self.stop.setEnabled(busy)

    def cancel_scan(self):
        if self.worker:
            self.worker.cancel.set()
            self.stop.setEnabled(False)
            self.summary.setText("취소 요청 중 · 현재 파일 시스템 호출이 끝나면 중단합니다.")

    def show_progress(self, files, size, path):
        self.summary.setText(f"분석 중 · {files:,}개 파일 · {size_text(size)}\n{path}")

    def scan_result(self, result):
        self.store.save(result)
        self.refresh(self.active_path)
        self.display(result)

    def scan_failed(self, message):
        self.store.status(self.active_path, "failed")
        self.refresh(self.active_path)
        self.folders.clear()
        self.issues.clear()
        self.summary.setText("분석 실패 · 현재 결과 없음 · " + message)
        QMessageBox.warning(self, "분석 실패", message)

    def worker_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)

    def open_result(self):
        path = self.selected()
        self.folders.clear()
        self.issues.clear()
        self.candidates.clear()
        self.details.clear()
        result = self.store.load(path) if path else None
        if result:
            self.display(result)
            status = next((s for p, _, s in self.store.projects() if p == path), None)
            if status != result.status:
                self.summary.setText("최근 시도: " + STATUS.get(status, str(status)) +
                                     " · 아래는 이전 저장 결과입니다.\n" + self.summary.text())
        else:
            self.summary.setText("저장된 분석 결과가 없습니다.")

    def display(self, result):
        self.folders.clear()
        self.issues.clear()
        self.candidates.clear()
        self.details.clear()
        self.summary.setText(f"{result.root}\n{STATUS[result.status]} · 확인된 {result.files:,}개 파일 · {size_text(result.size)} · 오류/제외 {len(result.issues):,}건")
        self.folders.setSortingEnabled(False)
        for folder in result.folders:
            item = NumericItem([folder.path, str(folder.size), str(folder.files)])
            item.setToolTip(0, CATEGORIES.get(folder.category, folder.category))
            self.folders.addTopLevelItem(item)
        self.folders.setSortingEnabled(True)
        for issue in result.issues:
            self.issues.addTopLevelItem(QTreeWidgetItem([issue.path, ("읽기 오류: " if issue.error else "제외: ") + issue.reason]))
        for candidate in result.candidates:
            item = QTreeWidgetItem([candidate.path, CATEGORIES[candidate.kind], str(candidate.size), "검토만 · 정리 미지원"])
            item.setData(0, Qt.ItemDataRole.UserRole, candidate)
            self.candidates.addTopLevelItem(item)
        projects = "\n".join(f"{p.kind}: {p.path} · {', '.join(p.markers)}" for p in result.projects)
        self.details.setPlainText("확인된 프로젝트 표식\n" + (projects or "표식 없음 · 일반 폴더로 분석") +
                                  "\n\n후보는 삭제 가능 판정이 아닙니다. 폴더 이름만으로 후보를 만들지 않습니다.")
        self.filter_rows()

    def candidate_selected(self, item, previous):
        if item is None:
            return
        candidate = item.data(0, Qt.ItemDataRole.UserRole)
        if candidate:
            self.details.setPlainText(f"정확한 대상: {candidate.path}\n논리적 파일 크기: {size_text(candidate.size)} · {candidate.files:,}개 파일\n\n근거: {candidate.evidence}\n\n주의: {candidate.warning}\n\n재생성 조건: {candidate.regeneration}\n\n현재 지원: 검토만 가능. 휴지통 이동은 비활성화되어 있습니다.")

    def start_review(self):
        item = self.candidates.currentItem()
        if not item or self.worker:
            return
        result = self.store.load(self.selected())
        if not result:
            return
        self.set_busy(True)
        self.worker = ReviewWorker(result, item.data(0, Qt.ItemDataRole.UserRole))
        self.worker.progress.connect(self.show_progress)
        self.worker.failed.connect(lambda text: QMessageBox.warning(self, "검토 실패", text))
        self.worker.result.connect(self.show_review)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def show_review(self, review):
        self.summary.setText("후보 검토 완료 · " + review.candidate.path)
        dialog = QDialog(self)
        dialog.setWindowTitle("정리 검토 · 읽기 전용")
        dialog.resize(1000, 650)
        layout = QVBoxLayout(dialog)
        label = QLabel(f"대상: {review.candidate.path}\n포함 {len(review.files):,}개 파일 · {size_text(sum(f.size for f in review.files))}\n분류 근거: {review.candidate.evidence}\n주의: {review.candidate.warning}\n재생성: {review.candidate.regeneration}")
        label.setWordWrap(True)
        layout.addWidget(label)
        blocked = QLabel("실행 제한:\n" + "\n".join(review.blocked))
        blocked.setWordWrap(True)
        layout.addWidget(blocked)
        tree = QTreeWidget()
        tree.setHeaderLabels(["정확한 포함 파일 경로", "논리적 바이트"])
        tree.setColumnWidth(0, 770)
        tree.addTopLevelItems([QTreeWidgetItem([f.path, str(f.size)]) for f in review.files])
        layout.addWidget(tree)
        execute = QPushButton("휴지통으로 이동 · 검증 전 비활성")
        execute.setEnabled(False)
        layout.addWidget(execute)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.open()
        self.review_dialog = dialog

    def edit_exclusions(self):
        path = self.selected()
        if not path:
            return
        text, accepted = QInputDialog.getMultiLineText(self, "분석 제외 목록", "프로젝트 기준 상대 경로를 한 줄에 하나씩 입력하세요.\n예: data 또는 assets/cache · 와일드카드 미지원\n변경 사항은 다음 분석부터 적용됩니다.", "\n".join(self.store.exclusions(path)))
        if accepted:
            try:
                self.store.set_exclusions(path, list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip())))
                self.summary.setText("제외 목록을 저장했습니다. 적용하려면 다시 분석하세요.")
            except ValueError as exc:
                QMessageBox.warning(self, "제외 경로 오류", str(exc))

    def filter_rows(self):
        query = self.search.text().casefold()
        for i in range(self.folders.topLevelItemCount()):
            item = self.folders.topLevelItem(i)
            item.setHidden(query not in item.text(0).casefold())

    def closeEvent(self, event):
        if self.worker:
            self.cancel_scan()
            self.summary.setText("분석 취소 중입니다. 중단 후 창을 다시 닫아주세요.")
            event.ignore()
        else:
            self.store.close()
            event.accept()


class NumericItem(QTreeWidgetItem):
    def __lt__(self, other):
        col = self.treeWidget().sortColumn()
        return int(self.text(col)) < int(other.text(col)) if col in (1, 2) else self.text(col) < other.text(col)
