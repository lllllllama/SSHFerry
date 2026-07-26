"""Local file system panel using QFileSystemModel."""
import fnmatch
import json
import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QDir, QMimeData, QModelIndex, QSize, Qt, QThread, QUrl, Signal, QItemSelectionModel, QSortFilterProxyModel, QTimer
from PySide6.QtGui import QColor, QDrag, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileIconProvider,
    QFileSystemModel,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from src.ui.i18n import tr
from src.ui.theme import TOKENS, alpha_hex, mono_font
from src.ui.widgets.feedback import install_button_feedback


class DeletePathsThread(QThread):
    """Delete files/directories off the GUI thread; big trees can take a while."""

    delete_done = Signal()
    delete_failed = Signal(str)

    def __init__(self, paths: list[str], parent=None):
        super().__init__(parent)
        self._paths = list(paths)

    def run(self):
        try:
            for path in self._paths:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                elif os.path.exists(path):
                    os.remove(path)
            self.delete_done.emit()
        except Exception as exc:
            self.delete_failed.emit(str(exc))


class MetricsColumnDelegate(QStyledItemDelegate):
    """Use tabular-looking mono font for aligned metrics columns."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.font = mono_font(9)


class NameColumnDelegate(QStyledItemDelegate):
    """Give folder names a stronger weight while preserving native icons."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        model = index.model()
        if model is None:
            return
        try:
            file_info = model.fileInfo(index)
        except Exception:
            return
        option.font.setPointSize(10)
        search_terms = getattr(model, "_search_terms", [])
        if file_info.isDir() or search_terms:
            option.font.setBold(True)


class SizeColumnDelegate(MetricsColumnDelegate):
    """Render local file sizes with stable English units."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignRight | Qt.AlignVCenter
        model = index.model()
        if model is None:
            return
        try:
            file_info = model.fileInfo(index)
        except Exception:
            return
        if file_info.isDir():
            option.text = ""
            return
        option.text = self._format_size(file_info.size())

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if size < 1024.0:
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} EB"


class DateColumnDelegate(MetricsColumnDelegate):
    """Keep date values left-aligned like Windows Explorer."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignLeft | Qt.AlignVCenter


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
        label = first_name if len(paths) == 1 else tr("label.items", count=len(paths))
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


