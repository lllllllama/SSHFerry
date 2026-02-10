"""Local file system panel using QFileSystemModel."""
import os
import sys
from pathlib import Path

from PySide6.QtCore import QDir, QMimeData, QModelIndex, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)


def get_available_drives() -> list[str]:
    """Get list of available drive letters on Windows."""
    if sys.platform != "win32":
        return ["/"]
    
    drives = []
    try:
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if bitmask & 1:
                drives.append(f"{letter}:/")
            bitmask >>= 1
    except Exception:
        # Fallback: check common drive letters
        for letter in "CDEFGHIJ":
            drive = f"{letter}:/"
            if os.path.exists(drive):
                drives.append(drive)
    
    return drives if drives else ["C:/"]


class DraggableTreeView(QTreeView):
    """TreeView with drag support for file paths."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)

    def startDrag(self, supportedActions):
        """Start a drag operation with file URLs."""
        indexes = self.selectedIndexes()
        if not indexes:
            return

        # Get unique file paths from selected rows
        model = self.model()
        paths = set()
        for idx in indexes:
            if idx.column() == 0:  # Only process first column to avoid duplicates
                path = model.filePath(idx)
                if path:
                    paths.add(path)

        if not paths:
            return

        # Create mime data with file URLs
        mime_data = QMimeData()
        urls = [QUrl.fromLocalFile(p) for p in paths]
        mime_data.setUrls(urls)

        # Start drag
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        first_name = os.path.basename(next(iter(paths)))
        label = first_name if len(paths) == 1 else f"{len(paths)} items"
        drag.setPixmap(self._build_drag_pixmap(label))
        drag.exec(Qt.CopyAction)

    @staticmethod
    def _build_drag_pixmap(label: str) -> QPixmap:
        """Create non-null drag pixmap to avoid Qt null-pixmap scaling warnings."""
        width = min(360, max(140, 24 + len(label) * 7))
        height = 28
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(0, 120, 212, 220))
        painter.setPen(QColor(0, 120, 212, 240))
        painter.drawRoundedRect(0, 0, width - 1, height - 1, 6, 6)
        painter.setPen(QColor("white"))
        painter.drawText(10, 19, label)
        painter.end()
        return pixmap


class LocalPanel(QWidget):
    """Panel displaying local file system with navigation and drag support."""

    file_selected = Signal(str)  # full path of selected file
    dir_changed = Signal(str)  # current directory changed
    files_dropped = Signal(list)  # files dropped from remote (for download)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_dir = str(Path.home())
        self._drag_anim_phase = 0
        self._drag_anim_active = False
        self._drag_colors = ["#cce4f7", "#a9dcff"]
        self._drag_timer = QTimer(self)
        self._drag_timer.timeout.connect(self._on_drag_anim_tick)
        self._base_tree_style = ""
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("Local"))
        header.addStretch()
        layout.addLayout(header)

        # Navigation bar
        nav = QHBoxLayout()
        
        # Drive selector (Windows)
        self.drive_combo = QComboBox()
        self.drive_combo.setFixedWidth(60)
        self.drive_combo.setToolTip("Select drive")
        self._populate_drives()
        self.drive_combo.currentTextChanged.connect(self._on_drive_changed)
        nav.addWidget(self.drive_combo)
        
        self.btn_up = QPushButton("..")
        self.btn_up.setFixedWidth(30)
        self.btn_up.setToolTip("Go to parent directory")
        self.btn_up.clicked.connect(self._go_up)
        nav.addWidget(self.btn_up)

        self.btn_refresh = QPushButton("⟳")
        self.btn_refresh.setFixedWidth(30)
        self.btn_refresh.setToolTip("Refresh")
        self.btn_refresh.clicked.connect(self._refresh)
        nav.addWidget(self.btn_refresh)

        self.path_edit = QLineEdit(self.current_dir)
        self.path_edit.returnPressed.connect(self._on_path_entered)
        nav.addWidget(self.path_edit)

        layout.addLayout(nav)

        # File system model
        self.model = QFileSystemModel()
        self.model.setRootPath(self.current_dir)
        self.model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)

        # Draggable tree view
        self.tree = DraggableTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(self.current_dir))
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        self.tree.doubleClicked.connect(self._on_double_clicked)

        # Hide unnecessary columns (keep Name, Size, Date Modified)
        self.tree.setColumnHidden(2, True)  # Type column
        self._base_tree_style = self.tree.styleSheet()

        # Enable drop for receiving files from remote
        self.setAcceptDrops(True)

        layout.addWidget(self.tree)

    def _go_up(self):
        parent = str(Path(self.current_dir).parent)
        if parent != self.current_dir:
            self._navigate_to(parent)

    def _refresh(self):
        """Refresh the current directory view."""
        # Force model to refresh
        self.model.setRootPath("")
        self.model.setRootPath(self.current_dir)
        self.tree.setRootIndex(self.model.index(self.current_dir))

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
        # Sync drive combo selection
        self._sync_drive_combo()

    def _populate_drives(self):
        """Populate drive selector with available drives."""
        self.drive_combo.blockSignals(True)
        self.drive_combo.clear()
        drives = get_available_drives()
        for drive in drives:
            self.drive_combo.addItem(drive.rstrip("/"))
        # Select current drive
        self._sync_drive_combo()
        self.drive_combo.blockSignals(False)

    def _sync_drive_combo(self):
        """Sync drive combo to current directory."""
        if sys.platform == "win32" and len(self.current_dir) >= 2:
            drive = self.current_dir[:2].upper()
            idx = self.drive_combo.findText(drive)
            if idx >= 0:
                self.drive_combo.blockSignals(True)
                self.drive_combo.setCurrentIndex(idx)
                self.drive_combo.blockSignals(False)

    def _on_drive_changed(self, drive: str):
        """Navigate to selected drive root."""
        if drive:
            drive_path = f"{drive}/"
            if os.path.isdir(drive_path):
                self._navigate_to(drive_path)

    def get_selected_paths(self) -> list[str]:
        """Return list of full paths for all selected items."""
        indexes = self.tree.selectionModel().selectedRows()
        return [self.model.filePath(idx) for idx in indexes]

    def get_current_dir(self) -> str:
        return self.current_dir

    # Drag-drop support for receiving downloads
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-sshferry-remote"):
            self._start_drag_animation()
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-sshferry-remote"):
            self._set_drag_target_from_pos(event.pos())
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._stop_drag_animation()
        event.accept()

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-sshferry-remote"):
            data = event.mimeData().data("application/x-sshferry-remote")
            paths = data.data().decode("utf-8").split("\n")
            self.files_dropped.emit(paths)
            self._stop_drag_animation()
            event.acceptProposedAction()

    def _target_index_from_pos(self, panel_pos):
        """Map panel coordinates to tree index for directory target."""
        viewport_pos = self.tree.viewport().mapFrom(self, panel_pos)
        idx = self.tree.indexAt(viewport_pos)
        if not idx.isValid():
            return self.tree.rootIndex()

        path = self.model.filePath(idx)
        if os.path.isfile(path):
            return idx.parent()
        return idx

    def _set_drag_target_from_pos(self, panel_pos):
        """Highlight hovered target directory during drag."""
        idx = self._target_index_from_pos(panel_pos)
        if idx.isValid():
            self.tree.setCurrentIndex(idx)
            self._start_drag_animation()

    def _start_drag_animation(self):
        """Start pulsing selected-directory highlight."""
        if self._drag_anim_active:
            return
        self._drag_anim_active = True
        self._drag_anim_phase = 0
        self._apply_drag_selection_color(self._drag_colors[self._drag_anim_phase])
        self._drag_timer.start(160)

    def _stop_drag_animation(self):
        """Stop pulsing highlight and restore style."""
        self._drag_timer.stop()
        self._drag_anim_active = False
        self.tree.setStyleSheet(self._base_tree_style)
        self.tree.clearSelection()

    def _on_drag_anim_tick(self):
        """Pulse selected color while dragging."""
        if not self._drag_anim_active:
            return
        self._drag_anim_phase = (self._drag_anim_phase + 1) % len(self._drag_colors)
        self._apply_drag_selection_color(self._drag_colors[self._drag_anim_phase])

    def _apply_drag_selection_color(self, color: str):
        """Apply temporary selected-item color for drag feedback."""
        override = (
            "\nQTreeView::item:selected {"
            f"background-color: {color};"
            "}\n"
        )
        self.tree.setStyleSheet((self._base_tree_style or "") + override)

