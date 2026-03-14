"""Main application window with dynamic remote sessions."""
import os
import uuid
from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
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


class ConnectionCheckThread(QThread):
    check_completed = Signal(list)

    def __init__(self, site_config: SiteConfig):
        super().__init__()
        self.site_config = site_config

    def run(self):
        checker = ConnectionChecker(self.site_config)
        self.check_completed.emit(checker.run_all_checks())


class ListDirThread(QThread):
    list_completed = Signal(str, list, object)
    list_failed = Signal(str, str)

    def __init__(self, site_config: SiteConfig, remote_path: str, parent_item: Optional[QTreeWidgetItem] = None):
        super().__init__()
        self.site_config = site_config
        self.remote_path = remote_path
        self.parent_item = parent_item

    def run(self):
        engine = SftpEngine(self.site_config)
        try:
            engine.connect()
            entries = engine.list_dir(self.remote_path)
            self.list_completed.emit(self.remote_path, entries, self.parent_item)
        except SSHFerryError as exc:
            self.list_failed.emit(self.remote_path, f"[{exc.code.name}] {exc.message}")
        except Exception as exc:
            self.list_failed.emit(self.remote_path, str(exc))
        finally:
            try:
                engine.disconnect()
            except Exception:
                pass


class RemoteOpThread(QThread):
    op_done = Signal()
    op_failed = Signal(str)

    def __init__(self, site_config: SiteConfig, func_name: str, *args):
        super().__init__()
        self.site_config = site_config
        self.func_name = func_name
        self.args = args

    def run(self):
        engine = SftpEngine(self.site_config)
        try:
            engine.connect()
            getattr(engine, self.func_name)(*self.args)
            self.op_done.emit()
        except SSHFerryError as exc:
            self.op_failed.emit(f"[{exc.code.name}] {exc.message}")
        except Exception as exc:
            self.op_failed.emit(str(exc))
        finally:
            try:
                engine.disconnect()
            except Exception:
                pass


class ScanRemoteDirThread(QThread):
    scan_completed = Signal(str, int, int)
    scan_failed = Signal(str, str)

    def __init__(self, site_config: SiteConfig, remote_path: str):
        super().__init__()
        self.site_config = site_config
        self.remote_path = remote_path

    def run(self):
        engine = SftpEngine(self.site_config)
        try:
            engine.connect()
            total_files, total_bytes = self._scan_recursive(engine, self.remote_path)
            self.scan_completed.emit(self.remote_path, total_files, total_bytes)
        except SSHFerryError as exc:
            self.scan_failed.emit(self.remote_path, f"[{exc.code.name}] {exc.message}")
        except Exception as exc:
            self.scan_failed.emit(self.remote_path, str(exc))
        finally:
            try:
                engine.disconnect()
            except Exception:
                pass

    def _scan_recursive(self, engine: SftpEngine, path: str) -> tuple[int, int]:
        total_files = 0
        total_bytes = 0
        for entry in engine.list_dir(path):
            if entry.is_dir:
                sub_files, sub_bytes = self._scan_recursive(engine, entry.path)
                total_files += sub_files
                total_bytes += sub_bytes
            else:
                total_files += 1
                total_bytes += entry.size
        return total_files, total_bytes


@dataclass
class RemoteSession:
    session_id: str
    site: SiteConfig
    panel: RemotePanel
    container: QWidget
    status_label: QLabel
    selector: QComboBox
    connected: bool = False