class LocalFileSortProxy(QSortFilterProxyModel):
    """Proxy that keeps directories ahead of files like Windows Explorer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sort_order = Qt.AscendingOrder
        self._root_path = ""
        self._search_terms: list[str] = []
        self.setDynamicSortFilter(True)
        self.setSortCaseSensitivity(Qt.CaseInsensitive)
        if hasattr(self, "setRecursiveFilteringEnabled"):
            self.setRecursiveFilteringEnabled(True)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        source = self.sourceModel()
        if source is None:
            return super().lessThan(left, right)

        left_info = source.fileInfo(left)
        right_info = source.fileInfo(right)
        if left_info.isDir() != right_info.isDir():
            if self._sort_order == Qt.DescendingOrder:
                return not left_info.isDir()
            return left_info.isDir()

        column = left.column()
        if column == 1:
            return left_info.size() < right_info.size()
        if column == 3:
            return left_info.lastModified() < right_info.lastModified()

        left_text = source.data(left, Qt.DisplayRole) or ""
        right_text = source.data(right, Qt.DisplayRole) or ""
        return str(left_text).casefold() < str(right_text).casefold()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._search_terms:
            return True

        source = self.sourceModel()
        if source is None:
            return True

        index = source.index(source_row, 0, source_parent)
        if not index.isValid():
            return False

        file_info = source.fileInfo(index)
        return self._search_score(file_info.fileName(), file_info.absoluteFilePath(), self._search_terms) is not None

    def set_search_text(self, text: str) -> None:
        self._search_terms = [term.casefold() for term in text.split() if term.strip()]
        self.invalidateFilter()

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        self._sort_order = order
        super().sort(column, order)

    def filePath(self, index: QModelIndex) -> str:
        source = self.sourceModel()
        if source is None or not index.isValid():
            return ""
        return source.filePath(self.mapToSource(index))

    def fileInfo(self, index: QModelIndex):
        source = self.sourceModel()
        if source is None:
            raise RuntimeError("source model unavailable")
        return source.fileInfo(self.mapToSource(index))

    def setRootPath(self, path: str) -> QModelIndex:
        source = self.sourceModel()
        if source is None:
            return QModelIndex()
        self._root_path = path
        return self.mapFromSource(source.setRootPath(path))

    def index_for_path(self, path: str) -> QModelIndex:
        source = self.sourceModel()
        if source is None:
            return QModelIndex()
        return self.mapFromSource(source.index(path))

    def _relative_display_path(self, absolute_path: str) -> str:
        try:
            return Path(absolute_path).resolve(strict=False).relative_to(
                Path(self._root_path).resolve(strict=False)
            ).as_posix()
        except (OSError, ValueError):
            return absolute_path.replace("\\", "/")

    def _search_score(self, name: str, absolute_path: str, terms: list[str]) -> int | None:
        name_folded = name.casefold()
        relative_folded = self._relative_display_path(absolute_path).casefold()

        for term in terms:
            normalized_term = term.replace("\\", "/")
            if any(char in normalized_term for char in "*?["):
                if fnmatch.fnmatchcase(name_folded, normalized_term) or fnmatch.fnmatchcase(relative_folded, normalized_term):
                    continue
                return None
            if normalized_term.startswith(".") and name_folded.endswith(normalized_term):
                continue
            if normalized_term in name_folded or normalized_term in relative_folded:
                continue
            return None

        return 0


class LocalPanel(QWidget):
    """Panel displaying local file system with navigation and drag support."""

    _DEFAULT_SORT_COLUMN = 0
    _DEFAULT_SORT_ORDER = Qt.AscendingOrder

    file_selected = Signal(str)  # full path of selected file
    dir_changed = Signal(str)  # current directory changed
    files_dropped = Signal(str, list, str)  # source session id, remote paths, target local directory
    request_upload_paths = Signal(list)  # upload selected local paths to active remote session

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_dir = str(Path.home())
        self._drag_anim_active = False
        self._base_tree_style = ""
        self._drag_saved_current_index = QModelIndex()
        self._drag_saved_selected_rows = []
        self._drag_pulse_on = False
        self._drag_pulse_timer = QTimer(self)
        self._drag_pulse_timer.setInterval(220)
        self._drag_pulse_timer.timeout.connect(self._toggle_drag_pulse)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(TOKENS.spacing_sm, TOKENS.spacing_sm, TOKENS.spacing_sm, TOKENS.spacing_sm)
        layout.setSpacing(TOKENS.spacing_xs)

        # Header
        header_frame = QFrame()
        header_frame.setObjectName("toolbarCard")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(TOKENS.spacing_sm, TOKENS.spacing_xs, TOKENS.spacing_sm, TOKENS.spacing_xs)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0)
        title = QLabel(tr("local.title"))
        title.setObjectName("sectionTitle")
        title_box.addWidget(title)
        header.addLayout(title_box)
        header.addStretch()
        layout.addWidget(header_frame)

        # Navigation bar
        nav_frame = QFrame()
        nav_frame.setObjectName("toolbarCard")
        nav = QHBoxLayout(nav_frame)
        nav.setContentsMargins(TOKENS.spacing_sm, TOKENS.spacing_xs, TOKENS.spacing_sm, TOKENS.spacing_xs)
        nav.setSpacing(TOKENS.spacing_xs)
        
        # Drive selector (Windows)
        self.drive_combo = QComboBox()
        self.drive_combo.setFixedWidth(60)
        self.drive_combo.setFixedHeight(34)
        self.drive_combo.setToolTip(tr("local.drive.tooltip"))
        self._populate_drives()
        self.drive_combo.currentTextChanged.connect(self._on_drive_changed)
        nav.addWidget(self.drive_combo)
        
        self.btn_up = QPushButton("..")
        self.btn_up.setProperty("variant", "ghost")
        self.btn_up.setFixedSize(34, 34)
        self.btn_up.setToolTip(tr("nav.up.tooltip"))
        self.btn_up.clicked.connect(self._go_up)
        nav.addWidget(self.btn_up)

        self.btn_refresh = QPushButton(tr("action.refresh"))
        self.btn_refresh.setProperty("variant", "ghost")
        self.btn_refresh.setMinimumWidth(78)
        self.btn_refresh.setFixedHeight(34)
        self.btn_refresh.setToolTip(tr("action.refresh"))
        self.btn_refresh.clicked.connect(self._refresh)
        nav.addWidget(self.btn_refresh)

        self.path_edit = QLineEdit(self.current_dir)
        self.path_edit.setObjectName("localPathInput")
        self.path_edit.setFixedHeight(34)
        self.path_edit.returnPressed.connect(self._on_path_entered)
        nav.addWidget(self.path_edit)

        layout.addWidget(nav_frame)

        search_frame = QFrame()
        search_frame.setObjectName("localSearchBar")
        search_outer = QVBoxLayout(search_frame)
        search_outer.setContentsMargins(TOKENS.spacing_sm, TOKENS.spacing_xs, TOKENS.spacing_sm, TOKENS.spacing_xs)
        search_outer.setSpacing(4)
        search = QHBoxLayout()
        search.setContentsMargins(0, 0, 0, 0)
        search.setSpacing(TOKENS.spacing_xs)

        self.search_label = QLabel(tr("local.search.label"))
        self.search_label.setObjectName("localSearchLabel")
        search.addWidget(self.search_label)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("localSearchInput")
        self.search_edit.setFixedHeight(34)
        self.search_edit.setPlaceholderText(tr("local.search.placeholder"))
        self.search_edit.setToolTip(tr("local.search.tooltip"))
        self.search_edit.textChanged.connect(self._on_search_changed)
        search.addWidget(self.search_edit)

        self.btn_clear_search = QPushButton(tr("action.clear"))
        self.btn_clear_search.setProperty("variant", "ghost")
        self.btn_clear_search.setMinimumWidth(66)
        self.btn_clear_search.setFixedHeight(34)
        self.btn_clear_search.setEnabled(False)
        self.btn_clear_search.clicked.connect(self._clear_search)
        search.addWidget(self.btn_clear_search)
        search_outer.addLayout(search)

        self.search_status = QLabel("")
        self.search_status.setObjectName("localSearchStatus")
        search_outer.addWidget(self.search_status)

        layout.addWidget(search_frame)

        # File system model
        self.icon_provider = QFileIconProvider()
        self.fs_model = QFileSystemModel()
        self.fs_model.setIconProvider(self.icon_provider)
        self.fs_model.setOption(QFileSystemModel.Option.DontUseCustomDirectoryIcons, True)
        self.fs_model.setRootPath(self.current_dir)
        self.fs_model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)

        self.model = LocalFileSortProxy(self)
        self.model.setSourceModel(self.fs_model)

        # Draggable tree view
        self.tree = DraggableTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.setRootPath(self.current_dir))
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(True)
        self.tree.setSortingEnabled(True)
        header = self.tree.header()
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(96)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(self._DEFAULT_SORT_COLUMN, self._DEFAULT_SORT_ORDER)
        self.tree.sortByColumn(self._DEFAULT_SORT_COLUMN, self._DEFAULT_SORT_ORDER)
        self.tree.doubleClicked.connect(self._on_double_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.setItemDelegateForColumn(1, SizeColumnDelegate(self.tree))
        self.tree.setItemDelegateForColumn(3, DateColumnDelegate(self.tree))
        self.tree.setItemDelegateForColumn(0, NameColumnDelegate(self.tree))

        # Hide unnecessary columns (keep Name, Size, Date Modified)
        self.tree.setColumnHidden(2, True)  # Type column
        self.tree.setColumnWidth(0, 280)
        self.tree.setColumnWidth(1, 110)
        self.tree.setColumnWidth(3, 150)
        self.tree.setAlternatingRowColors(True)
        self._base_tree_style = (
            "QTreeView { padding: 4px; }"
            "QTreeView::item { padding: 6px 4px; }"
        )
        self.tree.setStyleSheet(self._base_tree_style)

        # Enable drop for receiving files from remote
        self.setAcceptDrops(True)

        layout.addWidget(self.tree)
        self.find_shortcut = QShortcut(QKeySequence.Find, self)
        self.find_shortcut.activated.connect(self._focus_search)
        self.clear_search_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.clear_search_shortcut.activated.connect(self._clear_search)
        self._update_search_status()
        install_button_feedback(self)

    def _on_search_changed(self, text: str):
        self.model.set_search_text(text)
        self.btn_clear_search.setEnabled(bool(text.strip()))
        QTimer.singleShot(0, self._update_search_status)

    def _focus_search(self):
        self.search_edit.setFocus(Qt.ShortcutFocusReason)
        self.search_edit.selectAll()

    def _clear_search(self):
        if self.search_edit.text():
            self.search_edit.clear()
        self._update_search_status()

    def _update_search_status(self):
        query = self.search_edit.text().strip()
        if not query:
            self.search_status.setText(tr("local.search.ready"))
            return
        visible_count = self.model.rowCount(self.tree.rootIndex())
        self.search_status.setText(tr("local.search.status", count=visible_count, query=query))

    def _go_up(self):
        parent = str(Path(self.current_dir).parent)
        if parent != self.current_dir:
            self._navigate_to(parent)

    def _refresh(self):
        """Refresh the current directory view."""
        sort_column, sort_order = self._current_sort_state()
        self.model.setRootPath("")
        root_index = self.model.setRootPath(self.current_dir)
        self.tree.setRootIndex(root_index)
        self._apply_sort_state(sort_column, sort_order)
        QTimer.singleShot(0, self._update_search_status)

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
        sort_column, sort_order = self._current_sort_state()
        self.current_dir = path
        self.path_edit.setText(path)
        self.tree.setRootIndex(self.model.setRootPath(path))
        self._apply_sort_state(sort_column, sort_order)
        QTimer.singleShot(0, self._update_search_status)
        self.dir_changed.emit(path)
        # Sync drive combo selection
        self._sync_drive_combo()

    def _current_sort_state(self) -> tuple[int, Qt.SortOrder]:
        header = self.tree.header()
        column = header.sortIndicatorSection()
        if column < 0:
            column = self._DEFAULT_SORT_COLUMN
        return column, header.sortIndicatorOrder()

    def _apply_sort_state(self, column: int, order: Qt.SortOrder) -> None:
        header = self.tree.header()
        header.setSortIndicator(column, order)
        self.tree.sortByColumn(column, order)

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

    def _show_context_menu(self, pos):
        idx = self.tree.indexAt(pos)
        if idx.isValid() and not self.tree.selectionModel().isSelected(idx):
            self.tree.selectionModel().clearSelection()
            self.tree.selectionModel().select(
                idx,
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )
            self.tree.setCurrentIndex(idx)
        elif not idx.isValid():
            self.tree.selectionModel().clearSelection()
            self.tree.setCurrentIndex(QModelIndex())

        selected_paths = self._selected_paths_for_context_menu()
        target_dir = self._target_dir_from_pos(self.mapFromGlobal(self.tree.viewport().mapToGlobal(pos)))
        menu = QMenu(self)

        act_open = menu.addAction(tr("menu.open"))
        act_open.triggered.connect(lambda: self._open_selected_path(selected_paths))
        act_open.setEnabled(bool(selected_paths))

        act_upload = menu.addAction(tr("menu.upload_active"))
        act_upload.triggered.connect(lambda: self.request_upload_paths.emit(selected_paths))
        act_upload.setEnabled(bool(selected_paths))

        menu.addSeparator()

        act_rename = menu.addAction(tr("action.rename"))
        act_rename.triggered.connect(lambda: self._rename_selected_path(selected_paths))
        act_rename.setEnabled(len(selected_paths) == 1)

        act_delete = menu.addAction(tr("action.delete"))
        act_delete.triggered.connect(lambda: self._delete_selected_paths(selected_paths))
        act_delete.setEnabled(bool(selected_paths))

        menu.addSeparator()

        act_mkdir = menu.addAction(tr("action.new_folder"))
        act_mkdir.triggered.connect(lambda: self._create_folder(target_dir))

        menu.addSeparator()

        act_refresh = menu.addAction(tr("action.refresh"))
        act_refresh.triggered.connect(self._refresh)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _selected_paths_for_context_menu(self) -> list[str]:
        return self.get_selected_paths()

    def _open_selected_path(self, selected_paths: list[str]) -> None:
        if not selected_paths:
            return
        path = selected_paths[0]
        if os.path.isdir(path):
            self._navigate_to(path)
            return
        self.file_selected.emit(path)

    def _rename_selected_path(self, selected_paths: list[str]) -> None:
        if len(selected_paths) != 1:
            return
        path = selected_paths[0]
        current_name = os.path.basename(path.rstrip("/\\")) or path
        new_name, ok = QInputDialog.getText(self, tr("dialog.rename.title"), tr("dialog.rename.prompt"), text=current_name)
        if not ok or not new_name.strip() or new_name.strip() == current_name:
            return
        new_path = os.path.join(os.path.dirname(path), new_name.strip())
        try:
            os.rename(path, new_path)
            if os.path.normcase(path) == os.path.normcase(self.current_dir):
                self.current_dir = new_path
                self.path_edit.setText(new_path)
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(self, tr("dialog.rename_error.title"), str(exc))

    def _delete_selected_paths(self, selected_paths: list[str]) -> None:
        paths = self._prune_nested_paths(selected_paths)
        if not paths:
            return
        label = paths[0] if len(paths) == 1 else tr("label.items", count=len(paths))
        answer = QMessageBox.question(
            self,
            tr("dialog.delete.title"),
            tr("dialog.delete.body", label=label),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        existing = getattr(self, "_delete_thread", None)
        if existing is not None and existing.isRunning():
            QMessageBox.information(self, tr("dialog.delete.title"), tr("dialog.delete.in_progress"))
            return
        thread = DeletePathsThread(paths, self)
        thread.delete_done.connect(self._on_delete_finished)
        thread.delete_failed.connect(self._on_delete_failed)
        self._delete_thread = thread
        thread.start()

    def _on_delete_finished(self) -> None:
        self._delete_thread = None
        self._refresh()

    def _on_delete_failed(self, message: str) -> None:
        self._delete_thread = None
        self._refresh()
        QMessageBox.critical(self, tr("dialog.delete_error.title"), message)

    def _create_folder(self, parent_dir: str) -> None:
        name, ok = QInputDialog.getText(self, tr("dialog.new_folder.title"), tr("dialog.new_folder.prompt"))
        if not ok or not name.strip():
            return
        try:
            os.makedirs(os.path.join(parent_dir, name.strip()), exist_ok=False)
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(self, tr("dialog.create_folder_error.title"), str(exc))

    @staticmethod
    def _prune_nested_paths(paths: list[str]) -> list[str]:
        unique_paths = []
        normalized = sorted({os.path.normcase(os.path.abspath(path)): path for path in paths}.items())
        kept_prefixes: list[str] = []
        for normalized_path, original_path in normalized:
            if any(
                normalized_path == prefix or normalized_path.startswith(prefix + os.sep)
                for prefix in kept_prefixes
            ):
                continue
            kept_prefixes.append(normalized_path)
            unique_paths.append(original_path)
        return unique_paths

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
            payload = json.loads(data.data().decode("utf-8"))
            source_session_id = payload.get("session_id", "")
            paths = payload.get("paths", [])
            target_dir = self._target_dir_from_pos(event.pos())
            self.files_dropped.emit(source_session_id, paths, target_dir)
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

    def _target_dir_from_pos(self, panel_pos) -> str:
        """Resolve drop target local directory from panel coordinates."""
        idx = self._target_index_from_pos(panel_pos)
        if idx.isValid():
            path = self.model.filePath(idx)
            if os.path.isdir(path):
                return path
        return self.current_dir

    def _set_drag_target_from_pos(self, panel_pos):
        """Highlight hovered target directory during drag."""
        idx = self._target_index_from_pos(panel_pos)
        if idx.isValid():
            self._start_drag_animation()
            self.tree.selectionModel().clearSelection()
            self.tree.selectionModel().select(
                idx, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
            )
            self.tree.setCurrentIndex(idx)

    def _start_drag_animation(self):
        """Preserve current selection state when drag highlight starts."""
        if self._drag_anim_active:
            return
        self._drag_anim_active = True
        self._drag_saved_current_index = self.tree.currentIndex()
        self._drag_saved_selected_rows = list(self.tree.selectionModel().selectedRows())
        self._drag_pulse_on = False
        self._apply_drag_stylesheet()
        self._drag_pulse_timer.start()

    def _stop_drag_animation(self):
        """Restore previous selection state after drag feedback."""
        self._drag_anim_active = False
        self._drag_pulse_timer.stop()
        self._drag_pulse_on = False
        self.tree.setStyleSheet(self._base_tree_style)
        selection_model = self.tree.selectionModel()
        selection_model.clearSelection()
        for idx in self._drag_saved_selected_rows:
            if idx.isValid():
                selection_model.select(
                    idx, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
                )
        if self._drag_saved_current_index.isValid():
            self.tree.setCurrentIndex(self._drag_saved_current_index)
        self._drag_saved_current_index = QModelIndex()
        self._drag_saved_selected_rows = []

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
            self._base_tree_style
            + (
                f"QTreeView {{ border: 2px solid {border_color}; background-color: {background}; }}"
                f"QTreeView::item:selected {{ background-color: {selection}; "
                f"color: {TOKENS.text_main}; font-weight: 700; }}"
            )
        )

