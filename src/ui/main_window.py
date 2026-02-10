"""Main application window."""
import os
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtWidgets import QTreeWidgetItem
from src.core.scheduler import TaskScheduler
from src.engines.sftp_engine import SftpEngine
from src.services.connection_checker import ConnectionChecker
from src.services.site_store import SiteStore
from src.shared.errors import SSHFerryError
from src.shared.logging_ import setup_logger
from src.shared.models import RemoteEntry, SiteConfig
from src.shared.paths import ensure_in_sandbox, get_remote_parent, join_remote_path
from src.ui.panels.local_panel import LocalPanel
from src.ui.panels.remote_panel import RemotePanel
from src.ui.panels.task_center import TaskCenterPanel
from src.ui.widgets.site_editor import SiteEditorDialog

# ---------------------------------------------------------------------------
# Background threads (all network I/O off the UI thread)
# ---------------------------------------------------------------------------

class ConnectionCheckThread(QThread):
    check_completed = Signal(list)

    def __init__(self, site_config: SiteConfig):
        super().__init__()
        self.site_config = site_config

    def run(self):
        checker = ConnectionChecker(self.site_config)
        results = checker.run_all_checks()
        self.check_completed.emit(results)


class ListDirThread(QThread):
    list_completed = Signal(str, list, object)  # path, entries, parent_item
    list_failed = Signal(str, str)      # path, error

    def __init__(self, site_config: SiteConfig, remote_path: str, parent_item: Optional[QTreeWidgetItem] = None):
        super().__init__()
        self.site_config = site_config
        self.remote_path = remote_path
        self.parent_item = parent_item

    def run(self):
        try:
            engine = SftpEngine(self.site_config)
            engine.connect()
            entries = engine.list_dir(self.remote_path)
            engine.disconnect()
            self.list_completed.emit(self.remote_path, entries, self.parent_item)
        except SSHFerryError as e:
            self.list_failed.emit(self.remote_path, f"[{e.code.name}] {e.message}")
        except Exception as e:
            self.list_failed.emit(self.remote_path, str(e))


