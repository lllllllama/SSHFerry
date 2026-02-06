"""Main application window."""
import os

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

from src.core.scheduler import TaskScheduler
from src.engines.sftp_engine import SftpEngine
from src.services.connection_checker import ConnectionChecker
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
    list_completed = Signal(str, list)  # path, entries
    list_failed = Signal(str, str)      # path, error

    def __init__(self, site_config: SiteConfig, remote_path: str):
        super().__init__()
        self.site_config = site_config
        self.remote_path = remote_path

    def run(self):
        try:
            engine = SftpEngine(self.site_config)
            engine.connect()
            entries = engine.list_dir(self.remote_path)
            engine.disconnect()
            self.list_completed.emit(self.remote_path, entries)
        except SSHFerryError as e:
            self.list_failed.emit(self.remote_path, f"[{e.code.name}] {e.message}")
        except Exception as e:
            self.list_failed.emit(self.remote_path, str(e))


class RemoteOpThread(QThread):
    """Generic thread for single remote operations (mkdir / delete / rename)."""
    op_done = Signal()
    op_failed = Signal(str)

    def __init__(self, site_config: SiteConfig, func_name: str, *args):
        super().__init__()
        self.site_config = site_config
        self.func_name = func_name
        self.args = args

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
    def __init__(self):
        super().__init__()
        self.logger = setup_logger()
        self.sites: list[SiteConfig] = []
        self.current_site: SiteConfig | None = None
        self.scheduler: TaskScheduler | None = None

        # Keep references to background threads so they aren't GC'd
        self._bg_threads: list[QThread] = []

        self.setWindowTitle("SSHFerry - SSH/SFTP File Manager")
        self.resize(1400, 850)

        self._init_ui()
        self._add_test_site()

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
        self.remote_panel.request_go_up.connect(self._remote_go_up)
        self.remote_panel.request_refresh.connect(self._remote_refresh)
        self.remote_panel.request_mkdir.connect(self._remote_mkdir)
        self.remote_panel.request_delete.connect(self._remote_delete)
        self.remote_panel.request_rename.connect(self._remote_rename)
        self.remote_panel.request_upload.connect(self._upload_files)
        self.remote_panel.request_download.connect(self._download_entry)

        # --- Bottom: task center + log ---
        bottom_splitter = QSplitter(Qt.Horizontal)
        self.task_center = TaskCenterPanel()
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

        # Task refresh timer
        self._task_timer = QTimer()
        self._task_timer.timeout.connect(self._refresh_tasks)

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
            remote_root="/root/autodl-tmp",
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
            pwd, ok = QInputDialog.getText(
                self, "Password",
                f"Password for {self.current_site.username}@{self.current_site.host}:",
                echoMode=2,  # Password
            )
            if not ok or not pwd:
                return
            self.current_site.password = pwd

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

    def _list_remote_dir(self, path: str):
        if not self.current_site:
            return
        self._log(f"Listing {path}")
        t = ListDirThread(self.current_site, path)
        t.list_completed.connect(self._on_list_completed)
        t.list_failed.connect(self._on_list_failed)
        self._start_thread(t)

    def _on_list_completed(self, path: str, entries: list):
        self.remote_panel.set_path(path)
        self.remote_panel.set_entries(entries)
        self._log(f"  {len(entries)} items in {path}")

    def _on_list_failed(self, path: str, msg: str):
        self._log(f"List failed ({path}): {msg}")
        QMessageBox.critical(self, "Error", msg)

    def _on_remote_entry_activated(self, entry: RemoteEntry):
        if entry.is_dir:
            self._list_remote_dir(entry.path)
        else:
            self._log(f"File: {entry.name} ({entry.size} bytes)")

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
        self._list_remote_dir(self.remote_panel.current_path)

    # ------------------------------------------------------------------
    # Remote file operations (mkdir / delete / rename)
    # ------------------------------------------------------------------

    def _remote_mkdir(self, name: str):
        if not self._ensure_site():
            return
        full = join_remote_path(self.remote_panel.current_path, name)
        self._log(f"mkdir {full}")
        t = RemoteOpThread(self.current_site, "mkdir", full)
        t.op_done.connect(self._remote_refresh)
        t.op_failed.connect(lambda m: self._op_error("mkdir", m))
        self._start_thread(t)

    def _remote_delete(self, entry: RemoteEntry):
        if not self._ensure_site():
            return
        self._log(f"delete {entry.path}")
        func_name = "remove_dir" if entry.is_dir else "remove_file"
        t = RemoteOpThread(self.current_site, func_name, entry.path)
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

        remote_dir = self.remote_panel.current_path
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

    def _enqueue_dir_upload(self, local_dir: str, remote_parent: str):
        """Recursively enqueue upload tasks for a directory."""
        dir_name = os.path.basename(local_dir)
        remote_dir = join_remote_path(remote_parent, dir_name)
        # Create mkdir task first
        task = TaskScheduler.create_mkdir_task(remote_dir)
        self.scheduler.add_task(task)

        for name in os.listdir(local_dir):
            full = os.path.join(local_dir, name)
            if os.path.isfile(full):
                remote_path = join_remote_path(remote_dir, name)
                size = os.path.getsize(full)
                task = TaskScheduler.create_upload_task(full, remote_path, size)
                self.scheduler.add_task(task)
            elif os.path.isdir(full):
                self._enqueue_dir_upload(full, remote_dir)

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

    def _enqueue_dir_download(self, remote_dir: str, local_parent: str):
        """Recursively enqueue download tasks for a remote directory."""
        # We need to list the remote dir first (in a thread), then enqueue.
        t = ListDirThread(self.current_site, remote_dir)

        def on_listed(path, entries):
            dir_name = os.path.basename(remote_dir)
            local_dir = os.path.join(local_parent, dir_name)
            os.makedirs(local_dir, exist_ok=True)

            for ent in entries:
                if ent.is_dir:
                    self._enqueue_dir_download(ent.path, local_dir)
                else:
                    local_path = os.path.join(local_dir, ent.name)
                    task = TaskScheduler.create_download_task(ent.path, local_path, ent.size)
                    self.scheduler.add_task(task)

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
            self._log(f"Canceled {task_id[:8]}")

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
        event.accept()
