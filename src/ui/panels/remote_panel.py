"""Remote file panel for displaying remote directory contents."""
import json
import os
from dataclasses import dataclass, field

from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QDrag, QKeyEvent, QPainter, QPixmap
from shiboken6 import isValid
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
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
    QStyle,
    QStyledItemDelegate,
)

from src.shared.models import RemoteEntry
from src.ui.i18n import tr
from src.ui.theme import TOKENS, alpha_hex, mono_font
from src.ui.widgets.feedback import install_button_feedback


@dataclass
class TreeRestoreState:
    expanded_paths: set[str] = field(default_factory=set)
    current_path: str | None = None
    subtrees: dict[str, tuple[str, list[RemoteEntry]]] = field(default_factory=dict)
    anchor_path: str | None = None
    anchor_offset: int = 0
    vscroll_value: int = 0
    hscroll_value: int = 0


class MetricsColumnDelegate(QStyledItemDelegate):
    """Use mono font for aligned metric columns."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.font = mono_font(9)


class SizeColumnDelegate(MetricsColumnDelegate):
    """Right-align file sizes like Windows Explorer."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignRight | Qt.AlignVCenter


class DateColumnDelegate(MetricsColumnDelegate):
    """Keep modified dates left-aligned like Windows Explorer."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignLeft | Qt.AlignVCenter


class DraggableTreeWidget(QTreeWidget):
    """TreeWidget with drag support for remote file entries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Delete:
            panel = self.parent()
            delete_selected = getattr(panel, "_request_delete_selected_entries", None)
            if callable(delete_selected) and delete_selected():
                event.accept()
                return
        super().keyPressEvent(event)

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
        panel = self.parent()
        payload = {
            "session_id": getattr(panel, "session_id", ""),
            "site_name": getattr(panel, "site_name", ""),
            "paths": paths,
        }
        mime_data.setData(
            "application/x-sshferry-remote",
            QByteArray(json.dumps(payload).encode("utf-8")),
        )

        # Start drag
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        label = os.path.basename(paths[0]) if len(paths) == 1 else tr("label.items", count=len(paths))
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


