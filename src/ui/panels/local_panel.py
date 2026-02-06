"""Local file system panel using QFileSystemModel."""
import os
from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileSystemModel,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)


class LocalPanel(QWidget):
    """Panel displaying local file system with navigation."""

    file_selected = Signal(str)  # full path of selected file
    dir_changed = Signal(str)  # current directory changed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_dir = str(Path.home())
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Navigation bar
        nav = QHBoxLayout()
        self.btn_up = QPushButton("..")
        self.btn_up.setFixedWidth(30)
        self.btn_up.setToolTip("Go to parent directory")
        self.btn_up.clicked.connect(self._go_up)
        nav.addWidget(self.btn_up)

        self.path_edit = QLineEdit(self.current_dir)
        self.path_edit.returnPressed.connect(self._on_path_entered)
        nav.addWidget(self.path_edit)

        layout.addLayout(nav)

        # File system model
        self.model = QFileSystemModel()
        self.model.setRootPath(self.current_dir)
        self.model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)

        # Tree view
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(self.current_dir))
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        self.tree.doubleClicked.connect(self._on_double_clicked)

        # Hide unnecessary columns (keep Name, Size, Date Modified)
        self.tree.setColumnHidden(2, True)  # Type column

        layout.addWidget(self.tree)

    def _go_up(self):
        parent = str(Path(self.current_dir).parent)
        if parent != self.current_dir:
            self._navigate_to(parent)

    def _on_path_entered(self):
        path = self.path_edit.text().strip()
        if os.path.isdir(path):
            self._navigate_to(path)

    def _on_double_clicked(self, index: QModelIndex):
        path = self.model.filePath(index)
        if os.path.isdir(path):
            self._navigate_to(path)
        else:
            self.file_selected.emit(path)

    def _navigate_to(self, path: str):
        self.current_dir = path
        self.path_edit.setText(path)
        self.tree.setRootIndex(self.model.index(path))
        self.dir_changed.emit(path)

    def get_selected_paths(self) -> list[str]:
        """Return list of full paths for all selected items."""
        indexes = self.tree.selectionModel().selectedRows()
        return [self.model.filePath(idx) for idx in indexes]

    def get_current_dir(self) -> str:
        return self.current_dir
