import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtWidgets import QApplication
from dev_storage_manager.domain.models import Folder
from dev_storage_manager.ui.folder_model import FolderModel


def test_numeric_sort_and_literal_path_search():
    app = QApplication.instance() or QApplication([])
    model = FolderModel()
    model.set_folders([Folder("C:/프로젝트/A[1]", 100, 1), Folder("C:/프로젝트/B", 2, 10)])
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.setSortRole(Qt.ItemDataRole.UserRole)
    proxy.setFilterKeyColumn(0)
    proxy.sort(1, Qt.SortOrder.AscendingOrder)
    assert proxy.data(proxy.index(0, 1), Qt.ItemDataRole.UserRole) == 2
    assert proxy.data(proxy.index(0, 1)) == "2 B"
    proxy.setFilterFixedString("A[1]")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 1), Qt.ItemDataRole.UserRole) == 100


def test_relative_labels_preserve_exact_paths_for_search_and_tooltip():
    app = QApplication.instance() or QApplication([])
    model = FolderModel()
    root = "C:/한국어 프로젝트"
    full = root + "/src/cache"
    model.set_folders([Folder(root, 100, 1), Folder(full, 100, 1)], root)
    assert model.data(model.index(1, 0)) != full
    assert model.data(model.index(1, 0), Qt.ItemDataRole.ToolTipRole) == full
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.setFilterRole(Qt.ItemDataRole.UserRole)
    proxy.setFilterKeyColumn(0)
    proxy.setFilterFixedString(full)
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 0), Qt.ItemDataRole.UserRole) == full
