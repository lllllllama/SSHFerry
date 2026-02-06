"""Remote file panel for displaying remote directory contents."""

from PySide6.QtCore import QByteArray, QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.shared.models import RemoteEntry


class DraggableTableWidget(QTableWidget):
    """TableWidget with drag support for remote file entries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)

    def startDrag(self, supportedActions):
        """Start a drag operation with remote paths."""
        selected_rows = set(idx.row() for idx in self.selectedIndexes())
        if not selected_rows:
            return

        # Collect remote paths from selected rows
        paths = []
        for row in selected_rows:
            name_item = self.item(row, 0)
            if name_item:
                entry = name_item.data(Qt.UserRole)
                if entry:
                    paths.append(entry.path)

        if not paths:
            return

        # Create custom MIME data for remote paths
        mime_data = QMimeData()
        data = "\n".join(paths).encode("utf-8")
        mime_data.setData("application/x-sshferry-remote", QByteArray(data))

        # Start drag
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.CopyAction)


class RemotePanel(QWidget):
    """Panel for displaying and navigating remote directory contents with drag-drop support."""

    path_changed = Signal(str)  # Emitted when current path changes
    entry_activated = Signal(RemoteEntry)  # Emitted when entry is double-clicked

    # File operation requests (handled by MainWindow)
    request_go_up = Signal()
    request_refresh = Signal()
    request_mkdir = Signal(str)  # new dir name
    request_delete = Signal(RemoteEntry)
    request_rename = Signal(RemoteEntry, str)  # entry, new_name
    request_upload = Signal()  # upload selected local files to current remote dir
    request_upload_paths = Signal(list)  # upload specific local paths (from drag-drop)
    request_download = Signal(RemoteEntry)
    request_download_paths = Signal(list)  # download remote paths (from drag-drop)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_path = "/"
        self.entries: list[RemoteEntry] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Navigation bar
        nav = QHBoxLayout()

        self.btn_up = QPushButton("..")
        self.btn_up.setFixedWidth(30)
        self.btn_up.setToolTip("Go to parent directory")
        self.btn_up.clicked.connect(lambda: self.request_go_up.emit())
        nav.addWidget(self.btn_up)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setFixedWidth(60)
        self.btn_refresh.clicked.connect(lambda: self.request_refresh.emit())
        nav.addWidget(self.btn_refresh)

        self.path_label = QLabel("Remote: /")
        self.path_label.setStyleSheet("font-weight: bold; padding: 2px 5px;")
        nav.addWidget(self.path_label, stretch=1)

        layout.addLayout(nav)

        # File table with drag support
        self.table = DraggableTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Size", "Modified"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)

        # Enable drop for receiving files from local panel
        self.setAcceptDrops(True)

        layout.addWidget(self.table)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_path(self, path: str):
        self.current_path = path
        self.path_label.setText(f"Remote: {path}")
        self.path_changed.emit(path)

    def set_entries(self, entries: list[RemoteEntry]):
        self.entries = sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))
        self.table.setRowCount(len(self.entries))

        for row, entry in enumerate(self.entries):
            name_item = QTableWidgetItem(entry.name)
            name_item.setData(Qt.UserRole, entry)
            if entry.is_dir:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
            self.table.setItem(row, 0, name_item)

            type_item = QTableWidgetItem("DIR" if entry.is_dir else "FILE")
            self.table.setItem(row, 1, type_item)

            size_str = self._format_size(entry.size) if not entry.is_dir else ""
            size_item = QTableWidgetItem(size_str)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, size_item)

            mtime_str = entry.mtime_datetime.strftime("%Y-%m-%d %H:%M:%S")
            self.table.setItem(row, 3, QTableWidgetItem(mtime_str))

        self.table.resizeColumnsToContents()

    def clear(self):
        self.table.setRowCount(0)
        self.entries = []

    def get_selected_entries(self) -> list[RemoteEntry]:
        """Return all selected RemoteEntry objects."""
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        result = []
        for row in sorted(rows):
            item = self.table.item(row, 0)
            if item:
                entry = item.data(Qt.UserRole)
                if entry:
                    result.append(entry)
        return result

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos):
        menu = QMenu(self)

        act_refresh = menu.addAction("Refresh")
        act_refresh.triggered.connect(lambda: self.request_refresh.emit())

        menu.addSeparator()

        act_upload = menu.addAction("Upload here...")
        act_upload.triggered.connect(lambda: self.request_upload.emit())

        selected = self.get_selected_entries()

        if len(selected) == 1:
            entry = selected[0]
            if not entry.is_dir:
                act_dl = menu.addAction("Download")
                act_dl.triggered.connect(lambda: self.request_download.emit(entry))
            else:
                act_dl = menu.addAction("Download folder")
                act_dl.triggered.connect(lambda: self.request_download.emit(entry))

            menu.addSeparator()

            act_rename = menu.addAction("Rename")
            act_rename.triggered.connect(lambda: self._prompt_rename(entry))

            act_delete = menu.addAction("Delete")
            act_delete.triggered.connect(lambda: self._confirm_delete(entry))

        menu.addSeparator()
        act_mkdir = menu.addAction("New Folder")
        act_mkdir.triggered.connect(self._prompt_mkdir)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _prompt_mkdir(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            self.request_mkdir.emit(name.strip())

    def _prompt_rename(self, entry: RemoteEntry):
        new_name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=entry.name
        )
        if ok and new_name.strip() and new_name.strip() != entry.name:
            self.request_rename.emit(entry, new_name.strip())

    def _confirm_delete(self, entry: RemoteEntry):
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete '{entry.name}'?\n\nThis operation is restricted to the sandbox directory.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.request_delete.emit(entry)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_item_double_clicked(self, item: QTableWidgetItem):
        row = item.row()
        name_item = self.table.item(row, 0)
        if name_item:
            entry = name_item.data(Qt.UserRole)
            if entry:
                self.entry_activated.emit(entry)

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    # ------------------------------------------------------------------
    # Drag-drop support for receiving uploads from LocalPanel
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event):
        """Accept drag events with file URLs."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Accept drag move events with file URLs."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Handle dropped files - emit upload request."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
            if paths:
                self.request_upload_paths.emit(paths)
            event.acceptProposedAction()