class RemoteOpThread(QThread):
    """Generic thread for single remote operations (mkdir / delete / rename)."""
    op_done = Signal()
    op_failed = Signal(str)

    def __init__(self, site_config: SiteConfig, func_name: str, *args, **kwargs):
        super().__init__()
        self.site_config = site_config
        self.func_name = func_name
        self.args = args
        self.kwargs = kwargs
        # Extract optional 'parent_item' from kwargs if present (not used by SftpEngine but by callback)
        self.parent_item = kwargs.get('parent_item')

    def run(self):
        try:
            engine = SftpEngine(self.site_config)
            engine.connect()
            getattr(engine, self.func_name)(*self.args)
            engine.disconnect()
            self.op_done.emit()
        except SSHFerryError as e:
            self.op_failed.emit(f"[{e.code.name}] {e.message}")
        except Exception as e:
            self.op_failed.emit(str(e))


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    # Class variable to track window count for naming
    _window_count = 0
    
    def __init__(self):
        super().__init__()
        MainWindow._window_count += 1
        self._window_number = MainWindow._window_count
        
        self.logger = setup_logger()
        self.sites: List[SiteConfig] = []
        self.current_site: Optional[SiteConfig] = None
        self.scheduler: Optional[TaskScheduler] = None
        self.site_store = SiteStore()
        self.window_manager = None  # Set by WindowManager

        # Keep references to background threads so they aren't GC'd
        self._bg_threads: List[QThread] = []

        self.setWindowTitle(f"SSHFerry #{self._window_number}")
        self.resize(1400, 850)

        # Apply modern white-blue stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f7fa;
            }
            QWidget {
                background-color: #ffffff;
                color: #333333;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 500;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #106ebe;
                border: 1px solid #0078d4;
            }
            QPushButton:pressed {
                background-color: #005a9e;
                padding: 9px 15px 7px 17px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
            /* Secondary/outline buttons */
            QPushButton[flat="true"] {
                background-color: transparent;
                color: #0078d4;
                border: 1px solid #0078d4;
            }
            QPushButton[flat="true"]:hover {
                background-color: #e5f1fb;
            }
            QLineEdit, QComboBox {
                background-color: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                padding: 6px 10px;
                color: #333333;
                min-height: 20px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #0078d4;
                border-width: 2px;
            }
            QComboBox:hover {
                border-color: #0078d4;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                border: 1px solid #d0d0d0;
                selection-background-color: #cce4f7;
                selection-color: #333333;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item {
                padding: 6px 10px;
                min-height: 24px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #e5f1fb;
            }
            /* Tooltips */
            QToolTip {
                background-color: #333333;
                color: #ffffff;
                border: none;
                padding: 6px 10px;
                border-radius: 4px;
            }
            QListWidget, QTableWidget, QTreeView {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                alternate-background-color: #f8f9fa;
            }
            QListWidget::item:selected, QTableWidget::item:selected, QTreeView::item:selected {
                background-color: #cce4f7;
                color: #333333;
            }
            QListWidget::item:hover, QTableWidget::item:hover {
                background-color: #e5f1fb;
            }
            QLabel {
                color: #333333;
                background-color: transparent;
            }
            QSplitter::handle {
                background-color: #e0e0e0;
            }
            QHeaderView::section {
                background-color: #f0f4f8;
                color: #333333;
                padding: 8px;
                border: 1px solid #e0e0e0;
                font-weight: bold;
            }
            QScrollBar:vertical {
                background-color: #f5f5f5;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #0078d4;
            }
            QStatusBar {
                background-color: #0078d4;
                color: white;
            }
            QTextEdit {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
            QMenu {
                background-color: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                padding: 4px 0px;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                background-color: transparent;
                color: #333333;
            }
            QMenu::item:selected {
                background-color: #e5f1fb;
                color: #0078d4;
            }
            QMenu::separator {
                height: 1px;
                background-color: #e0e0e0;
                margin: 4px 0px;
            }
        """)

        self._init_ui()
        self._load_saved_sites()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)

        # --- Left: site list ---
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)

        left_lay.addWidget(QLabel("Sites"))
        self.site_list = QListWidget()
        self.site_list.itemClicked.connect(self._on_site_selected)
        left_lay.addWidget(self.site_list)

        btn_add = QPushButton("Add Site")
        btn_add.clicked.connect(self._add_site)
        left_lay.addWidget(btn_add)

        btn_edit = QPushButton("Edit Site")
        btn_edit.clicked.connect(self._edit_site)
        left_lay.addWidget(btn_edit)

        btn_check = QPushButton("Check Connection")
        btn_check.clicked.connect(self._check_connection)
        left_lay.addWidget(btn_check)

        btn_connect = QPushButton("Connect")
        btn_connect.clicked.connect(self._connect_to_site)
        left_lay.addWidget(btn_connect)

        self.conn_label = QLabel("Disconnected")
        left_lay.addWidget(self.conn_label)
        left.setMaximumWidth(220)

        # --- Centre: dual-panel ---
        panel_splitter = QSplitter(Qt.Horizontal)

        self.local_panel = LocalPanel()
        panel_splitter.addWidget(self.local_panel)

        self.remote_panel = RemotePanel()
        panel_splitter.addWidget(self.remote_panel)
        panel_splitter.setStretchFactor(0, 1)
        panel_splitter.setStretchFactor(1, 1)

        # Wire remote panel signals
        self.remote_panel.entry_activated.connect(self._on_remote_entry_activated)
        self.remote_panel.request_expand.connect(self._remote_expand)  # New handler
        self.remote_panel.request_go_up.connect(self._remote_go_up)
        self.remote_panel.request_refresh.connect(self._remote_refresh)
        self.remote_panel.request_mkdir.connect(self._remote_mkdir)
        self.remote_panel.request_delete.connect(self._remote_delete)
        self.remote_panel.request_rename.connect(self._remote_rename)
        self.remote_panel.request_upload.connect(self._upload_files)
        self.remote_panel.request_upload_paths.connect(self._upload_paths)
        self.remote_panel.request_download.connect(self._download_entry)

        # Wire local panel signals for download via drag-drop
        self.local_panel.files_dropped.connect(self._download_paths)

        # --- Bottom: task center + log ---
        bottom_splitter = QSplitter(Qt.Horizontal)
        self.task_center = TaskCenterPanel()
        self.task_center.request_pause.connect(self.pause_task)
        self.task_center.request_resume.connect(self.resume_task)
        self.task_center.request_cancel.connect(self.cancel_task)
        self.task_center.request_restart.connect(self.restart_task)
        self.task_center.request_clear_finished.connect(self.clear_finished_tasks)
        bottom_splitter.addWidget(self.task_center)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        bottom_splitter.addWidget(self.log_text)
        bottom_splitter.setStretchFactor(0, 2)
        bottom_splitter.setStretchFactor(1, 1)

        # --- Compose ---
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(panel_splitter)
        right_splitter.addWidget(bottom_splitter)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 1)

        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(left)
        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)

        root_layout.addWidget(main_splitter)

        # Status bar
        self.setStatusBar(QStatusBar())
        
        # Menu bar
        self._create_menu_bar()

        # Task refresh timer
        self._task_timer = QTimer()
        self._task_timer.timeout.connect(self._refresh_tasks)

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("&File")
        
        # New Window action
        new_window_action = file_menu.addAction("&New Window")
        new_window_action.setShortcut("Ctrl+N")
        new_window_action.triggered.connect(self._new_window)
        
        file_menu.addSeparator()
        
        # Close Window action
        close_action = file_menu.addAction("&Close Window")
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(self.close)

    def _new_window(self):
        """Create a new window."""
        if self.window_manager:
            self.window_manager.create_window()
            self._log(f"Opened new window #{MainWindow._window_count}")

    # ------------------------------------------------------------------
    # Site management
    # ------------------------------------------------------------------

    def _add_test_site(self):
        password = os.environ.get("APP_SSH_PASSWORD")
        site = SiteConfig(
            name="AutoDL Test",
            host="connect.westb.seetacloud.com",
            port=16921,
            username="root",
            auth_method="password",
            password=password,
            remote_root="/",
        )
        self.sites.append(site)
        self.site_list.addItem(site.name)
        self._log(f"Added test site: {site.name}")
        if not password:
            self._log("  (Set APP_SSH_PASSWORD env var or enter via Site Editor)")

    def _add_site(self):
        dlg = SiteEditorDialog(parent=self)
        dlg.site_saved.connect(self._on_site_saved)
        dlg.exec()

    def _on_site_saved(self, cfg: SiteConfig):
        self.sites.append(cfg)
        self.site_list.addItem(cfg.name)
        self._log(f"Saved site: {cfg.name}")

    def _on_site_selected(self, item: QListWidgetItem):
        idx = self.site_list.row(item)
        if 0 <= idx < len(self.sites):
            self.current_site = self.sites[idx]
            self._log(f"Selected: {self.current_site.name}")

    def _edit_site(self):
        """Edit the currently selected site."""
        if not self.current_site:
            QMessageBox.warning(self, "No Site Selected", "Please select a site to edit.")
            return

        # Find index of current site
        try:
            idx = self.sites.index(self.current_site)
        except ValueError:
            return

        dlg = SiteEditorDialog(site_config=self.current_site, parent=self)
        # Connect to a specific handler for edits
        dlg.site_saved.connect(lambda cfg: self._on_site_edited(idx, cfg))
        dlg.exec()

    def _on_site_edited(self, idx: int, cfg: SiteConfig):
        """Handle saving an edited site."""
        # Update site in list
        self.sites[idx] = cfg
        self.current_site = cfg
        
        # Update UI list item
        item = self.site_list.item(idx)
        if item:
            item.setText(cfg.name)
            
        self._log(f"Updated site: {cfg.name}")
        self._save_sites()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _check_connection(self):
        if not self._ensure_site():
            return
        self._log(f"Checking {self.current_site.name}...")
        t = ConnectionCheckThread(self.current_site)
        t.check_completed.connect(self._on_check_completed)
        self._start_thread(t)

    def _on_check_completed(self, results):
        lines = [f"{'PASS' if r.passed else 'FAIL'} {r.name}: {r.message}" for r in results]
        ok = all(r.passed for r in results)
        title = "All Passed" if ok else "Some Failed"
        func = QMessageBox.information if ok else QMessageBox.warning
        func(self, title, "\n".join(lines))
        for line in lines:
            self._log(f"  {line}")

    def _connect_to_site(self):
        if not self._ensure_site():
            return

        # Prompt for password if not set
        if self.current_site.auth_method == "password" and not self.current_site.password:
            from PySide6.QtWidgets import QLineEdit
            pwd, ok = QInputDialog.getText(
                self, "Password",
                f"Password for {self.current_site.username}@{self.current_site.host}:",
                QLineEdit.EchoMode.Password,
            )
            if not ok or not pwd:
                return
            self.current_site.password = pwd

        # Default empty remote_root to root
        if not self.current_site.remote_root or not self.current_site.remote_root.strip():
            self.current_site.remote_root = "/"

        self._log(f"Connecting to {self.current_site.name}...")
        self.conn_label.setText("Connecting...")

        if self.scheduler:
            self.scheduler.stop()

        self.scheduler = TaskScheduler(self.current_site, logger=self.logger)
        self.scheduler.start()
        self._task_timer.start(500)

        self.conn_label.setText(f"Connected: {self.current_site.name}")
        self._list_remote_dir(self.current_site.remote_root)

    # ------------------------------------------------------------------
    # Remote navigation
    # ------------------------------------------------------------------

    def _list_remote_dir(self, path: str, parent_item: Optional[QTreeWidgetItem] = None):
        if not self.current_site:
            return
        self._log(f"Listing {path}")
        t = ListDirThread(self.current_site, path, parent_item)
        t.list_completed.connect(self._on_list_completed)
        t.list_failed.connect(self._on_list_failed)
        self._start_thread(t)

    def _remote_expand(self, path: str, item: QTreeWidgetItem):
        """Handle tree expansion request."""
        self._list_remote_dir(path, item)

    def _on_list_completed(self, path: str, entries: list, parent_item: Optional[QTreeWidgetItem]):
        if parent_item:
            # Populate specific node
            self.remote_panel.populate_node(parent_item, entries)
        else:
            # Populate root
            self.remote_panel.set_path(path)
            self.remote_panel.set_root_entries(entries)
        
        self._log(f"  {len(entries)} items in {path}")

    def _on_list_failed(self, path: str, msg: str):
        self._log(f"List failed ({path}): {msg}")
        QMessageBox.critical(self, "Error", msg)

    def _on_remote_entry_activated(self, entry: RemoteEntry):
        self._log(f"Activated: {entry.path} (is_dir={entry.is_dir})")
        # For tree view, double click typically just expands/collapses. 
        # If we want double click to 'enter' directory (change root), we can keep this.
        # But user requested "folder expand", so usually we don't change root unless explicitly requested.
        pass
        # if entry.is_dir:
        #     self._list_remote_dir(entry.path)
        # else:
        #     self._log(f"File: {entry.name} ({entry.size} bytes)")

    def _remote_go_up(self):
        if not self.current_site:
            return
        parent = get_remote_parent(self.remote_panel.current_path)
        if parent:
            try:
                ensure_in_sandbox(parent, self.current_site.remote_root)
                self._list_remote_dir(parent)
            except Exception:
                self._log("Already at sandbox root")

    def _remote_refresh(self):
        # Refresh current root. 
        # TODO: Ideally should refresh expanded nodes too, but for now just root or user has to collapse/expand.
        # Or we could track expanded paths.
        self._list_remote_dir(self.remote_panel.current_path)

    # ------------------------------------------------------------------
    # Remote file operations (mkdir / delete / rename)
    # ------------------------------------------------------------------

    def _remote_mkdir(self, name: str, parent_item: QTreeWidgetItem = None):
        if not self._ensure_site():
            return
            
        # Determine parent path
        if parent_item:
            # If created under a specific node
            entry = parent_item.data(0, Qt.UserRole)
            parent_path = entry.path if entry else self.remote_panel.current_path
        else:
            # Use current view root or specific target
            parent_path = self.remote_panel.get_current_target_dir()

        full = join_remote_path(parent_path, name)
        self._log(f"mkdir {full}")
        
        # Pass parent_item to refresh the specific node if possible
        # For now, we simple refresh the parent node if it's expanded
        t = RemoteOpThread(self.current_site, "mkdir", full)
        
        def on_done():
            # Refresh the parent folder
            if parent_item:
                self._list_remote_dir(parent_path, parent_item)
            else:
                self._remote_refresh()
                
        t.op_done.connect(on_done)
        t.op_failed.connect(lambda m: self._op_error("mkdir", m))
        self._start_thread(t)

    def _remote_delete(self, entry: RemoteEntry):
        if not self._ensure_site():
            return
            
        is_dir = entry.is_dir
        msg = f"Delete '{entry.name}'"
        if is_dir:
            msg += " and all its contents?\n\nThis cannot be undone."
        else:
            msg += "?"
            
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        cmd = "remove_dir_recursive" if is_dir else "remove_file"
            
        self._log(f"Deleting {entry.path}")
        t = RemoteOpThread(self.current_site, cmd, entry.path)
        t.op_done.connect(self._remote_refresh)
        t.op_failed.connect(lambda m: self._op_error("delete", m))
        self._start_thread(t)

    def _remote_rename(self, entry: RemoteEntry, new_name: str):
        if not self._ensure_site():
            return
        parent = get_remote_parent(entry.path) or self.remote_panel.current_path
        new_path = join_remote_path(parent, new_name)
        self._log(f"rename {entry.path} -> {new_path}")
        t = RemoteOpThread(self.current_site, "rename", entry.path, new_path)
        t.op_done.connect(self._remote_refresh)
        t.op_failed.connect(lambda m: self._op_error("rename", m))
        self._start_thread(t)

    def _op_error(self, op: str, msg: str):
        self._log(f"{op} failed: {msg}")
        QMessageBox.critical(self, f"{op} Error", msg)

    # ------------------------------------------------------------------
    # Upload / Download
    # ------------------------------------------------------------------

    def _upload_files(self):
        if not self._ensure_site() or not self.scheduler:
            return

        paths = self.local_panel.get_selected_paths()
        if not paths:
            # Fallback: open file dialog
            paths, _ = QFileDialog.getOpenFileNames(self, "Select files to upload")
        if not paths:
            return

        # Upload to where?
        remote_dir = self.remote_panel.get_current_target_dir()
        
        for local_path in paths:
            if os.path.isfile(local_path):
                fname = os.path.basename(local_path)
                remote_path = join_remote_path(remote_dir, fname)
                size = os.path.getsize(local_path)
                task = TaskScheduler.create_upload_task(local_path, remote_path, size)
                self.scheduler.add_task(task)
                self._log(f"Queued upload: {fname} -> {remote_path}")
            elif os.path.isdir(local_path):
                self._enqueue_dir_upload(local_path, remote_dir)

    def _upload_paths(self, paths: list, target_item: QTreeWidgetItem = None):
        """Handle drag-drop upload from local panel."""
        if not self._ensure_site() or not self.scheduler:
            return
        if not paths:
            return

        # Determine target remote directory
        remote_dir = self.remote_panel.current_path
        if target_item:
            entry = target_item.data(0, Qt.UserRole)
            if entry:
                remote_dir = entry.path if entry.is_dir else get_remote_parent(entry.path)
        
        for local_path in paths:
            if os.path.isfile(local_path):
                fname = os.path.basename(local_path)
                remote_path = join_remote_path(remote_dir, fname)
                size = os.path.getsize(local_path)
                task = TaskScheduler.create_upload_task(local_path, remote_path, size)
                self.scheduler.add_task(task)
                self._log(f"Queued upload (drag): {fname} -> {remote_path}")
            elif os.path.isdir(local_path):
                self._log(f"Queued upload folder (drag): {local_path}")
                self._enqueue_dir_upload(local_path, remote_dir)

    def _enqueue_dir_upload(self, local_dir: str, remote_parent: str):
        """Create a single folder upload task for the entire directory."""
        dir_name = os.path.basename(local_dir)
        remote_dir = join_remote_path(remote_parent, dir_name)
        
        # Scan folder to get file count and total size
        total_files, total_bytes = self._scan_local_dir(local_dir)
        
        if total_files > 0:
            task = TaskScheduler.create_folder_upload_task(
                local_dir, remote_dir, total_files, total_bytes
            )
            self.scheduler.add_task(task)
            self._log(f"Queued folder upload: {dir_name} ({total_files} files, {self._format_size(total_bytes)})")
        else:
            # Empty folder - just create mkdir task
            task = TaskScheduler.create_mkdir_task(remote_dir)
            self.scheduler.add_task(task)

    def _scan_local_dir(self, path: str) -> tuple:
        """Recursively count files and total bytes in a local directory."""
        total_files = 0
        total_bytes = 0
        for name in os.listdir(path):
            full = os.path.join(path, name)
            if os.path.isfile(full):
                total_files += 1
                total_bytes += os.path.getsize(full)
            elif os.path.isdir(full):
                sub_files, sub_bytes = self._scan_local_dir(full)
                total_files += sub_files
                total_bytes += sub_bytes
        return total_files, total_bytes

    def _format_size(self, size: int) -> str:
        """Format size in human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _download_entry(self, entry: RemoteEntry):
        if not self._ensure_site() or not self.scheduler:
            return

        local_dir = self.local_panel.get_current_dir()
        if entry.is_dir:
            self._log(f"Queued download folder: {entry.path}")
            self._enqueue_dir_download(entry.path, local_dir)
        else:
            local_path = os.path.join(local_dir, entry.name)
            task = TaskScheduler.create_download_task(entry.path, local_path, entry.size)
            self.scheduler.add_task(task)
            self._log(f"Queued download: {entry.name} -> {local_path}")

    def _download_paths(self, remote_paths: list):
        """Handle drag-drop download from remote panel."""
        if not self._ensure_site() or not self.scheduler:
            return
        if not remote_paths:
            return

        local_dir = self.local_panel.get_current_dir()

        for remote_path in remote_paths:
            entry = self._find_remote_entry_by_path(remote_path)
            if entry:
                if entry.is_dir:
                    self._log(f"Queued download folder (drag): {entry.path}")
                    self._enqueue_dir_download(entry.path, local_dir)
                else:
                    local_path = os.path.join(local_dir, entry.name)
                    task = TaskScheduler.create_download_task(entry.path, local_path, entry.size)
                    self.scheduler.add_task(task)
                    self._log(f"Queued download (drag): {entry.name} -> {local_path}")
            else:
                # Entry not found in cache, create task with unknown size
                name = os.path.basename(remote_path)
                local_path = os.path.join(local_dir, name)
                task = TaskScheduler.create_download_task(remote_path, local_path, 0)
                self.scheduler.add_task(task)
                self._log(f"Queued download (drag): {name} -> {local_path}")

    def _enqueue_dir_download(self, remote_dir: str, local_parent: str):
        """Create a single folder download task for the remote directory."""
        # We need to scan the remote dir first (in a thread) to count files
        t = ListDirThread(self.current_site, remote_dir)

        def on_listed(path, entries, _parent_item):
            dir_name = os.path.basename(remote_dir)
            local_dir = os.path.join(local_parent, dir_name)
            
            # Count files and total size (non-recursive for now, scheduler handles recursion)
            total_files = 0
            total_bytes = 0
            
            def count_entries(ents):
                nonlocal total_files, total_bytes
                for ent in ents:
                    if not ent.is_dir:
                        total_files += 1
                        total_bytes += ent.size
            
            count_entries(entries)
            
            if total_files > 0 or any(e.is_dir for e in entries):
                task = TaskScheduler.create_folder_download_task(
                    remote_dir, local_dir, max(1, total_files), total_bytes
                )
                self.scheduler.add_task(task)
                self._log(f"Queued folder download: {dir_name} ({total_files} files, {self._format_size(total_bytes)})")

        t.list_completed.connect(on_listed)
        t.list_failed.connect(lambda p, m: self._log(f"Download list failed: {m}"))
        self._start_thread(t)

    # ------------------------------------------------------------------
    # Task center
    # ------------------------------------------------------------------

    def _refresh_tasks(self):
        if self.scheduler:
            self.task_center.set_tasks(self.scheduler.get_all_tasks())

    def cancel_task(self, task_id: str):
        if self.scheduler and self.scheduler.cancel_task(task_id):
            self._log(f"Canceled task {task_id[:8]}")

    def pause_task(self, task_id: str):
        if self.scheduler and self.scheduler.pause_task(task_id):
            self._log(f"Paused task {task_id[:8]}")

    def resume_task(self, task_id: str):
        if self.scheduler and self.scheduler.resume_task(task_id):
            self._log(f"Resumed task {task_id[:8]}")

    def restart_task(self, task_id: str):
        if self.scheduler and self.scheduler.restart_task(task_id):
            self._log(f"Restarted task {task_id[:8]}")

    def clear_finished_tasks(self):
        if not self.scheduler:
            return
        with self.scheduler.task_lock:
            ids = [tid for tid, t in self.scheduler.tasks.items() if t.is_finished]
            for tid in ids:
                del self.scheduler.tasks[tid]
        self._log(f"Cleared {len(ids)} finished tasks")
        self._refresh_tasks()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_site(self) -> bool:
        if not self.current_site:
            QMessageBox.warning(self, "No Site", "Select a site first.")
            return False
        return True

    def _find_remote_entry_by_path(self, remote_path: str) -> Optional[RemoteEntry]:
        """Find a RemoteEntry in the remote tree by full path."""
        tree = self.remote_panel.tree

        def walk(item: QTreeWidgetItem) -> Optional[RemoteEntry]:
            entry = item.data(0, Qt.UserRole)
            if entry and entry.path == remote_path:
                return entry
            for i in range(item.childCount()):
                found = walk(item.child(i))
                if found:
                    return found
            return None

        root = tree.invisibleRootItem()
        for i in range(root.childCount()):
            found = walk(root.child(i))
            if found:
                return found
        return None

    def _log(self, msg: str):
        self.log_text.append(msg)
        self.logger.info(msg)

    def _start_thread(self, thread: QThread):
        """Keep a reference and auto-cleanup."""
        self._bg_threads.append(thread)
        thread.finished.connect(lambda: self._bg_threads.remove(thread) if thread in self._bg_threads else None)
        thread.start()

    def closeEvent(self, event):
        self._task_timer.stop()
        if self.scheduler:
            self.scheduler.stop()
        # Save sites on exit
        self._save_sites()
        event.accept()

    def _load_saved_sites(self):
        """Load saved sites or add test site if none exist."""
        saved = self.site_store.load()
        if saved:
            self.sites = saved
            for site in saved:
                self.site_list.addItem(site.name)
            self._log(f"Loaded {len(saved)} saved sites")
        else:
            self._add_test_site()

    def _save_sites(self):
        """Save sites to persistent storage."""
        self.site_store.save(self.sites)
        self._log(f"Saved {len(self.sites)} sites")
