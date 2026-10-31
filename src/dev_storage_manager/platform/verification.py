"""Startup/worker smoke verification using only self-created temporary data."""
from dev_storage_manager.i18n import tr, get_language
import json
from pathlib import Path
import tempfile
from time import monotonic

from PySide6.QtCore import QEventLoop, QTimer, Qt
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.persistence.journal import Journal
from dev_storage_manager.ui.main_window import Window
from dev_storage_manager.cleanup.review import Review, IncludedFile
from dev_storage_manager.domain.models import Candidate, Result, Folder, Issue
from dev_storage_manager.ui.folder_model import FolderModel
from dev_storage_manager.domain.cleanup_result import CleanupReport
from dev_storage_manager.ui.cleanup_result_dialog import CleanupResultDialog
from dev_storage_manager.demo.project import create_demo, SOURCE, GIT_SENTINEL
from dev_storage_manager.cleanup.service import prepare
from dev_storage_manager.scanning.scanner import scan


def verify_startup(app, report_path: Path):
    with tempfile.TemporaryDirectory(prefix="dsm-selftest-", dir=report_path.parent) as temporary:
        demo = create_demo(Path(temporary))
        demo_result = scan(demo)
        demo_candidates = [c for c in demo_result.candidates if c.kind == "python-cache"]
        demo_valid = demo_result.status == "complete" and len(demo_candidates) == 1
        if demo_valid:
            demo_valid = bool(prepare(demo_result, demo_candidates[0]).proof)
        demo_valid = demo_valid and (demo / "demo_owned.py").read_bytes() == SOURCE and (demo / ".git/KEEP.txt").read_bytes() == GIT_SENTINEL
        partial_model = FolderModel()
        partial_model.set_result(Result(str(demo), status="incomplete", folders=[Folder(str(demo))],
                                        issues=[Issue(str(demo), tr("표시 자체 검사 · 실제 권한 거부 아님"), True)]))
        partial_unknown = partial_model.data(partial_model.index(0, 1)) == "—" and partial_model.data(partial_model.index(0, 2)) == "—"
        root = Path(temporary) / '한글 Việt 日本語 中文 시험 프로젝트'
        root.mkdir()
        (root / "pyproject.toml").write_bytes(b"[project]\nname = 'fixture'\n")
        (root / "source.py").write_bytes(b"fixture = 42\n")
        store = Store(Path(temporary) / "appdata")
        store.add(str(root))
        journal = Journal(store.directory)
        history_path = str(root / "never-created-cache")
        job = journal.begin([(history_path, 0)], None)
        journal.item(job, history_path, "cancelled", tr("자체 검사: 파일 작업 없이 취소한 임시 기록."))
        journal.finish(job, "cancelled", None)
        cancelled_result = journal.job_result(job)
        journal.close()
        window = Window(store)
        window.projects.selectRow(0)
        window.show()
        window.start_scan()
        loop = QEventLoop()
        window.worker.finished.connect(loop.quit)
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        app.processEvents()
        if window.history_worker is not None:
            history_loop = QEventLoop()
            window.history_worker.finished.connect(history_loop.quit)
            QTimer.singleShot(10000, history_loop.quit)
            history_loop.exec()
            app.processEvents()
        result = store.load(str(root))
        history_rows = window.history.topLevelItemCount()
        history_status = window.history_page.records[0][3] if window.history_page and window.history_page.records else None
        passed = (demo_valid and partial_unknown and window.worker is None and result is not None and result.status == "complete" and result.files == 2
                  and result.file_sample_available and len(result.largest_files) == 2
                  and window.file_proxy.rowCount() == 2 and not window.cleanup_ready and not window.qualified_kinds
                  and window.history_worker is None and history_rows == 1 and history_status == "cancelled"
                  and history_path in window.history_details.toPlainText())
        content_rows = None
        folder_query_verified = False
        if passed:
            def wait_folder_query():
                deadline = monotonic() + 10
                while window.folder_proxy.worker is not None or window.folder_proxy.timer.isActive():
                    if monotonic() > deadline:
                        return False
                    query_loop = QEventLoop()
                    QTimer.singleShot(5, query_loop.quit)
                    query_loop.exec()
                    app.processEvents()
                return not window.folder_proxy.error
            window.folder_proxy.setFilterFixedString("never-match-selftest-folder")
            filtered = wait_folder_query() and window.folder_proxy.rowCount() == 0
            window.folder_proxy.setFilterFixedString("")
            window.folder_proxy.sort(1, Qt.SortOrder.DescendingOrder)
            folder_query_verified = wait_folder_query() and filtered and window.folder_proxy.rowCount() == 1
            passed = passed and folder_query_verified
        if passed:
            window.browse_selected_folder()
            browser_loop = QEventLoop()
            window.worker.finished.connect(browser_loop.quit)
            QTimer.singleShot(10000, browser_loop.quit)
            browser_loop.exec()
            app.processEvents()
            if window.worker is None and window.browser is not None:
                content_rows = window.browser.model.rowCount()
            passed = window.worker is None and content_rows == 2
        review_rows, review_cleanup_enabled = None, None
        if passed:
            if window.browser is not None:
                window.browser.reject()
                app.processEvents()
            candidate = Candidate(str(root), "display-fixture", result.size, result.files,
                                  tr("읽기 전용 표시 자체 검사"), tr("시험 자료이며 정리하지 않습니다."), tr("명령을 실행하지 않습니다."))
            review = Review(str(root), candidate, [IncludedFile(f.path, f.size) for f in result.largest_files], "fixture", [])
            window.show_review((review, None))
            dialog = window.review_dialog
            if dialog.worker is not None:
                review_loop = QEventLoop()
                dialog.worker.finished.connect(review_loop.quit)
                QTimer.singleShot(10000, review_loop.quit)
                review_loop.exec()
                app.processEvents()
            review_rows = dialog.model.rowCount()
            review_cleanup_enabled = dialog.run_button.isEnabled()
            passed = (dialog.worker is None and review_rows == 2 and not review_cleanup_enabled
                      and not dialog.confirmed.isChecked() and not dialog.table.selectionModel().hasSelection())
            if dialog.worker is not None:
                dialog.worker.cancel.set()
                dialog.worker.wait()
                app.processEvents()
            dialog.reject()
            app.processEvents()
        result_read_only = False
        if passed:
            window.show_cleanup_history(job)
            if window.history_worker is not None:
                outcome_loop = QEventLoop()
                window.history_worker.finished.connect(outcome_loop.quit)
                QTimer.singleShot(10000, outcome_loop.quit)
                outcome_loop.exec()
                app.processEvents()
            outcome_dialog = CleanupResultDialog(CleanupReport(str(root), history_path, job, cancelled_result), window)
            outcome_dialog.show()
            app.processEvents()
            result_read_only = outcome_dialog.details.isReadOnly()
            passed = (window.history_worker is None and window.history_page is not None and window.history_page.job == job
                      and window.history_page.total == 1 and result_read_only
                      and outcome_dialog.headline.text() == tr("실행 전 취소"))
            outcome_dialog.reject()
        from dev_storage_manager.platform.diagnostics import runtime_info
        record = {"passed": passed, "runtime": runtime_info(), "language": get_language(),
                  "window_title": window.windowTitle(), "add_folder_label": window.add.text(),
                  "english_fallback_sample": tr("휴지통 작업 실패/취소 또는 결과 미확정"),
                  "analysis_status": result.status if result else None,
                  "files": result.files if result else None,
                  "logical_bytes": result.size if result else None,
                  "ui_folder_rows": window.folder_proxy.rowCount(),
                  "project_kind": result.projects[0].kind if result and result.projects else None,
                  "large_file_rows": window.file_proxy.rowCount(),
                  "folder_content_rows": content_rows,
                  "history_rows": history_rows,
                  "history_item_status": history_status,
                  "review_rows": review_rows,
                  "review_cleanup_enabled": review_cleanup_enabled,
                  "cleanup_result_status": cancelled_result.status,
                  "cleanup_result_read_only": result_read_only,
                  "demo_files": demo_result.files,
                  "demo_candidates": len(demo_candidates),
                  "demo_proof_verified": demo_valid,
                  "partial_zero_displayed_as_unknown": partial_unknown,
                  "folder_query_verified": folder_query_verified,
                  "cleanup_enabled": window.cleanup_ready,
                  "qualified_kinds": sorted(window.qualified_kinds)}
        if window.worker is not None:
            window.worker.cancel.set()
            window.worker.wait()
            app.processEvents()
        if window.history_worker is not None:
            window.history_worker.cancel.set()
            window.history_worker.wait()
            app.processEvents()
        if window.browser is not None:
            window.browser.reject()
        window.grab().save(str(report_path.with_suffix(".png")))
        window.close()
        with report_path.open("x", encoding="utf-8") as report:
            json.dump(record, report, ensure_ascii=False, indent=2)
        return 0 if passed else 1
