"""Main application window."""
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.scheduler import TaskScheduler
from ..engines.sftp_engine import SftpEngine
from ..services.connection_checker import ConnectionChecker
from ..shared.errors import SSHFerryError
from ..shared.logging_ import setup_logger
from ..shared.models import RemoteEntry, SiteConfig
from ..shared.paths import get_remote_parent, join_remote_path
from .panels.remote_panel import RemotePanel
from .panels.task_center import TaskCenterPanel
from .widgets.site_editor import SiteEditorDialog


class ConnectionCheckThread(QThread):
    """Thread for running connection checks without blocking UI."""
    
    check_completed = Signal(list)  # Emits list of CheckResult
    
    def __init__(self, site_config: SiteConfig):
        super().__init__()
        self.site_config = site_config
    
    def run(self):
        """Run the connection checks."""
        checker = ConnectionChecker(self.site_config)
        results = checker.run_all_checks()
        self.check_completed.emit(results)


class ListDirThread(QThread):
    """Thread for listing remote directory contents."""
    
    list_completed = Signal(list)  # Emits list of RemoteEntry
    list_failed = Signal(str)  # Emits error message
    
    def __init__(self, site_config: SiteConfig, remote_path: str):
        super().__init__()
        self.site_config = site_config
        self.remote_path = remote_path
    
    def run(self):
        """List directory contents."""
        try:
            engine = SftpEngine(self.site_config)
            engine.connect()
            entries = engine.list_dir(self.remote_path)
            engine.disconnect()
            self.list_completed.emit(entries)
        except SSHFerryError as e:
            self.list_failed.emit(f"[{e.code.name}] {e.message}")
        except Exception as e:
            self.list_failed.emit(f"Error: {e}")


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.logger = setup_logger()
        self.sites: list[SiteConfig] = []
        self.current_site: Optional[SiteConfig] = None
        self.sftp_engine: Optional[SftpEngine] = None
        self.scheduler: Optional[TaskScheduler] = None
        
        self.setWindowTitle("SSHFerry - SSH/SFTP File Manager")
        self.resize(1200, 800)
        
        self._init_ui()
        
        # Add default test site from agent.md
        self._add_test_site()
    
    def _init_ui(self):
        """Initialize UI components."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel: Site list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Site list
        self.site_list = QListWidget()
        self.site_list.itemClicked.connect(self._on_site_selected)
        left_layout.addWidget(self.site_list)
        
        # Site management buttons
        btn_add_site = QPushButton("Add Site")
        btn_add_site.clicked.connect(self._add_site)
        left_layout.addWidget(btn_add_site)
        
        btn_check_conn = QPushButton("Check Connection")
        btn_check_conn.clicked.connect(self._check_connection)
        left_layout.addWidget(btn_check_conn)
        
        btn_connect = QPushButton("Connect")
        btn_connect.clicked.connect(self._connect_to_site)
        left_layout.addWidget(btn_connect)
        
        left_panel.setMaximumWidth(250)
        
        # Right panel: Remote files, task center, and log
        right_splitter = QSplitter(Qt.Vertical)
        
        # Remote panel
        self.remote_panel = RemotePanel()
        self.remote_panel.entry_activated.connect(self._on_remote_entry_activated)
        right_splitter.addWidget(self.remote_panel)
        
        # Task center panel
        self.task_center = TaskCenterPanel()
        self.task_center.setMinimumHeight(150)
        right_splitter.addWidget(self.task_center)
        
        # Log panel
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        right_splitter.addWidget(self.log_text)
        
        # Main splitter
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(main_splitter)
    
    def _add_test_site(self):
        """Add the test site from agent.md."""
        test_site = SiteConfig(
            name="AutoDL Test",
            host="connect.westb.seetacloud.com",
            port=16921,
            username="root",
            auth_method="password",
            password="wRogEEjPxeuA",
            remote_root="/root/autodl-tmp"
        )
        self.sites.append(test_site)
        self.site_list.addItem(test_site.name)
        self._log(f"Added test site: {test_site.name}")
    
    def _add_site(self):
        """Open site editor to add a new site."""
        dialog = SiteEditorDialog(parent=self)
        dialog.site_saved.connect(self._on_site_saved)
        dialog.exec()
    
    def _on_site_saved(self, site_config: SiteConfig):
        """Handle site configuration saved."""
        self.sites.append(site_config)
        self.site_list.addItem(site_config.name)
        self._log(f"Saved site: {site_config.name}")
    
    def _on_site_selected(self, item: QListWidgetItem):
        """Handle site selection."""
        idx = self.site_list.row(item)
        if 0 <= idx < len(self.sites):
            self.current_site = self.sites[idx]
            self._log(f"Selected site: {self.current_site.name}")
    
    def _check_connection(self):
        """Run connection self-check."""
        if not self.current_site:
            QMessageBox.warning(self, "No Site Selected", "Please select a site first.")
            return
        
        self._log(f"Running connection check for {self.current_site.name}...")
        
        # Run check in background thread
        self.check_thread = ConnectionCheckThread(self.current_site)
        self.check_thread.check_completed.connect(self._on_check_completed)
        self.check_thread.start()
    
    def _on_check_completed(self, results):
        """Handle connection check completion."""
        summary = "\n".join([
            f"{'✓' if r.passed else '✗'} {r.name}: {r.message}"
            for r in results
        ])
        
        all_passed = all(r.passed for r in results)
        
        if all_passed:
            QMessageBox.information(
                self,
                "Connection Check Passed",
                f"All checks passed!\n\n{summary}"
            )
            self._log("Connection check: ALL PASSED")
        else:
            QMessageBox.warning(
                self,
                "Connection Check Failed",
                f"Some checks failed:\n\n{summary}"
            )
            self._log("Connection check: FAILED")
        
        for result in results:
            self._log(f"  {result.name}: {'PASS' if result.passed else 'FAIL'} - {result.message}")
    
    def _connect_to_site(self):
        """Connect to the selected site and list remote_root."""
        if not self.current_site:
            QMessageBox.warning(self, "No Site Selected", "Please select a site first.")
            return
        
        self._log(f"Connecting to {self.current_site.name}...")
        
        # Initialize scheduler for this site
        if self.scheduler:
            self.scheduler.stop()
        
        self.scheduler = TaskScheduler(self.current_site, logger=self.logger)
        self.scheduler.start()
        self._log("Task scheduler started")
        
        # Start task refresh timer
        from PySide6.QtCore import QTimer
        self.task_refresh_timer = QTimer()
        self.task_refresh_timer.timeout.connect(self._refresh_tasks)
        self.task_refresh_timer.start(500)  # Refresh every 500ms
        
        self._list_remote_dir(self.current_site.remote_root)
    
    def _list_remote_dir(self, remote_path: str):
        """List contents of a remote directory."""
        if not self.current_site:
            return
        
        self._log(f"Listing directory: {remote_path}")
        
        # Run in background thread
        self.list_thread = ListDirThread(self.current_site, remote_path)
        self.list_thread.list_completed.connect(self._on_list_completed)
        self.list_thread.list_failed.connect(self._on_list_failed)
        self.list_thread.started.connect(lambda: self.remote_panel.clear())
        self.list_thread.start()
    
    def _on_list_completed(self, entries: list[RemoteEntry]):
        """Handle directory listing completion."""
        self.remote_panel.set_entries(entries)
        self._log(f"Listed {len(entries)} entries")
    
    def _on_list_failed(self, error_msg: str):
        """Handle directory listing failure."""
        self._log(f"Failed to list directory: {error_msg}")
        QMessageBox.critical(self, "List Directory Failed", error_msg)
    
    def _on_remote_entry_activated(self, entry: RemoteEntry):
        """Handle double-click on remote entry (navigate into directory)."""
        if entry.is_dir:
            self.remote_panel.set_path(entry.path)
            self._list_remote_dir(entry.path)
        else:
            self._log(f"Selected file: {entry.name}")
    
    def _log(self, message: str):
        """Add message to log panel."""
        self.log_text.append(message)
        self.logger.info(message)
    
    def _refresh_tasks(self):
        """Refresh task center with current tasks."""
        if self.scheduler:
            tasks = self.scheduler.get_all_tasks()
            self.task_center.set_tasks(tasks)
    
    def cancel_task(self, task_id: str):
        """Cancel a task (called from task center)."""
        if self.scheduler:
            if self.scheduler.cancel_task(task_id):
                self._log(f"Canceled task {task_id[:8]}")
            else:
                self._log(f"Failed to cancel task {task_id[:8]}")
    
    def clear_finished_tasks(self):
        """Clear finished tasks from the scheduler."""
        if self.scheduler:
            with self.scheduler.task_lock:
                finished_ids = [
                    task_id for task_id, task in self.scheduler.tasks.items()
                    if task.is_finished
                ]
                for task_id in finished_ids:
                    del self.scheduler.tasks[task_id]
            self._log(f"Cleared {len(finished_ids)} finished tasks")
            self._refresh_tasks()
    
    def closeEvent(self, event):
        """Handle window close."""
        if self.scheduler:
            self.scheduler.stop()
        if self.sftp_engine:
            self.sftp_engine.disconnect()
        event.accept()
