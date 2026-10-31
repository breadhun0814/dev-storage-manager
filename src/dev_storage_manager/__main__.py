from dev_storage_manager.i18n import tr, set_language
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from dev_storage_manager.platform.paths import data_dir
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.ui.application import configure_font
from PySide6.QtCore import QLockFile
from dev_storage_manager.persistence.journal import Journal


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DevStorageManager")
    if (len(sys.argv) == 3 and sys.argv[1] == "--self-test") or (len(sys.argv) == 4 and sys.argv[1] == "--self-test-language"):
        set_language(sys.argv[2] if len(sys.argv) == 4 else "ko")
        configure_font(app)
        from pathlib import Path
        from dev_storage_manager.platform.verification import verify_startup
        return verify_startup(app, Path(sys.argv[-1]).absolute())
    try:
        directory = data_dir()
        directory.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(directory / "application.lock"))
        if not lock.tryLock(0):
            QMessageBox.warning(None, tr('이미 실행 중'), tr('다른 개발 저장공간 관리자 창을 먼저 닫아주세요.'))
            return 1
        store = Store(directory)
        set_language(store.language())
        configure_font(app)
        # Module-level labels must be created after the saved language is loaded.
        from dev_storage_manager.ui.main_window import Window
        journal = Journal(directory)
        journal.recover()
        journal.close()
        window = Window(store)
    except Exception as exc:
        QMessageBox.critical(None, tr('시작 실패'), str(exc))
        return 1
    window.show()
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