class MainWindow(QMainWindow):
    _window_count = 0

    def __init__(self):
        super().__init__()
        MainWindow._window_count += 1
        self._window_number = MainWindow._window_count

        self.logger = setup_logger()
        self.site_store = SiteStore()
        self.sites: List[SiteConfig] = []
        self.scheduler = TaskScheduler(logger=self.logger)
        self.window_manager = None
        self._bg_threads: List[QThread] = []
        self.sessions: dict[str, RemoteSession] = {}
        self._session_order: list[str] = []
        self._active_session_id: str | None = None

        self.setWindowTitle(f"SSHFerry #{self._window_number}")
        self.resize(1520, 900)

        self._init_ui()
        self._load_saved_sites()
        self.scheduler.start()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)

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

        self.btn_edit_site = QPushButton("Edit Site")
        self.btn_edit_site.clicked.connect(self._edit_site)
        left_lay.addWidget(self.btn_edit_site)

        self.btn_remove_site = QPushButton("Remove Site")
        self.btn_remove_site.clicked.connect(self._remove_site)
        left_lay.addWidget(self.btn_remove_site)

        self.btn_check_connection = QPushButton("Check Connection")
        self.btn_check_connection.clicked.connect(self._check_connection)
        left_lay.addWidget(self.btn_check_connection)

        self.btn_new_session = QPushButton("Open Session")
        self.btn_new_session.clicked.connect(self._create_session_from_selection)
        left_lay.addWidget(self.btn_new_session)

        self.btn_remove_session = QPushButton("Close Session")
        self.btn_remove_session.clicked.connect(self._remove_current_session)
        left_lay.addWidget(self.btn_remove_session)

        left_lay.addWidget(QLabel("Task Protocol Override"))
        self.transfer_override_combo = QComboBox()
        self.transfer_override_combo.addItem("Auto (Site Default)", "auto")
        self.transfer_override_combo.addItem("SFTP", "sftp")
        self.transfer_override_combo.addItem("SCP", "scp")
        left_lay.addWidget(self.transfer_override_combo)
        left.setMaximumWidth(220)

        self.local_panel = LocalPanel()
        self.local_panel.files_dropped.connect(self._download_paths)

        self.remote_area = QWidget()
        remote_area_layout = QVBoxLayout(self.remote_area)
        remote_area_layout.setContentsMargins(0, 0, 0, 0)
        self.remote_placeholder = QLabel("No remote sessions open")
        self.remote_placeholder.setAlignment(Qt.AlignCenter)
        self.remote_splitter = QSplitter(Qt.Horizontal)
        self.remote_splitter.setChildrenCollapsible(False)
        self.remote_splitter.setHandleWidth(10)
        self.remote_splitter.setOpaqueResize(False)
        self.remote_splitter.setStyleSheet(
            "QSplitter::handle { background-color: palette(mid); }"
        )
        remote_area_layout.addWidget(self.remote_placeholder)
        remote_area_layout.addWidget(self.remote_splitter)
        self._refresh_remote_area()

        panel_splitter = QSplitter(Qt.Horizontal)
        panel_splitter.setChildrenCollapsible(False)
        panel_splitter.setHandleWidth(10)
        panel_splitter.setOpaqueResize(False)
        panel_splitter.setStyleSheet(
            "QSplitter::handle { background-color: palette(mid); }"
        )
        panel_splitter.addWidget(self.local_panel)
        panel_splitter.addWidget(self.remote_area)
        panel_splitter.setStretchFactor(0, 1)
        panel_splitter.setStretchFactor(1, 2)
        panel_splitter.setSizes([480, 1040])

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
        self.log_text.document().setMaximumBlockCount(1500)
        bottom_splitter.addWidget(self.log_text)
        bottom_splitter.setStretchFactor(0, 2)
        bottom_splitter.setStretchFactor(1, 1)

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(panel_splitter)
        right_splitter.addWidget(bottom_splitter)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 1)

        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(left)
        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(1, 1)
        root_layout.addWidget(main_splitter)

        self.setStatusBar(QStatusBar())
        self._create_menu_bar()

        self._task_timer = QTimer()
        self._task_timer.timeout.connect(self._refresh_tasks)
        self._task_timer.start(350)
        self._update_site_action_buttons()

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        new_window_action = file_menu.addAction("&New Window")
        new_window_action.setShortcut("Ctrl+N")
        new_window_action.triggered.connect(self._new_window)
        file_menu.addSeparator()
        add_session_action = file_menu.addAction("Open Session")
        add_session_action.setShortcut("Ctrl+T")
        add_session_action.triggered.connect(self._create_session_from_selection)
        close_action = file_menu.addAction("&Close Window")
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(self.close)

    def _new_window(self):
        if self.window_manager:
            self.window_manager.create_window()

    def _selected_site(self) -> Optional[SiteConfig]:
        item = self.site_list.currentItem()
        if not item:
            return None
        idx = self.site_list.row(item)
        if 0 <= idx < len(self.sites):
            return self.sites[idx]
        return None

    def _add_site(self):
        dlg = SiteEditorDialog(parent=self)
        dlg.site_saved.connect(self._on_site_saved)
        dlg.exec()

    def _on_site_saved(self, cfg: SiteConfig):
        self.sites.append(cfg)
        self.site_list.addItem(cfg.name)
        self.site_list.setCurrentRow(len(self.sites) - 1)
        self._save_sites()
        self._refresh_session_selectors()
        self._update_site_action_buttons()

    def _on_site_selected(self, _item: QListWidgetItem):
        self._update_site_action_buttons()

    def _edit_site(self):
        site = self._selected_site()
        if not site:
            QMessageBox.warning(self, "No Site Selected", "Please select a site to edit.")
            return
        idx = self.sites.index(site)
        dlg = SiteEditorDialog(site_config=site, parent=self)
        dlg.site_saved.connect(lambda cfg: self._on_site_edited(idx, cfg))
        dlg.exec()

    def _on_site_edited(self, idx: int, cfg: SiteConfig):
        self.sites[idx] = cfg
        item = self.site_list.item(idx)
        if item:
            item.setText(cfg.name)
        self._save_sites()
        self._refresh_session_selectors()
        self._update_site_action_buttons()

    def _remove_site(self):
        site = self._selected_site()
        if not site:
            QMessageBox.warning(self, "No Site Selected", "Please select a site to remove.")
            return

        answer = QMessageBox.question(
            self,
            "Remove Site",
            f"Remove site '{site.name}'?\n\nThis will also close any open sessions using it.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        idx = self.sites.index(site)
        self._close_sessions_for_site(site.name)
        self.sites.pop(idx)
        item = self.site_list.takeItem(idx)
        if item:
            del item

        if self.sites:
            self.site_list.setCurrentRow(min(idx, len(self.sites) - 1))

        self._save_sites()
        self._refresh_session_selectors()
        self._update_site_action_buttons()

    def _check_connection(self):
        site = self._selected_site()
        if not site:
            return
        self._log(f"Checking {site.name}...")
        thread = ConnectionCheckThread(site)
        thread.check_completed.connect(self._on_check_completed)
        self._start_thread(thread)

    def _on_check_completed(self, results: list):
        lines = [f"{r.name}: {'OK' if r.passed else 'FAIL'} - {r.message}" for r in results]
        QMessageBox.information(self, "Connection Check", "\n".join(lines))

    def _create_session_from_selection(self):
        site = self._selected_site()
        if not site:
            QMessageBox.warning(self, "No Site Selected", "Select a site first.")
            return
        self._create_session(site)

    def _create_session(self, site: SiteConfig):
        session_id = str(uuid.uuid4())
        container = QFrame()
        container.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        container.setStyleSheet("QFrame { border: 1px solid palette(mid); }")

        header = QHBoxLayout()
        session_label = QLabel(site.name)
        session_label.setStyleSheet("font-weight: bold; padding: 0 4px;")
        selector = QComboBox()
        self._populate_site_selector(selector, site.name)
        status_label = QLabel("Disconnected")
        btn_connect = QPushButton("Connect")
        btn_connect.clicked.connect(lambda: self._activate_and_run(session_id, self._connect_session))
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(lambda: self._activate_and_run(session_id, self._remote_refresh))
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(lambda: self._close_session(session_id))
        header.addWidget(session_label)
        header.addWidget(selector, 1)
        header.addWidget(btn_connect)
        header.addWidget(btn_refresh)
        header.addWidget(btn_close)
        header.addWidget(status_label)
        layout.addLayout(header)

        panel = RemotePanel()
        panel.set_session_context(session_id, site.name)
        layout.addWidget(panel)

        session = RemoteSession(session_id, site, panel, container, status_label, selector)
        selector.currentIndexChanged.connect(lambda _idx, sid=session_id: self._switch_session_site(sid))
        panel.tree.itemPressed.connect(lambda _item, _col, sid=session_id: self._set_active_session(sid))
        panel.entry_activated.connect(lambda entry, sid=session_id: self._on_remote_entry_activated(sid, entry))
        panel.request_expand.connect(lambda path, item, sid=session_id: self._remote_expand(sid, path, item))
        panel.request_go_up.connect(lambda sid=session_id: self._activate_and_run(sid, self._remote_go_up))
        panel.request_refresh.connect(lambda sid=session_id: self._activate_and_run(sid, self._remote_refresh))
        panel.request_refresh_node.connect(
            lambda path, item, sid=session_id: self._activate_and_run(sid, self._remote_refresh_node, path, item)
        )
        panel.request_mkdir.connect(lambda name, item, sid=session_id: self._activate_and_run(sid, self._remote_mkdir, name, item))
        panel.request_delete.connect(lambda entry, sid=session_id: self._activate_and_run(sid, self._remote_delete, entry))
        panel.request_rename.connect(
            lambda entry, new_name, sid=session_id: self._activate_and_run(sid, self._remote_rename, entry, new_name)
        )
        panel.request_upload.connect(lambda sid=session_id: self._activate_and_run(sid, self._upload_files))
        panel.request_upload_paths.connect(
            lambda paths, item, sid=session_id: self._activate_and_run(sid, self._upload_paths, paths, item)
        )
        panel.request_download.connect(lambda entry, sid=session_id: self._activate_and_run(sid, self._download_entry, entry))
        panel.request_remote_transfer.connect(
            lambda src_sid, paths, item, dst_sid=session_id: self._remote_to_remote_drop(src_sid, dst_sid, paths, item)
        )

        self.sessions[session_id] = session
        self._session_order.append(session_id)
        self.remote_splitter.addWidget(container)
        self._refresh_remote_area()
        self._rebalance_remote_splitter()
        self._set_active_session(session_id)
        self._update_site_action_buttons()
        self._log(f"Opened session for {site.name}")

    def _remove_current_session(self):
        session = self._current_session()
        if session:
            self._close_session(session.session_id)

    def _close_session(self, session_id: str):
        session = self.sessions.get(session_id)
        if not session:
            return
        self.sessions.pop(session_id, None)
        if session_id in self._session_order:
            self._session_order.remove(session_id)
        if self._active_session_id == session_id:
            self._active_session_id = self._session_order[-1] if self._session_order else None
        session.container.setParent(None)
        session.container.deleteLater()
        self._refresh_remote_area()
        self._rebalance_remote_splitter()
        self._update_active_session_styles()
        self._update_site_action_buttons()

    def _close_sessions_for_site(self, site_name: str):
        session_ids = [sid for sid, session in self.sessions.items() if session.site.name == site_name]
        for session_id in session_ids:
            self._close_session(session_id)

    def _switch_session_site(self, session_id: str):
        session = self.sessions.get(session_id)
        if not session:
            return
        selected_name = session.selector.currentData()
        site = next((cfg for cfg in self.sites if cfg.name == selected_name), None)
        if not site:
            return
        session.site = site
        session.panel.set_session_context(session_id, site.name)
        session.status_label.setText("Disconnected")
        self._set_active_session(session_id)

    def _connect_session(self, session_id: str):
        session = self.sessions.get(session_id)
        if not session:
            return
        site = session.site
        if site.auth_method == "password" and not site.password:
            pwd, ok = QInputDialog.getText(
                self,
                "Password Required",
                f"Password for {site.username}@{site.host}:",
            )
            if not ok:
                return
            site.password = pwd
        if not site.remote_root or not site.remote_root.strip():
            site.remote_root = "/"
        session.connected = True
        session.status_label.setText(f"Connected: {site.name}")
        session.panel.set_session_context(session_id, site.name)
        self._list_remote_dir(session_id, site.remote_root)

    def _list_remote_dir(self, session_id: str, path: str, parent_item: Optional[QTreeWidgetItem] = None):
        session = self.sessions.get(session_id)
        if not session:
            return
        thread = ListDirThread(session.site, path, parent_item)
        thread.list_completed.connect(
            lambda remote_path, entries, item, sid=session_id: self._on_list_completed(sid, remote_path, entries, item)
        )
        thread.list_failed.connect(lambda remote_path, msg, sid=session_id: self._on_list_failed(sid, remote_path, msg))
        self._start_thread(thread)

    def _on_list_completed(self, session_id: str, path: str, entries: list, parent_item: Optional[QTreeWidgetItem]):
        session = self.sessions.get(session_id)
        if not session:
            return
        if parent_item:
            session.panel.populate_node(parent_item, entries)
        else:
            session.panel.set_path(path)
            session.panel.set_root_entries(entries)

    def _on_list_failed(self, session_id: str, path: str, msg: str):
        session = self.sessions.get(session_id)
        if session:
            session.connected = False
            session.status_label.setText("Disconnected")
        self._log(f"List failed ({path}): {msg}")
        QMessageBox.critical(self, "Error", msg)

    def _on_remote_entry_activated(self, session_id: str, entry: RemoteEntry):
        session = self.sessions.get(session_id)
        if session:
            self._log(f"[{session.site.name}] Activated: {entry.path}")

    def _remote_expand(self, session_id: str, path: str, item: QTreeWidgetItem):
        self._list_remote_dir(session_id, path, item)

    def _remote_go_up(self, session_id: str):
        session = self.sessions.get(session_id)
        if not session:
            return
        parent = get_remote_parent(session.panel.current_path)
        if parent:
            ensure_in_sandbox(parent, session.site.remote_root)
            self._list_remote_dir(session_id, parent)

    def _remote_refresh(self, session_id: str):
        session = self.sessions.get(session_id)
        if session:
            self._list_remote_dir(session_id, session.panel.current_path)

    def _remote_refresh_node(self, session_id: str, path: str, item: QTreeWidgetItem):
        self._list_remote_dir(session_id, path, item)

    def _remote_mkdir(self, session_id: str, name: str, parent_item: QTreeWidgetItem = None):
        session = self.sessions.get(session_id)
        if not session:
            return
        parent_path = session.panel.get_current_target_dir()
        if parent_item:
            entry = parent_item.data(0, Qt.UserRole)
            if entry:
                parent_path = entry.path
        full = join_remote_path(parent_path, name)
        thread = RemoteOpThread(session.site, "mkdir", full)
        thread.op_done.connect(lambda sid=session_id: self._remote_refresh(sid))
        thread.op_failed.connect(lambda msg: self._op_error("mkdir", msg))
        self._start_thread(thread)

    def _remote_delete(self, session_id: str, entry: RemoteEntry):
        session = self.sessions.get(session_id)
        if not session:
            return
        cmd = "remove_dir_recursive" if entry.is_dir else "remove_file"
        thread = RemoteOpThread(session.site, cmd, entry.path)
        thread.op_done.connect(lambda sid=session_id: self._remote_refresh(sid))
        thread.op_failed.connect(lambda msg: self._op_error("delete", msg))
        self._start_thread(thread)

    def _remote_rename(self, session_id: str, entry: RemoteEntry, new_name: str):
        session = self.sessions.get(session_id)
        if not session:
            return
        parent = get_remote_parent(entry.path) or session.panel.current_path
        new_path = join_remote_path(parent, new_name)
        thread = RemoteOpThread(session.site, "rename", entry.path, new_path)
        thread.op_done.connect(lambda sid=session_id: self._remote_refresh(sid))
        thread.op_failed.connect(lambda msg: self._op_error("rename", msg))
        self._start_thread(thread)

    def _upload_files(self, session_id: str):
        self._upload_paths(session_id, self.local_panel.get_selected_paths())

    def _upload_paths(self, session_id: str, paths: list, target_item: QTreeWidgetItem = None):
        session = self.sessions.get(session_id)
        if not session or not paths:
            return
        remote_dir = session.panel.current_path
        if target_item:
            entry = target_item.data(0, Qt.UserRole)
            if entry:
                remote_dir = entry.path if entry.is_dir else get_remote_parent(entry.path)
        for local_path in paths:
            if os.path.isfile(local_path):
                fname = os.path.basename(local_path)
                remote_path = join_remote_path(remote_dir, fname)
                size = os.path.getsize(local_path)
                engine = self._resolve_transfer_engine(session.site, size)
                task = TaskScheduler.create_upload_task(
                    local_path,
                    remote_path,
                    size,
                    engine=engine,
                    auto_engine=False,
                    dst_site=session.site,
                    dst_session_id=session.session_id,
                    dst_display_name=session.site.name,
                )
                self.scheduler.add_task(task)
            elif os.path.isdir(local_path):
                self._enqueue_dir_upload(session_id, local_path, remote_dir)

    def _enqueue_dir_upload(self, session_id: str, local_dir: str, remote_parent: str):
        session = self.sessions.get(session_id)
        if not session:
            return
        remote_dir = join_remote_path(remote_parent, os.path.basename(local_dir))
        total_files, total_bytes = self._scan_local_dir(local_dir)
        task = TaskScheduler.create_folder_upload_task(
            local_dir,
            remote_dir,
            total_files,
            total_bytes,
            dst_site=session.site,
            dst_session_id=session.session_id,
            dst_display_name=session.site.name,
        )
        self.scheduler.add_task(task)

    def _download_entry(self, session_id: str, entry: RemoteEntry):
        local_dir = self.local_panel.get_current_dir()
        if entry.is_dir:
            self._enqueue_dir_download(session_id, entry.path, local_dir)
            return
        session = self.sessions.get(session_id)
        if not session:
            return
        local_path = os.path.join(local_dir, entry.name)
        engine = self._resolve_transfer_engine(session.site, entry.size)
        task = TaskScheduler.create_download_task(
            entry.path,
            local_path,
            entry.size,
            engine=engine,
            auto_engine=False,
            src_site=session.site,
            src_session_id=session.session_id,
            src_display_name=session.site.name,
        )
        self.scheduler.add_task(task)

    def _download_paths(self, src_session_id: str, remote_paths: list, target_local_dir: str):
        session = self.sessions.get(src_session_id) if src_session_id else self._current_session()
        if not session:
            return
        for remote_path in remote_paths:
            entry = self._find_remote_entry_by_path(session.panel, remote_path)
            name = entry.name if entry else os.path.basename(remote_path)
            size = entry.size if entry else 0
            if entry and entry.is_dir:
                self._enqueue_dir_download(session.session_id, remote_path, target_local_dir)
                continue
            task = TaskScheduler.create_download_task(
                remote_path,
                os.path.join(target_local_dir, name),
                size,
                engine=self._resolve_transfer_engine(session.site, size),
                auto_engine=False,
                src_site=session.site,
                src_session_id=session.session_id,
                src_display_name=session.site.name,
            )
            self.scheduler.add_task(task)

    def _enqueue_dir_download(self, session_id: str, remote_dir: str, local_parent: str):
        session = self.sessions.get(session_id)
        if not session:
            return
        thread = ScanRemoteDirThread(session.site, remote_dir)

        def on_scanned(path: str, total_files: int, total_bytes: int, sid=session_id):
            session_obj = self.sessions.get(sid)
            if not session_obj:
                return
            local_dir = os.path.join(local_parent, os.path.basename(path.rstrip("/")))
            task = TaskScheduler.create_folder_download_task(
                path,
                local_dir,
                max(1, total_files),
                total_bytes,
                src_site=session_obj.site,
                src_session_id=session_obj.session_id,
                src_display_name=session_obj.site.name,
            )
            self.scheduler.add_task(task)

        thread.scan_completed.connect(on_scanned)
        thread.scan_failed.connect(lambda path, msg: self._log(f"Download scan failed ({path}): {msg}"))
        self._start_thread(thread)

    def _remote_to_remote_drop(self, src_session_id: str, dst_session_id: str, remote_paths: list[str], target_item: QTreeWidgetItem = None):
        src_session = self.sessions.get(src_session_id)
        dst_session = self.sessions.get(dst_session_id)
        if not src_session or not dst_session:
            return
        dst_dir = dst_session.panel.current_path
        if target_item:
            entry = target_item.data(0, Qt.UserRole)
            if entry:
                dst_dir = entry.path if entry.is_dir else get_remote_parent(entry.path)
        for remote_path in remote_paths:
            entry = self._find_remote_entry_by_path(src_session.panel, remote_path)
            name = entry.name if entry else os.path.basename(remote_path)
            dst_path = join_remote_path(dst_dir, name)
            if entry and entry.is_dir:
                self._enqueue_remote_dir_transfer(src_session, dst_session, entry.path, dst_path)
                continue
            size = entry.size if entry else 0
            task = TaskScheduler.create_remote_to_remote_task(
                remote_path,
                dst_path,
                size,
                src_site=src_session.site,
                dst_site=dst_session.site,
                src_session_id=src_session.session_id,
                dst_session_id=dst_session.session_id,
            )
            self.scheduler.add_task(task)

    def _enqueue_remote_dir_transfer(self, src_session: RemoteSession, dst_session: RemoteSession, src_dir: str, dst_dir: str):
        thread = ScanRemoteDirThread(src_session.site, src_dir)

        def on_scanned(path: str, total_files: int, total_bytes: int):
            task = TaskScheduler.create_folder_remote_to_remote_task(
                path,
                dst_dir,
                max(1, total_files),
                total_bytes,
                src_site=src_session.site,
                dst_site=dst_session.site,
                src_session_id=src_session.session_id,
                dst_session_id=dst_session.session_id,
            )
            self.scheduler.add_task(task)

        thread.scan_completed.connect(on_scanned)
        thread.scan_failed.connect(lambda path, msg: self._log(f"Remote transfer scan failed ({path}): {msg}"))
        self._start_thread(thread)

    def _scan_local_dir(self, path: str) -> tuple[int, int]:
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

    def _find_remote_entry_by_path(self, panel: RemotePanel, remote_path: str) -> Optional[RemoteEntry]:
        tree = panel.tree

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

    def _current_session(self) -> Optional[RemoteSession]:
        if self._active_session_id:
            return self.sessions.get(self._active_session_id)
        if self._session_order:
            return self.sessions.get(self._session_order[-1])
        return None

    def _set_active_session(self, session_id: str):
        if session_id not in self.sessions:
            return
        self._active_session_id = session_id
        self._update_active_session_styles()

    def _update_active_session_styles(self):
        for session_id, session in self.sessions.items():
            if session_id == self._active_session_id:
                session.container.setStyleSheet(
                    "QFrame { border: 2px solid palette(highlight); border-radius: 4px; }"
                )
            else:
                session.container.setStyleSheet("QFrame { border: 1px solid palette(mid); border-radius: 4px; }")

    def _refresh_remote_area(self):
        has_sessions = bool(self.sessions)
        self.remote_placeholder.setVisible(not has_sessions)
        self.remote_splitter.setVisible(has_sessions)

    def _rebalance_remote_splitter(self):
        count = self.remote_splitter.count()
        if count <= 0:
            return
        total = max(1200, self.remote_splitter.size().width(), count * 320)
        size = max(280, total // count)
        self.remote_splitter.setSizes([size] * count)

    def _activate_and_run(self, session_id: str, func, *args):
        self._set_active_session(session_id)
        func(session_id, *args)

    def _refresh_tasks(self):
        self.task_center.set_tasks(self.scheduler.get_all_tasks())

    def cancel_task(self, task_id: str):
        self.scheduler.cancel_task(task_id)

    def pause_task(self, task_id: str):
        self.scheduler.pause_task(task_id)

    def resume_task(self, task_id: str):
        self.scheduler.resume_task(task_id)

    def restart_task(self, task_id: str):
        self.scheduler.restart_task(task_id)

    def clear_finished_tasks(self):
        with self.scheduler.task_lock:
            ids = [tid for tid, task in self.scheduler.tasks.items() if task.is_finished]
            for tid in ids:
                del self.scheduler.tasks[tid]

    def _resolve_transfer_engine(self, site: SiteConfig, file_size: int) -> str:
        override = self.transfer_override_combo.currentData()
        base_protocol = override if override in ("sftp", "scp") else site.default_transfer_protocol
        if base_protocol != "scp" and file_size >= self.scheduler.parallel_threshold:
            return "parallel"
        return base_protocol

    def _populate_site_selector(self, selector: QComboBox, current_name: Optional[str] = None):
        selector.blockSignals(True)
        selector.clear()
        for site in self.sites:
            selector.addItem(site.name, site.name)
        if current_name:
            idx = selector.findData(current_name)
            if idx >= 0:
                selector.setCurrentIndex(idx)
        selector.blockSignals(False)

    def _refresh_session_selectors(self):
        for session in self.sessions.values():
            current_name = session.selector.currentData() or session.site.name
            self._populate_site_selector(session.selector, current_name)

    def _start_thread(self, thread: QThread):
        self._bg_threads.append(thread)
        thread.finished.connect(lambda: self._bg_threads.remove(thread) if thread in self._bg_threads else None)
        thread.start()

    def _op_error(self, op: str, msg: str):
        self._log(f"{op} failed: {msg}")
        QMessageBox.critical(self, f"{op} Error", msg)

    def _load_saved_sites(self):
        saved = self.site_store.load()
        self.sites = saved
        for site in saved:
            self.site_list.addItem(site.name)
        self._update_site_action_buttons()

    def _save_sites(self):
        self.site_store.save(self.sites)

    def _update_site_action_buttons(self):
        has_site = self._selected_site() is not None
        self.btn_edit_site.setEnabled(has_site)
        self.btn_remove_site.setEnabled(has_site)
        self.btn_check_connection.setEnabled(has_site)
        self.btn_new_session.setEnabled(has_site)
        self.btn_remove_session.setEnabled(bool(self.sessions))

    def _log(self, msg: str):
        self.log_text.append(msg)
        self.logger.info(msg)

    def closeEvent(self, event):
        self._task_timer.stop()
        self.scheduler.stop()
        self._save_sites()
        event.accept()