class RemotePanel(QWidget):
    """Panel for displaying and navigating remote directory contents with drag-drop and tree support."""

    path_changed = Signal(str)  # Emitted when current path changes (root of view)
    entry_activated = Signal(RemoteEntry)  # Emitted when file is double-clicked
    
    # Request signals
    request_go_up = Signal()
    request_refresh = Signal()
    request_refresh_node = Signal(str, object)  # path, node item
    request_mkdir = Signal(str, object)  # new dir name, parent item
    request_delete = Signal(RemoteEntry)
    request_delete_entries = Signal(list)
    request_rename = Signal(RemoteEntry, str)  # entry, new_name
    request_upload = Signal(object)  # upload selected local files; target item or None
    request_upload_paths = Signal(list, object)  # upload specific local paths (from drag-drop), target item
    request_download = Signal(RemoteEntry)
    request_download_paths = Signal(list)  # download remote paths (from drag-drop)
    request_remote_transfer = Signal(str, list, object)  # source_session_id, paths, target item
    
    # New signal for lazy loading
    request_expand = Signal(str, QTreeWidgetItem)  # path, item to populate
    ROLE_EMPTY_LOADED = Qt.UserRole + 1
    POPULATE_BATCH_SIZE = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_path = "/"
        self.session_id = ""
        self.site_name = ""
        self._drag_anim_active = False
        self._base_tree_stylesheet = ""
        self._drag_saved_current_item = None
        self._drag_saved_selected_items = []
        self._population_generations: dict[str, int] = {}
        self._drag_pulse_on = False
        self._drag_pulse_timer = QTimer(self)
        self._drag_pulse_timer.setInterval(220)
        self._drag_pulse_timer.timeout.connect(self._toggle_drag_pulse)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(TOKENS.spacing_xs)

        # Navigation bar
        nav_frame = QFrame()
        nav_frame.setObjectName("toolbarCard")
        nav = QHBoxLayout(nav_frame)
        nav.setContentsMargins(TOKENS.spacing_sm, TOKENS.spacing_xs, TOKENS.spacing_sm, TOKENS.spacing_xs)
        nav.setSpacing(TOKENS.spacing_xs)

        self.btn_up = QPushButton("..")
        self.btn_up.setProperty("variant", "ghost")
        self.btn_up.setFixedSize(34, 34)
        self.btn_up.setToolTip(tr("nav.up.tooltip"))
        self.btn_up.clicked.connect(lambda: self.request_go_up.emit())
        nav.addWidget(self.btn_up)

        self.path_label = QLabel(tr("remote.path.label", path="/"))
        self.path_label.setObjectName("sectionTitle")
        nav.addWidget(self.path_label, stretch=1)

        layout.addWidget(nav_frame)

        # File tree with drag support
        self.tree = DraggableTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels([tr("col.name"), tr("col.type"), tr("col.size"), tr("col.modified")])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(True)
        self.tree.setIconSize(QSize(18, 18))
        header = self.tree.header()
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(96)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemCollapsed.connect(self._on_item_collapsed)
        self.tree.setItemDelegateForColumn(2, SizeColumnDelegate(self.tree))
        self.tree.setItemDelegateForColumn(3, DateColumnDelegate(self.tree))
        
        # Adjust column widths
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 60)
        self.tree.setColumnWidth(2, 110)
        self.tree.setColumnWidth(3, 150)

        self.tree.setAlternatingRowColors(True)
        self._base_tree_stylesheet = (
            "QTreeWidget { font-size: 13px; padding: 4px; }"
            "QTreeWidget::item { padding: 6px 4px; }"
        )
        self.tree.setStyleSheet(self._base_tree_stylesheet)

        # Enable drop for receiving files from local panel
        self.setAcceptDrops(True)

        layout.addWidget(self.tree)
        install_button_feedback(self)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_path(self, path: str):
        self.current_path = path
        prefix = f"{self.site_name} " if self.site_name else ""
        self.path_label.setText(f"{prefix}{tr('remote.path.label', path=path)}")
        self.path_changed.emit(path)

    def set_session_context(self, session_id: str, site_name: str):
        """Attach this panel to a specific remote session."""
        self.session_id = session_id
        self.site_name = site_name
        self.set_path(self.current_path)

    def reset_view_state(self):
        """Clear visible items and any pending restore state."""
        self._population_generations.clear()
        self._drag_saved_current_item = None
        self._drag_saved_selected_items = []
        self.tree.clear()

    def set_root_entries(self, entries: list[RemoteEntry], preserve_state: bool = False):
        """Populate the root level of the tree."""
        restore_state = self._capture_restore_state() if preserve_state else None
        self._drag_saved_current_item = None
        self._drag_saved_selected_items = []
        self.tree.clear()
        self._start_population(self.tree.invisibleRootItem(), entries, restore_state, scope_key="__root__")

    def populate_node(
        self,
        item: QTreeWidgetItem,
        entries: list[RemoteEntry],
        preserve_state: bool = False,
        restore_state: TreeRestoreState | None = None,
    ):
        """Populate a specific node with entries."""
        if not isValid(item):
            return
        if restore_state is None and preserve_state:
            restore_state = self._capture_restore_state(item)
        entry = item.data(0, Qt.UserRole) if item != self.tree.invisibleRootItem() else None
        scope_key = entry.path if entry else "__root__"
        self._start_population(item, entries, restore_state, scope_key=scope_key)

    def _start_population(
        self,
        item: QTreeWidgetItem,
        entries: list[RemoteEntry],
        restore_state: TreeRestoreState | None,
        *,
        scope_key: str,
    ) -> None:
        generation = self._population_generations.get(scope_key, 0) + 1
        self._population_generations[scope_key] = generation
        item.takeChildren()
        item.setData(0, self.ROLE_EMPTY_LOADED, False)
        sorted_entries = sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))

        def process_batch(start_index: int = 0) -> None:
            if self._population_generations.get(scope_key) != generation:
                return
            if not isValid(item):
                return
            end_index = min(start_index + self.POPULATE_BATCH_SIZE, len(sorted_entries))
            self.tree.setUpdatesEnabled(False)
            try:
                for entry in sorted_entries[start_index:end_index]:
                    self._append_entry_item(item, entry, restore_state)
                if end_index >= len(sorted_entries):
                    if item != self.tree.invisibleRootItem() and not sorted_entries:
                        empty = QTreeWidgetItem(item)
                        empty.setText(0, tr("tree.empty"))
                        empty.setDisabled(True)
                        item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                        item.setData(0, self.ROLE_EMPTY_LOADED, True)
                    self._restore_tree_state_for_children(item, restore_state)
            finally:
                self.tree.setUpdatesEnabled(True)
            if end_index < len(sorted_entries):
                QTimer.singleShot(0, lambda next_index=end_index: process_batch(next_index))
                return
            if restore_state:
                self._schedule_restore_view_anchor(restore_state)

        process_batch()

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
            if entry is None:
                # Loading / empty placeholder rows carry no entry.
                return self.current_path
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

    def find_item_by_path(self, path: str) -> QTreeWidgetItem | None:
        """Return the visible tree item matching a remote path, if any."""
        if not path:
            return None
        root = self.tree.invisibleRootItem()
        for index in range(root.childCount()):
            found = self._find_item_by_path_recursive(root.child(index), path)
            if found:
                return found
        return None

    def _capture_restore_state(self, scope_item: QTreeWidgetItem | None = None) -> TreeRestoreState:
        anchor_path, anchor_offset, vscroll_value, hscroll_value = self._capture_view_anchor()
        expanded_paths, current_path, subtrees = self._capture_tree_state(scope_item)
        return TreeRestoreState(
            expanded_paths=expanded_paths,
            current_path=current_path,
            subtrees=subtrees,
            anchor_path=anchor_path,
            anchor_offset=anchor_offset,
            vscroll_value=vscroll_value,
            hscroll_value=hscroll_value,
        )

    def _capture_view_anchor(self) -> tuple[str | None, int, int, int]:
        vscroll = self.tree.verticalScrollBar()
        hscroll = self.tree.horizontalScrollBar()
        vscroll_value = vscroll.value()
        hscroll_value = hscroll.value()
        anchor_item = self.tree.itemAt(0, 0)
        anchor_path = None
        anchor_offset = 0
        if anchor_item:
            entry = anchor_item.data(0, Qt.UserRole)
            if entry:
                anchor_path = entry.path
                anchor_offset = self.tree.visualItemRect(anchor_item).top()
        return anchor_path, anchor_offset, vscroll_value, hscroll_value

    def _schedule_restore_view_anchor(self, restore_state: TreeRestoreState):
        QTimer.singleShot(0, lambda state=restore_state: self._restore_view_anchor(state))

    def _restore_view_anchor(self, restore_state: TreeRestoreState):
        hscroll = self.tree.horizontalScrollBar()
        vscroll = self.tree.verticalScrollBar()
        hscroll.setValue(restore_state.hscroll_value)
        if restore_state.anchor_path:
            anchor_item = self.find_item_by_path(restore_state.anchor_path)
            if anchor_item:
                self.tree.scrollToItem(anchor_item, QAbstractItemView.PositionAtTop)
                vscroll.setValue(max(0, vscroll.value() + restore_state.anchor_offset))
                return
        vscroll.setValue(restore_state.vscroll_value)

    def _capture_tree_state(
        self,
        scope_item: QTreeWidgetItem | None = None,
    ) -> tuple[set[str], str | None, dict[str, tuple[str, list[RemoteEntry]]]]:
        expanded_paths: set[str] = set()
        subtrees: dict[str, tuple[str, list[RemoteEntry]]] = {}

        def walk(item: QTreeWidgetItem):
            entry = item.data(0, Qt.UserRole)
            if entry and entry.is_dir and item.isExpanded():
                expanded_paths.add(entry.path)
                subtrees[entry.path] = self._snapshot_directory(item)
            for index in range(item.childCount()):
                walk(item.child(index))

        root = self.tree.invisibleRootItem()
        if scope_item is None or scope_item == root:
            for index in range(root.childCount()):
                walk(root.child(index))
        else:
            walk(scope_item)

        current_item = self.tree.currentItem()
        current_path = None
        if current_item and self._item_within_scope(current_item, scope_item):
            entry = current_item.data(0, Qt.UserRole)
            if entry:
                current_path = entry.path
        return expanded_paths, current_path, subtrees

    @staticmethod
    def _item_within_scope(item: QTreeWidgetItem | None, scope_item: QTreeWidgetItem | None) -> bool:
        if item is None or scope_item is None:
            return True
        current = item
        while current:
            if current == scope_item:
                return True
            current = current.parent()
        return False

    def _snapshot_directory(self, item: QTreeWidgetItem) -> tuple[str, list[RemoteEntry]]:
        if item.data(0, self.ROLE_EMPTY_LOADED):
            return ("empty", [])
        if self._has_loading_placeholder(item):
            return ("loading", [])
        children: list[RemoteEntry] = []
        for index in range(item.childCount()):
            child_entry = item.child(index).data(0, Qt.UserRole)
            if child_entry:
                children.append(child_entry)
        return ("entries", children)

    def _append_entry_item(
        self,
        parent: QTreeWidgetItem,
        entry: RemoteEntry,
        restore_state: TreeRestoreState | None = None,
    ) -> QTreeWidgetItem:
        child = QTreeWidgetItem(parent)

        child.setText(0, entry.name)
        style = self.tree.style()
        std_icon = style.standardIcon(QStyle.SP_DirIcon) if entry.is_dir else style.standardIcon(QStyle.SP_FileIcon)
        child.setIcon(0, std_icon)
        child.setFont(0, self._get_font(bold=entry.is_dir))

        child.setText(1, tr("tree.type.dir") if entry.is_dir else tr("tree.type.file"))
        child.setText(2, self._format_size(entry.size) if not entry.is_dir else "")
        child.setText(3, entry.mtime_datetime.strftime("%Y-%m-%d %H:%M:%S"))
        child.setFont(2, mono_font(9))
        child.setFont(3, mono_font(9))
        child.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
        child.setTextAlignment(3, Qt.AlignLeft | Qt.AlignVCenter)
        child.setData(0, Qt.UserRole, entry)

        if entry.is_dir:
            if not self._restore_cached_children(child, entry.path, restore_state):
                dummy = QTreeWidgetItem(child)
                dummy.setText(0, tr("tree.loading"))
                dummy.setDisabled(True)
            child.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
        return child

    def _restore_cached_children(
        self,
        item: QTreeWidgetItem,
        path: str,
        restore_state: TreeRestoreState | None,
    ) -> bool:
        if restore_state is None:
            return False
        snapshot = restore_state.subtrees.pop(path, None)
        if snapshot is None:
            return False

        state, entries = snapshot
        if state == "loading":
            loading = QTreeWidgetItem(item)
            loading.setText(0, tr("tree.loading"))
            loading.setDisabled(True)
            return True
        if state == "empty":
            empty = QTreeWidgetItem(item)
            empty.setText(0, tr("tree.empty"))
            empty.setDisabled(True)
            item.setData(0, self.ROLE_EMPTY_LOADED, True)
            return True

        for child_entry in entries:
            self._append_entry_item(item, child_entry, restore_state)
        self._restore_tree_state_for_children(item, restore_state)
        return True

    def _restore_tree_state_for_children(self, item: QTreeWidgetItem, restore_state: TreeRestoreState | None):
        if restore_state is None:
            return
        for index in range(item.childCount()):
            child = item.child(index)
            entry = child.data(0, Qt.UserRole)
            if not entry:
                continue
            if restore_state.current_path == entry.path:
                self.tree.setCurrentItem(child)
                child.setSelected(True)
                restore_state.current_path = None
            if entry.is_dir and entry.path in restore_state.expanded_paths:
                restore_state.expanded_paths.discard(entry.path)
                child.setExpanded(True)
                if not self._has_loading_placeholder(child):
                    QTimer.singleShot(0, lambda path=entry.path, node=child: self.request_expand.emit(path, node))

    @staticmethod
    def _has_loading_placeholder(item: QTreeWidgetItem) -> bool:
        return item.childCount() == 1 and item.child(0).text(0) == tr("tree.loading")

    # ------------------------------------------------------------------
    # Tree Interaction
    # ------------------------------------------------------------------

    def _on_item_expanded(self, item: QTreeWidgetItem):
        """Handle item expansion - lazy load."""
        # Check if first child is dummy
        if item.childCount() == 1 and item.child(0).text(0) == tr("tree.loading"):
            entry = item.data(0, Qt.UserRole)
            if entry and entry.is_dir:
                self.request_expand.emit(entry.path, item)

    def _on_item_collapsed(self, item: QTreeWidgetItem):
        """Handle item collapse - can be used to free memory if needed."""
        # For empty folder, collapse back to unopened state.
        if item.data(0, self.ROLE_EMPTY_LOADED):
            item.takeChildren()
            loading = QTreeWidgetItem(item)
            loading.setText(0, tr("tree.loading"))
            loading.setDisabled(True)
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

    def _on_refresh_clicked(self):
        """Refresh selected node if possible, otherwise refresh root view."""
        self._emit_refresh_for_item(self.tree.currentItem())

    def _emit_refresh_for_item(self, item: QTreeWidgetItem | None):
        """Emit refresh signal for the most relevant directory context."""
        if item:
            entry = item.data(0, Qt.UserRole)
            if entry and entry.is_dir:
                self.request_refresh_node.emit(entry.path, item)
                return
            parent = item.parent()
            if parent:
                parent_entry = parent.data(0, Qt.UserRole)
                if parent_entry and parent_entry.is_dir:
                    self.request_refresh_node.emit(parent_entry.path, parent)
                    return
        self.request_refresh.emit()

    def _show_context_menu(self, pos):
        menu = QMenu(self)

        target_item = self.tree.itemAt(pos)
        act_refresh = menu.addAction(tr("action.refresh"))
        act_refresh.triggered.connect(lambda: self._emit_refresh_for_item(target_item))

        menu.addSeparator()

        selected = self._prepare_context_selection(target_item)

        act_upload = menu.addAction(tr("menu.upload_here"))
        act_upload.triggered.connect(lambda: self.request_upload.emit(target_item))

        if selected:
            entry = selected[0]
            if len(selected) == 1:
                if not entry.is_dir:
                    act_dl = menu.addAction(tr("action.download"))
                    act_dl.triggered.connect(lambda: self.request_download.emit(entry))
                else:
                    act_dl = menu.addAction(tr("menu.download_folder"))
                    act_dl.triggered.connect(lambda: self.request_download.emit(entry))

                menu.addSeparator()

                act_rename = menu.addAction(tr("action.rename"))
                act_rename.triggered.connect(lambda: self._prompt_rename(entry))

            delete_label = self._delete_action_label(selected)
            act_delete = menu.addAction(delete_label)
            act_delete.triggered.connect(lambda checked=False, entries=list(selected): self._emit_delete_entries(entries, checked))

        menu.addSeparator()
        act_mkdir = menu.addAction(tr("action.new_folder"))
        act_mkdir.triggered.connect(lambda: self._prompt_mkdir(target_item))

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _prepare_context_selection(self, target_item: QTreeWidgetItem | None) -> list[RemoteEntry]:
        if target_item and not target_item.isSelected():
            self.tree.clearSelection()
            target_item.setSelected(True)
            self.tree.setCurrentItem(target_item)
        return self.get_selected_entries()

    @staticmethod
    def _delete_action_label(entries: list[RemoteEntry]) -> str:
        return tr("action.delete") if len(entries) == 1 else tr("label.delete_many", count=len(entries))

    def _request_delete_selected_entries(self) -> bool:
        selected = self.get_selected_entries()
        if not selected:
            return False
        self._emit_delete_entries(selected)
        return True

    def _emit_delete_entries(self, entries: list[RemoteEntry], _checked: bool = False) -> None:
        self.request_delete_entries.emit(entries)

    def _prompt_mkdir(self, parent_item: QTreeWidgetItem = None):
        name, ok = QInputDialog.getText(self, tr("dialog.new_folder.title"), tr("dialog.new_folder.prompt"))
        if ok and name.strip():
            self.request_mkdir.emit(name.strip(), parent_item)

    def _prompt_rename(self, entry: RemoteEntry):
        new_name, ok = QInputDialog.getText(
            self, tr("dialog.rename.title"), tr("dialog.rename.prompt"), text=entry.name
        )
        if ok and new_name.strip() and new_name.strip() != entry.name:
            self.request_rename.emit(entry, new_name.strip())

    def _find_item_by_path_recursive(self, item: QTreeWidgetItem, path: str) -> QTreeWidgetItem | None:
        entry = item.data(0, Qt.UserRole)
        if entry and entry.path == path:
            return item
        for index in range(item.childCount()):
            found = self._find_item_by_path_recursive(item.child(index), path)
            if found:
                return found
        return None



    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ["Byte", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    # ------------------------------------------------------------------
    # Drag-drop support for receiving uploads from LocalPanel
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event):
        """Accept drag events with file URLs."""
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-sshferry-remote"):
            self._start_drag_animation()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Accept drag move events with file URLs."""
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-sshferry-remote"):
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
            return
        if event.mimeData().hasFormat("application/x-sshferry-remote"):
            raw = bytes(event.mimeData().data("application/x-sshferry-remote")).decode("utf-8")
            payload = json.loads(raw)
            source_session_id = payload.get("session_id", "")
            paths = payload.get("paths", [])
            if source_session_id and paths and source_session_id != self.session_id:
                target_item = self._target_item_from_pos(event.pos())
                self.request_remote_transfer.emit(source_session_id, paths, target_item)
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
            self._start_drag_animation()
            self.tree.clearSelection()
            item.setSelected(True)
            self.tree.setCurrentItem(item)

    def _start_drag_animation(self):
        """Mark drag as active and preserve existing selection state."""
        if self._drag_anim_active:
            return
        self._drag_anim_active = True
        self._drag_saved_current_item = self.tree.currentItem()
        self._drag_saved_selected_items = list(self.tree.selectedItems())
        self._drag_pulse_on = False
        self._apply_drag_stylesheet()
        self._drag_pulse_timer.start()

    def _stop_drag_animation(self):
        """Restore previous selection state after drag feedback."""
        self._drag_anim_active = False
        self._drag_pulse_timer.stop()
        self._drag_pulse_on = False
        self.tree.setStyleSheet(self._base_tree_stylesheet)
        self.tree.clearSelection()
        # The tree may have been repopulated mid-drag; saved items can be
        # dead C++ objects.
        for item in self._drag_saved_selected_items:
            if isValid(item):
                item.setSelected(True)
        if self._drag_saved_current_item and isValid(self._drag_saved_current_item):
            self.tree.setCurrentItem(self._drag_saved_current_item)
        self._drag_saved_current_item = None
        self._drag_saved_selected_items = []

    def _toggle_drag_pulse(self):
        if not self._drag_anim_active:
            return
        self._drag_pulse_on = not self._drag_pulse_on
        self._apply_drag_stylesheet()

    def _apply_drag_stylesheet(self):
        border_color = TOKENS.accent
        background = alpha_hex(TOKENS.accent, 0.12 if self._drag_pulse_on else 0.08)
        selection = alpha_hex(TOKENS.accent, 0.24 if self._drag_pulse_on else 0.18)
        self.tree.setStyleSheet(
            self._base_tree_stylesheet
            + (
                f"QTreeWidget {{ border: 2px solid {border_color}; background-color: {background}; }}"
                f"QTreeWidget::item:selected {{ background-color: {selection}; "
                f"color: {TOKENS.text_main}; font-weight: 700; }}"
            )
        )


