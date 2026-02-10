"""Remote file panel for displaying remote directory contents."""

from PySide6.QtCore import QByteArray, QMimeData, QTimer, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.shared.models import RemoteEntry


class DraggableTreeWidget(QTreeWidget):
    """TreeWidget with drag support for remote file entries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)

    def startDrag(self, supportedActions):
        """Start a drag operation with remote paths."""
        selected_items = self.selectedItems()
        if not selected_items:
            return

        # Collect remote paths from selected items
        paths = []
        for item in selected_items:
            entry = item.data(0, Qt.UserRole)
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
    """Panel for displaying and navigating remote directory contents with drag-drop and tree support."""

    path_changed = Signal(str)  # Emitted when current path changes (root of view)
    entry_activated = Signal(RemoteEntry)  # Emitted when file is double-clicked
    
    # Request signals
    request_go_up = Signal()
    request_refresh = Signal()
    request_mkdir = Signal(str, object)  # new dir name, parent item
    request_delete = Signal(RemoteEntry)
    request_rename = Signal(RemoteEntry, str)  # entry, new_name
    request_upload = Signal()  # upload selected local files to current remote dir
    request_upload_paths = Signal(list, object)  # upload specific local paths (from drag-drop), target item
    request_download = Signal(RemoteEntry)
    request_download_paths = Signal(list)  # download remote paths (from drag-drop)
    
    # New signal for lazy loading
    request_expand = Signal(str, QTreeWidgetItem)  # path, item to populate
    ROLE_EMPTY_LOADED = Qt.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_path = "/"
        self._drag_anim_phase = 0
        self._drag_anim_active = False
        self._drag_colors = ["#cce4f7", "#a9dcff"]
        self._drag_timer = QTimer(self)
        self._drag_timer.timeout.connect(self._on_drag_anim_tick)
        self._base_tree_stylesheet = ""
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

        # File tree with drag support
        self.tree = DraggableTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Name", "Type", "Size", "Modified"])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemCollapsed.connect(self._on_item_collapsed)
        
        # Adjust column widths
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 60)
        self.tree.setColumnWidth(2, 80)

        # Improved styling
        self._base_tree_stylesheet = """
            QTreeWidget {
                font-size: 13px;
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #cce4f7;
                color: #333333;
            }
            QTreeWidget::item:hover {
                background-color: #e5f1fb;
            }
            QHeaderView::section {
                background-color: #f0f4f8;
                padding: 6px;
                font-weight: bold;
                border: 1px solid #e0e0e0;
                color: #333333;
            }
        """
        self.tree.setStyleSheet(self._base_tree_stylesheet)

        # Enable drop for receiving files from local panel
        self.setAcceptDrops(True)

        layout.addWidget(self.tree)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_path(self, path: str):
        self.current_path = path
        self.path_label.setText(f"Remote: {path}")
        self.path_changed.emit(path)

    def set_root_entries(self, entries: list[RemoteEntry]):
        """Populate the root level of the tree."""
        self.tree.clear()
        self.populate_node(self.tree.invisibleRootItem(), entries)

    def populate_node(self, item: QTreeWidgetItem, entries: list[RemoteEntry]):
        """Populate a specific node with entries."""
        # Clear existing children (usually the 'loading' dummy)
        item.takeChildren()
        item.setData(0, self.ROLE_EMPTY_LOADED, False)

        sorted_entries = sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))

        for entry in sorted_entries:
            # Create item
            child = QTreeWidgetItem(item)
            
            # Name & Icon
            icon = "📁" if entry.is_dir else "📄"
            child.setText(0, f"{icon} {entry.name}")
            child.setFont(0, self._get_font(bold=entry.is_dir))
            
            # Metadata
            child.setText(1, "DIR" if entry.is_dir else "FILE")
            child.setText(2, self._format_size(entry.size) if not entry.is_dir else "")
            child.setText(3, entry.mtime_datetime.strftime("%Y-%m-%d %H:%M:%S"))
            
            # Store data
            child.setData(0, Qt.UserRole, entry)

            # If directory, add dummy child to enable expansion indicator
            if entry.is_dir:
                dummy = QTreeWidgetItem(child)
                dummy.setText(0, "Loading...")
                child.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)

        # Keep an expansion handle for empty folders so users can collapse back.
        if item != self.tree.invisibleRootItem() and not sorted_entries:
            empty = QTreeWidgetItem(item)
            empty.setText(0, "(empty)")
            empty.setDisabled(True)
            item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            item.setData(0, self.ROLE_EMPTY_LOADED, True)

    def get_selected_entries(self) -> list[RemoteEntry]:
        """Return all selected RemoteEntry objects."""
        result = []
        for item in self.tree.selectedItems():
            entry = item.data(0, Qt.UserRole)
            if entry:
                result.append(entry)
        return result

    def get_current_target_dir(self) -> str:
        """Get the directory path implied by selection, or root."""
        selected = self.tree.selectedItems()
        if selected:
            item = selected[0]
            entry = item.data(0, Qt.UserRole)
            if entry.is_dir:
                return entry.path
            else:
                # Use parent directory
                parent = item.parent()
                if parent:
                    p_entry = parent.data(0, Qt.UserRole)
                    if p_entry:
                        return p_entry.path
        return self.current_path

    # ------------------------------------------------------------------
    # Tree Interaction
    # ------------------------------------------------------------------

    def _on_item_expanded(self, item: QTreeWidgetItem):
        """Handle item expansion - lazy load."""
        # Check if first child is dummy
        if item.childCount() == 1 and item.child(0).text(0) == "Loading...":
            entry = item.data(0, Qt.UserRole)
            if entry and entry.is_dir:
                self.request_expand.emit(entry.path, item)

    def _on_item_collapsed(self, item: QTreeWidgetItem):
        """Handle item collapse - can be used to free memory if needed."""
        # For empty folder, collapse back to unopened state.
        if item.data(0, self.ROLE_EMPTY_LOADED):
            item.takeChildren()
            loading = QTreeWidgetItem(item)
            loading.setText(0, "Loading...")
            item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            item.setData(0, self.ROLE_EMPTY_LOADED, False)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double click."""
        entry = item.data(0, Qt.UserRole)
        if entry:
            if not entry.is_dir:
                self.entry_activated.emit(entry)
            # Directories automatically expand/collapse via default QTreeWidget behavior

    def _get_font(self, bold=False):
        font = self.tree.font()
        font.setBold(bold)
        return font

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos):
        menu = QMenu(self)

        act_refresh = menu.addAction("Refresh")
        act_refresh.triggered.connect(lambda: self.request_refresh.emit())

        menu.addSeparator()

        selected = self.get_selected_entries()
        
        # Determine context parent
        target_item = self.tree.itemAt(pos)
        
        act_upload = menu.addAction("Upload here...")
        act_upload.triggered.connect(lambda: self.request_upload.emit())

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
            act_delete.triggered.connect(lambda: self.request_delete.emit(entry))

        menu.addSeparator()
        act_mkdir = menu.addAction("New Folder")
        act_mkdir.triggered.connect(lambda: self._prompt_mkdir(target_item))

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _prompt_mkdir(self, parent_item: QTreeWidgetItem = None):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            self.request_mkdir.emit(name.strip(), parent_item)

    def _prompt_rename(self, entry: RemoteEntry):
        new_name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=entry.name
        )
        if ok and new_name.strip() and new_name.strip() != entry.name:
            self.request_rename.emit(entry, new_name.strip())



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
            self._start_drag_animation()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Accept drag move events with file URLs."""
        if event.mimeData().hasUrls():
            self._set_drag_target_from_pos(event.pos())
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        """Clear drag highlight when pointer leaves widget."""
        self._stop_drag_animation()
        event.accept()

    def dropEvent(self, event):
        """Handle dropped files - emit upload request."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
            if paths:
                # Find target item
                target_item = self._target_item_from_pos(event.pos())
                self.request_upload_paths.emit(paths, target_item)
            self._stop_drag_animation()
            event.acceptProposedAction()

    def _target_item_from_pos(self, panel_pos):
        """Map panel coordinates to tree target directory item."""
        viewport_pos = self.tree.viewport().mapFrom(self, panel_pos)
        item = self.tree.itemAt(viewport_pos)
        if not item:
            return None
        entry = item.data(0, Qt.UserRole)
        if entry and not entry.is_dir:
            return item.parent()
        return item

    def _set_drag_target_from_pos(self, panel_pos):
        """Highlight hovered target directory during drag."""
        item = self._target_item_from_pos(panel_pos)
        if item:
            self.tree.setCurrentItem(item)
            self._start_drag_animation()
        else:
            self.tree.clearSelection()

    def _start_drag_animation(self):
        """Start pulsing selected-directory highlight."""
        if self._drag_anim_active:
            return
        self._drag_anim_active = True
        self._drag_anim_phase = 0
        self._apply_drag_selection_color(self._drag_colors[self._drag_anim_phase])
        self._drag_timer.start(160)

    def _stop_drag_animation(self):
        """Stop pulsing highlight and restore base style."""
        self._drag_timer.stop()
        self._drag_anim_active = False
        self.tree.setStyleSheet(self._base_tree_stylesheet)
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
            "\nQTreeWidget::item:selected {"
            f"background-color: {color}; color: #333333;"
            "}\n"
        )
        self.tree.setStyleSheet(self._base_tree_stylesheet + override)

