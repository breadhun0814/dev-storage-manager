import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from dev_storage_manager.platform.paths import data_dir
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.ui.main_window import Window
from dev_storage_manager.ui.application import configure_font


def main():
    app = QApplication(sys.argv)
    configure_font(app)
    app.setApplicationName("DevStorageManager")
    try:
        window = Window(Store(data_dir()))
    except Exception as exc:
        QMessageBox.critical(None, "시작 실패", str(exc))
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
