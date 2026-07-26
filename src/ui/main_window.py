"""Main application window with dynamic remote sessions."""
import os
import uuid
from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtCore import QSize
from PySide6.QtGui import QDesktopServices
from shiboken6 import isValid
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    )
from PySide6.QtWidgets import QTreeWidgetItem
from PySide6.QtCore import QUrl

from src.core.scheduler import TaskScheduler
from src.engines.sftp_engine import SftpEngine
from src.services.connection_checker import ConnectionChecker
from src.services.site_store import SiteStore
from src.shared.errors import SSHFerryError
from src.shared.logging_ import setup_logger
from src.shared.models import RemoteEntry, SiteConfig
from src.shared.paths import ensure_in_sandbox, get_remote_parent, join_remote_path, normalize_remote_path
from src.shared.remote_scan import summarize_remote_tree_via_shell
from src.ui.theme import TOKENS
from src.ui.panels.local_panel import LocalPanel
from src.ui.panels.remote_panel import RemotePanel
from src.ui.panels.task_center import TaskCenterPanel
from src.ui.widgets.site_editor import SiteEditorDialog
from src.ui.widgets.feedback import install_button_feedback


def _env_int(name: str, default: int, min_value: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return max(min_value, int(raw))
    except ValueError:
        return default


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


class RemoteDeleteManyThread(QThread):
    op_done = Signal()
    op_failed = Signal(str)

    def __init__(self, site_config: SiteConfig, entries: list[RemoteEntry]):
        super().__init__()
        self.site_config = site_config
        self.entries = entries

    def run(self):
        engine = SftpEngine(self.site_config)
        try:
            engine.connect()
            for entry in sorted(self.entries, key=lambda item: item.path.count("/"), reverse=True):
                if entry.is_dir:
                    engine.remove_dir_recursive(entry.path)
                else:
                    engine.remove_file(entry.path)
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
    scan_completed = Signal(str, object, object)
    scan_failed = Signal(str, str)

    def __init__(self, site_config: SiteConfig, remote_path: str):
        super().__init__()
        self.site_config = site_config
        self.remote_path = remote_path

    def run(self):
        engine = SftpEngine(self.site_config)
        try:
            engine.connect()
            fast_summary = summarize_remote_tree_via_shell(engine, self.remote_path)
            if fast_summary is not None:
                total_files, total_bytes = fast_summary
            else:
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
        return self._scan_recursive_inner(engine, path, visited=set())

    def _scan_recursive_inner(self, engine: SftpEngine, path: str, visited: set[str]) -> tuple[int, int]:
        canonical_path = self._canonical_remote_walk_path(engine, path)
        if canonical_path in visited:
            return 0, 0
        visited.add(canonical_path)
        total_files = 0
        total_bytes = 0
        for entry in engine.list_dir(path):
            if entry.is_dir:
                sub_files, sub_bytes = self._scan_recursive_inner(engine, entry.path, visited)
                total_files += sub_files
                total_bytes += sub_bytes
            else:
                total_files += 1
                total_bytes += entry.size
        return total_files, total_bytes

    @staticmethod
    def _canonical_remote_walk_path(engine: SftpEngine, remote_path: str) -> str:
        normalized_path = normalize_remote_path(remote_path)
        sftp_client = getattr(engine, "sftp_client", None)
        normalize_fn = getattr(sftp_client, "normalize", None)
        if callable(normalize_fn):
            try:
                resolved_path = normalize_fn(normalized_path)
            except Exception:
                return normalized_path
            if isinstance(resolved_path, str) and resolved_path:
                return normalize_remote_path(resolved_path)
        return normalized_path


class ScanLocalDirThread(QThread):
    scan_completed = Signal(str, object, object)
    scan_failed = Signal(str, str)

    def __init__(self, local_path: str):
        super().__init__()
        self.local_path = local_path

    def run(self):
        try:
            total_files, total_bytes = self._scan_recursive(self.local_path)
            self.scan_completed.emit(self.local_path, total_files, total_bytes)
        except Exception as exc:
            self.scan_failed.emit(self.local_path, str(exc))

    def _scan_recursive(self, path: str) -> tuple[int, int]:
        total_files = 0
        total_bytes = 0
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_file(follow_symlinks=False):
                    total_files += 1
                    total_bytes += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    sub_files, sub_bytes = self._scan_recursive(entry.path)
                    total_files += sub_files
                    total_bytes += sub_bytes
        return total_files, total_bytes


@dataclass
class RemoteSession:
    session_id: str
    site: SiteConfig
    panel: RemotePanel
    container: QWidget
    status_label: QLabel
    refresh_button: QPushButton
    selected_box: QCheckBox
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
        self._list_request_counter = 0
        self._inflight_list_requests: dict[tuple[str, str, str], int] = {}
        self._pending_list_requests: dict[tuple[str, str, str], dict] = {}
        self._latest_list_response_ids: dict[tuple[str, str] | tuple[str, str, str], int] = {}
        self._session_list_activity: dict[str, int] = {}
        self._max_remote_list_concurrency = _env_int("SSHFERRY_REMOTE_LIST_MAX_CONCURRENT", 3, 1)
        self._topbar_snapshot: tuple[int, int, int] | None = None

        self.setWindowTitle(f"SSHFerry #{self._window_number}")
        self.resize(1520, 900)

        self._init_ui()
        self._load_saved_sites()
        self.scheduler.start()

    def _init_ui(self):
        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(TOKENS.spacing_lg, TOKENS.spacing_lg, TOKENS.spacing_lg, TOKENS.spacing_lg)
        root_layout.setSpacing(TOKENS.spacing_md)

        root_layout.addWidget(self._build_top_bar())

        content_shell = QWidget()
        content_layout = QHBoxLayout(content_shell)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        root_layout.addWidget(content_shell, 1)

        left = QFrame()
        left.setObjectName("panelCard")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(TOKENS.spacing_lg, TOKENS.spacing_lg, TOKENS.spacing_lg, TOKENS.spacing_lg)
        left_lay.setSpacing(TOKENS.spacing_sm)
        sites_title = QLabel("Sites")
        sites_title.setObjectName("sectionTitle")
        left_lay.addWidget(sites_title)
        self.site_list = QListWidget()
        self.site_list.setObjectName("siteList")
        self.site_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.site_list.itemClicked.connect(self._on_site_selected)
        # itemClicked only fires for mouse clicks; keep buttons in sync for
        # keyboard-driven selection changes too.
        self.site_list.itemSelectionChanged.connect(self._update_site_action_buttons)
        self.site_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.site_list.customContextMenuRequested.connect(self._show_site_context_menu)
        left_lay.addWidget(self.site_list)

        site_actions = QFrame()
        site_actions.setObjectName("toolbarCard")
        site_actions_layout = QHBoxLayout(site_actions)
        site_actions_layout.setContentsMargins(TOKENS.spacing_sm, TOKENS.spacing_sm, TOKENS.spacing_sm, TOKENS.spacing_sm)
        site_actions_layout.setSpacing(TOKENS.spacing_xs)

        self.btn_add_site = QPushButton()
        self.btn_add_site.setProperty("chrome", "icon")
        self.btn_add_site.setProperty("variant", "primary")
        self.btn_add_site.setIcon(self.style().standardIcon(QStyle.SP_FileDialogNewFolder))
        self.btn_add_site.setToolTip("Add Site")
        self.btn_add_site.clicked.connect(self._add_site)
        self._configure_site_icon_button(self.btn_add_site)
        site_actions_layout.addWidget(self.btn_add_site, 1)

        self.btn_edit_site = QPushButton()
        self.btn_edit_site.setProperty("chrome", "icon")
        self.btn_edit_site.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        self.btn_edit_site.setToolTip("Edit Site")
        self.btn_edit_site.clicked.connect(self._edit_site)
        self._configure_site_icon_button(self.btn_edit_site)
        site_actions_layout.addWidget(self.btn_edit_site, 1)

        self.btn_check_connection = QPushButton()
        self.btn_check_connection.setProperty("chrome", "icon")
        self.btn_check_connection.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.btn_check_connection.setToolTip("Check Connection")
        self.btn_check_connection.clicked.connect(self._check_connection)
        self._configure_site_icon_button(self.btn_check_connection)
        site_actions_layout.addWidget(self.btn_check_connection, 1)

        self.btn_remove_site = QPushButton()
        self.btn_remove_site.setProperty("chrome", "icon")
        self.btn_remove_site.setProperty("variant", "danger")
        self.btn_remove_site.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.btn_remove_site.setToolTip("Remove Site")
        self.btn_remove_site.clicked.connect(self._remove_site)
        self._configure_site_icon_button(self.btn_remove_site)
        site_actions_layout.addWidget(self.btn_remove_site, 1)
        left_lay.addWidget(site_actions)

        self.btn_new_session = QPushButton("Connect")
        self.btn_new_session.setProperty("variant", "primary")
        self.btn_new_session.clicked.connect(self._create_session_from_selection)
        left_lay.addWidget(self.btn_new_session)

        self.btn_remove_session = QPushButton("Disconnect")
        self.btn_remove_session.setProperty("variant", "danger")
        self.btn_remove_session.clicked.connect(self._remove_selected_sessions)
        left_lay.addWidget(self.btn_remove_session)

        protocol_label = QLabel("Task Protocol Override")
        protocol_label.setObjectName("sectionTitle")
        left_lay.addWidget(protocol_label)
        self.transfer_override_combo = QComboBox()
        self.transfer_override_combo.addItem("Auto (Site Default)", "auto")
        self.transfer_override_combo.addItem("SFTP", "sftp")
        self.transfer_override_combo.addItem("SCP", "scp")
        left_lay.addWidget(self.transfer_override_combo)
        left.setMinimumWidth(170)
        left.setMaximumWidth(420)

        self.local_panel = LocalPanel()
        self.local_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.local_panel.file_selected.connect(self._on_local_file_selected)
        self.local_panel.files_dropped.connect(self._download_paths)
        self.local_panel.request_upload_paths.connect(self._upload_local_paths_to_active_remote)

        self.remote_area = QFrame()
        self.remote_area.setObjectName("panelCard")
        self.remote_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        remote_area_layout = QVBoxLayout(self.remote_area)
        remote_area_layout.setContentsMargins(TOKENS.spacing_sm, TOKENS.spacing_sm, TOKENS.spacing_sm, TOKENS.spacing_sm)
        remote_area_layout.setSpacing(0)
        self.remote_empty_state = self._build_remote_empty_state()
        self.remote_splitter = QSplitter(Qt.Horizontal)
        self.remote_splitter.setChildrenCollapsible(False)
        self.remote_splitter.setHandleWidth(10)
        self.remote_splitter.setOpaqueResize(False)
        self.remote_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        remote_area_layout.addWidget(self.remote_empty_state)
        remote_area_layout.addWidget(self.remote_splitter, 1)
        self._refresh_remote_area()

        panel_splitter = QSplitter(Qt.Horizontal)
        panel_splitter.setChildrenCollapsible(False)
        panel_splitter.setHandleWidth(10)
        panel_splitter.setOpaqueResize(False)
        panel_splitter.addWidget(self.local_panel)
        panel_splitter.addWidget(self.remote_area)
        panel_splitter.setStretchFactor(0, 1)
        panel_splitter.setStretchFactor(1, 1)
        panel_splitter.setSizes([560, 680])

        bottom_splitter = QSplitter(Qt.Horizontal)
        self.task_center = TaskCenterPanel()
        self.task_center.request_pause.connect(self.pause_task)
        self.task_center.request_resume.connect(self.resume_task)
        self.task_center.request_cancel.connect(self.cancel_task)
        self.task_center.request_restart.connect(self.restart_task)
        self.task_center.request_clear_finished.connect(self.clear_finished_tasks)
        bottom_splitter.addWidget(self.task_center)

        log_panel = QFrame()
        log_panel.setObjectName("panelCard")
        log_panel.setMaximumWidth(260)
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(TOKENS.spacing_sm, TOKENS.spacing_sm, TOKENS.spacing_sm, TOKENS.spacing_sm)
        log_layout.setSpacing(2)
        log_title = QLabel("Log")
        log_title.setObjectName("sectionTitle")
        log_layout.addWidget(log_title)
        log_hint = QLabel("Recent runtime output")
        log_hint.setObjectName("mutedLabel")
        log_layout.addWidget(log_hint)

        self.log_text = QTextEdit()
        self.log_text.setObjectName("logOutput")
        self.log_text.setReadOnly(True)
        self.log_text.document().setMaximumBlockCount(1500)
        log_layout.addWidget(self.log_text, 1)
        bottom_splitter.addWidget(log_panel)
        bottom_splitter.setStretchFactor(0, 2)
        bottom_splitter.setStretchFactor(1, 0)
        bottom_splitter.setSizes([1160, 220])

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(panel_splitter)
        right_splitter.addWidget(bottom_splitter)
        right_splitter.setStretchFactor(0, 5)
        right_splitter.setStretchFactor(1, 2)
        right_splitter.setSizes([760, 220])

        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setHandleWidth(10)
        main_splitter.setOpaqueResize(False)
        main_splitter.addWidget(left)
        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 4)
        main_splitter.setSizes([200, 1280])
        main_splitter.setStretchFactor(1, 1)
        content_layout.addWidget(main_splitter)

        self.setStatusBar(QStatusBar())
        self._create_menu_bar()

        self._task_timer = QTimer()
        self._task_timer.timeout.connect(self._refresh_tasks)
        self._task_timer.start(500)
        install_button_feedback(self)
        self._update_site_action_buttons()

    def _show_site_context_menu(self, pos):
        item = self.site_list.itemAt(pos)
        if item:
            self.site_list.setCurrentItem(item)
        menu = QMenu(self)
        act_add = menu.addAction("Add Site")
        act_add.triggered.connect(self._add_site)
        if self._selected_site():
            act_edit = menu.addAction("Edit Site")
            act_edit.triggered.connect(self._edit_site)
            act_check = menu.addAction("Check Connection")
            act_check.triggered.connect(self._check_connection)
            act_remove = menu.addAction("Remove Site")
            act_remove.triggered.connect(self._remove_site)
            menu.addSeparator()
            act_connect = menu.addAction("Connect")
            act_connect.triggered.connect(self._create_session_from_selection)
        menu.exec(self.site_list.mapToGlobal(pos))

    def _build_top_bar(self) -> QWidget:
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setMinimumHeight(52)
        top_bar.setMaximumHeight(60)
        layout = QHBoxLayout(top_bar)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(10)

        title = QLabel("SSHFerry")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        text_box = QWidget()
        text_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)
        text_layout.addWidget(title, 0, Qt.AlignLeft | Qt.AlignVCenter)

        status_box = QWidget()
        status_box.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        status_layout = QHBoxLayout(status_box)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(10)
        self.topbar_sites_label = QLabel("Sites: 0")
        self.topbar_sites_label.setObjectName("summaryLabel")
        self.topbar_sessions_label = QLabel("Sessions: 0")
        self.topbar_sessions_label.setObjectName("summaryLabel")
        self.topbar_tasks_label = QLabel("Tasks: 0")
        self.topbar_tasks_label.setObjectName("summaryLabel")
        status_layout.addWidget(self.topbar_sites_label)
        status_layout.addWidget(self.topbar_sessions_label)
        status_layout.addWidget(self.topbar_tasks_label)

        layout.addWidget(text_box, 1)
        layout.addWidget(status_box, 0, Qt.AlignRight | Qt.AlignVCenter)

        return top_bar

    def _build_remote_empty_state(self) -> QWidget:
        empty = QFrame()
        empty.setObjectName("toolbarCard")
        empty.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(empty)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(2)

        art = QLabel("SSH")
        art.setObjectName("titleLabel")
        art.setAlignment(Qt.AlignCenter)
        art.setStyleSheet(f"color: {TOKENS.accent};")

        title = QLabel("No remote sessions open")
        title.setObjectName("sectionTitle")
        title.setAlignment(Qt.AlignCenter)

        body = QLabel("Select a site on the left, then connect to open a remote workspace.")
        body.setObjectName("mutedLabel")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)

        button = QPushButton("Quick Connect")
        button.setProperty("variant", "primary")
        button.clicked.connect(self._create_session_from_selection)

        layout.addStretch(1)
        layout.addWidget(art)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(button, 0, Qt.AlignCenter)
        layout.addStretch(1)
        return empty

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

    def _selected_sites(self) -> list[SiteConfig]:
        selected_sites: list[SiteConfig] = []
        for item in self.site_list.selectedItems():
            idx = self.site_list.row(item)
            if 0 <= idx < len(self.sites):
                selected_sites.append(self.sites[idx])
        if selected_sites:
            return selected_sites
        current = self._selected_site()
        return [current] if current else []

    def _selected_session_ids(self) -> list[str]:
        selected_ids = [
            session_id
            for session_id, session in self.sessions.items()
            if session.selected_box.isChecked()
        ]
        if selected_ids:
            return selected_ids
        current = self._current_session()
        return [current.session_id] if current else []

    @staticmethod
    def _configure_site_icon_button(button: QPushButton) -> None:
        button.setObjectName("siteActionButton")
        button.setMinimumHeight(42)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setIconSize(QSize(30, 30))

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
        sites = self._selected_sites()
        if not sites:
            QMessageBox.warning(self, "No Site Selected", "Select a site first.")
            return
        for site in sites:
            matching_sessions = [
                session for session in self.sessions.values() if session.site.name == site.name
            ]
            if matching_sessions:
                for session in matching_sessions:
                    self._refresh_or_reconnect_session(session.session_id)
                continue
            session_id = self._create_session(site)
            self._connect_session(session_id)

    def _create_session(self, site: SiteConfig) -> str:
        session_id = str(uuid.uuid4())
        container = QFrame()
        container.setObjectName("sessionCard")
        container.setProperty("active", False)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(TOKENS.spacing_sm, TOKENS.spacing_sm, TOKENS.spacing_sm, TOKENS.spacing_sm)
        layout.setSpacing(TOKENS.spacing_xs)

        header = QHBoxLayout()
        header.setSpacing(TOKENS.spacing_sm)
        selected_box = QCheckBox()
        selected_box.setToolTip("Select this session for batch disconnect")
        selected_box.stateChanged.connect(lambda _state, sid=session_id: self._update_site_action_buttons())
        selector = QComboBox()
        selector.setObjectName("sessionSiteSelector")
        selector.setMinimumWidth(220)
        self._populate_site_selector(selector, site.name)
        status_label = QLabel("Disconnected")
        status_label.setObjectName("mutedLabel")
        btn_refresh = QPushButton("Refresh")
        btn_refresh.setProperty("variant", "ghost")
        btn_refresh.clicked.connect(lambda: self._activate_and_run(session_id, self._refresh_or_reconnect_session))
        btn_close = QPushButton("Close")
        btn_close.setProperty("variant", "danger")
        btn_close.clicked.connect(lambda: self._close_session(session_id))
        header.addWidget(selected_box)
        header.addWidget(selector, 1)
        header.addWidget(btn_refresh)
        header.addWidget(btn_close)
        header.addWidget(status_label)
        layout.addLayout(header)

        panel = RemotePanel()
        panel.set_session_context(session_id, site.name)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(panel, 1)

        session = RemoteSession(session_id, site, panel, container, status_label, btn_refresh, selected_box, selector)
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
        panel.request_delete_entries.connect(lambda entries, sid=session_id: self._activate_and_run(sid, self._remote_delete_entries, entries))
        panel.request_rename.connect(
            lambda entry, new_name, sid=session_id: self._activate_and_run(sid, self._remote_rename, entry, new_name)
        )
        panel.request_upload.connect(
            lambda target_item=None, sid=session_id: self._activate_and_run(sid, self._upload_files, target_item)
        )
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
        return session_id

    def _remove_selected_sessions(self):
        session_ids = self._selected_session_ids()
        for session_id in list(session_ids):
            self._close_session(session_id)

    def _close_session(self, session_id: str):
        session = self.sessions.get(session_id)
        if not session:
            return
        previous_active = self._active_session_id
        self.sessions.pop(session_id, None)
        if session_id in self._session_order:
            self._session_order.remove(session_id)
        if self._active_session_id == session_id:
            self._active_session_id = self._session_order[-1] if self._session_order else None
        self._session_list_activity.pop(session_id, None)
        self._inflight_list_requests = {
            key: value for key, value in self._inflight_list_requests.items() if key[0] != session_id
        }
        self._pending_list_requests = {
            key: value for key, value in self._pending_list_requests.items() if key[0] != session_id
        }
        self._latest_list_response_ids = {
            key: value for key, value in self._latest_list_response_ids.items() if key[0] != session_id
        }
        session.container.setParent(None)
        session.container.deleteLater()
        self._refresh_remote_area()
        self._rebalance_remote_splitter()
        self._update_active_session_styles(previous_active, self._active_session_id)
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
        self._session_list_activity.pop(session_id, None)
        session.refresh_button.setEnabled(True)
        self._inflight_list_requests = {
            key: value for key, value in self._inflight_list_requests.items() if key[0] != session_id
        }
        self._pending_list_requests = {
            key: value for key, value in self._pending_list_requests.items() if key[0] != session_id
        }
        self._latest_list_response_ids = {
            key: value for key, value in self._latest_list_response_ids.items() if key[0] != session_id
        }
        session.panel.set_session_context(session_id, site.name)
        session.panel.reset_view_state()
        session.panel.set_path(site.remote_root or "/")
        session.connected = False
        session.status_label.setText("Disconnected")
        self._set_active_session(session_id)

    def _ensure_site_credentials(self, site: SiteConfig) -> bool:
        if site.auth_method == "password" and not site.password:
            pwd, ok = QInputDialog.getText(
                self,
                "Password Required",
                f"Password for {site.username}@{site.host}:",
                QLineEdit.Password,
            )
            if not ok:
                return False
            site.password = pwd
        if not site.remote_root or not site.remote_root.strip():
            site.remote_root = "/"
        return True

    def _connect_session(self, session_id: str, target_path: Optional[str] = None):
        session = self.sessions.get(session_id)
        if not session:
            return
        site = session.site
        if not self._ensure_site_credentials(site):
            return
        session.connected = True
        session.status_label.setText(f"Connected: {site.name}")
        session.panel.set_session_context(session_id, site.name)
        self._list_remote_dir(session_id, target_path or site.remote_root, retry_on_failure=False)

    @staticmethod
    def _list_request_scope(parent_item: Optional[QTreeWidgetItem]) -> str:
        return "node" if parent_item is not None else "root"

    def _list_request_key(
        self,
        session_id: str,
        path: str,
        parent_item: Optional[QTreeWidgetItem],
    ) -> tuple[str, str, str]:
        return (session_id, self._list_request_scope(parent_item), path)

    def _list_response_scope_key(
        self,
        session_id: str,
        path: str,
        parent_item: Optional[QTreeWidgetItem],
    ) -> tuple[str, str] | tuple[str, str, str]:
        scope = self._list_request_scope(parent_item)
        if scope == "root":
            return (session_id, scope)
        return (session_id, scope, path)

    def _begin_session_list_activity(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if not session:
            return
        active = self._session_list_activity.get(session_id, 0) + 1
        self._session_list_activity[session_id] = active
        if active == 1:
            session.refresh_button.setEnabled(False)

    def _end_session_list_activity(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if not session:
            self._session_list_activity.pop(session_id, None)
            return
        active = max(0, self._session_list_activity.get(session_id, 0) - 1)
        if active == 0:
            self._session_list_activity.pop(session_id, None)
            session.refresh_button.setEnabled(True)
        else:
            self._session_list_activity[session_id] = active

    def _queue_list_request(
        self,
        request_key: tuple[str, str, str],
        session_id: str,
        path: str,
        parent_item: Optional[QTreeWidgetItem],
        retry_on_failure: bool,
        suppress_error_dialog: bool,
    ) -> None:
        self._pending_list_requests[request_key] = {
            "session_id": session_id,
            "path": path,
            "parent_item": parent_item if parent_item and isValid(parent_item) else None,
            "retry_on_failure": retry_on_failure,
            "suppress_error_dialog": suppress_error_dialog,
        }

    def _session_inflight_list_count(self, session_id: str) -> int:
        return sum(1 for key in self._inflight_list_requests if key[0] == session_id)

    def _session_list_concurrency_limit(self) -> int:
        return max(1, getattr(self, "_max_remote_list_concurrency", 3))

    def _drain_session_list_queue(self, session_id: str) -> None:
        while self._session_inflight_list_count(session_id) < self._session_list_concurrency_limit():
            for request_key, pending in list(self._pending_list_requests.items()):
                if request_key[0] != session_id:
                    continue
                if request_key in self._inflight_list_requests:
                    continue
                self._pending_list_requests.pop(request_key, None)
                self._list_remote_dir(**pending)
                break
            else:
                return

    def _finalize_list_request(self, request_key: tuple[str, str, str], drain_pending: bool = True) -> None:
        self._inflight_list_requests.pop(request_key, None)
        if drain_pending:
            self._drain_session_list_queue(request_key[0])

    def _list_remote_dir(
        self,
        session_id: str,
        path: str,
        parent_item: Optional[QTreeWidgetItem] = None,
        retry_on_failure: bool = False,
        suppress_error_dialog: bool = False,
    ):
        session = self.sessions.get(session_id)
        if not session:
            return
        request_key = self._list_request_key(session_id, path, parent_item)
        response_scope_key = self._list_response_scope_key(session_id, path, parent_item)
        if (
            request_key in self._inflight_list_requests
            or self._session_inflight_list_count(session_id) >= self._session_list_concurrency_limit()
        ):
            self._queue_list_request(
                request_key,
                session_id,
                path,
                parent_item,
                retry_on_failure,
                suppress_error_dialog,
            )
            return
        self._list_request_counter += 1
        request_id = self._list_request_counter
        self._inflight_list_requests[request_key] = request_id
        self._latest_list_response_ids[response_scope_key] = request_id
        self._begin_session_list_activity(session_id)
        self._start_list_request(
            session_id,
            path,
            parent_item,
            retry_on_failure,
            suppress_error_dialog,
            request_id,
            request_key,
            response_scope_key,
            session.site.name,
        )

    def _start_list_request(
        self,
        session_id: str,
        path: str,
        parent_item: Optional[QTreeWidgetItem],
        retry_on_failure: bool,
        suppress_error_dialog: bool,
        request_id: int,
        request_key: tuple[str, str, str],
        response_scope_key: tuple[str, str] | tuple[str, str, str],
        site_name: str,
    ) -> None:
        session = self.sessions.get(session_id)
        if not session:
            return
        thread = ListDirThread(session.site, path, parent_item)
        thread.list_completed.connect(
            lambda remote_path, entries, item, sid=session_id, rid=request_id, rkey=request_key, scope_key=response_scope_key, site_name=site_name: self._on_list_completed(
                sid,
                remote_path,
                entries,
                item,
                rid,
                rkey,
                scope_key,
                site_name,
            )
        )
        thread.list_failed.connect(
            lambda remote_path, msg, sid=session_id, item=parent_item, retry=retry_on_failure, silent=suppress_error_dialog, rid=request_id, rkey=request_key, scope_key=response_scope_key, site_name=site_name: self._on_list_failed(
                sid, remote_path, msg, item, retry, silent, rid, rkey, scope_key, site_name
            )
        )
        self._start_thread(thread)

    def _on_list_completed(
        self,
        session_id: str,
        path: str,
        entries: list,
        parent_item: Optional[QTreeWidgetItem],
        request_id: int,
        request_key: tuple[str, str, str],
        response_scope_key: tuple[str, str] | tuple[str, str, str],
        site_name: str,
    ):
        session = self.sessions.get(session_id)
        self._end_session_list_activity(session_id)
        self._finalize_list_request(request_key, drain_pending=False)
        try:
            if not session:
                return
            if session.site.name != site_name:
                return
            if self._latest_list_response_ids.get(response_scope_key) != request_id:
                return
            if parent_item:
                target_item = parent_item if isValid(parent_item) else session.panel.find_item_by_path(path)
                if not target_item:
                    self._log(f"[{session.site.name}] Ignored stale list result for {path}")
                    return
                session.panel.populate_node(target_item, entries, preserve_state=True)
            else:
                preserve_state = path == session.panel.current_path
                session.panel.set_path(path)
                session.panel.set_root_entries(entries, preserve_state=preserve_state)
            session.connected = True
            session.status_label.setText(f"Connected: {session.site.name}")
        finally:
            self._drain_session_list_queue(session_id)

    def _on_list_failed(
        self,
        session_id: str,
        path: str,
        msg: str,
        parent_item: Optional[QTreeWidgetItem] = None,
        retry_on_failure: bool = False,
        suppress_error_dialog: bool = False,
        request_id: int = 0,
        request_key: tuple[str, str, str] | None = None,
        response_scope_key: tuple[str, str] | tuple[str, str, str] | None = None,
        site_name: str | None = None,
    ):
        session = self.sessions.get(session_id)
        self._end_session_list_activity(session_id)
        if session and site_name and session.site.name != site_name:
            if request_key is not None:
                self._finalize_list_request(request_key)
            return
        if response_scope_key is not None and self._latest_list_response_ids.get(response_scope_key) != request_id:
            if request_key is not None:
                self._finalize_list_request(request_key)
            return
        if retry_on_failure and session and self._ensure_site_credentials(session.site):
            if request_key is not None:
                self._finalize_list_request(request_key, drain_pending=False)
            self._log(f"Refreshing {session.site.name} after disconnect on {path}")
            self._list_remote_dir(
                session_id,
                path,
                parent_item,
                retry_on_failure=False,
                suppress_error_dialog=suppress_error_dialog,
            )
            return
        if request_key is not None:
            self._finalize_list_request(request_key)
        if session:
            session.connected = False
            session.status_label.setText("Disconnected")
        self._log(f"List failed ({path}): {msg}")
        if not suppress_error_dialog:
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
            self._list_remote_dir(session_id, parent, retry_on_failure=True)

    def _refresh_or_reconnect_session(self, session_id: str):
        session = self.sessions.get(session_id)
        if not session:
            return
        current_path = session.panel.current_path or session.site.remote_root or "/"
        if not self._ensure_site_credentials(session.site):
            return
        session.status_label.setText(f"Refreshing: {session.site.name}")
        self._list_remote_dir(
            session_id,
            current_path,
            retry_on_failure=True,
        )

    def _remote_refresh(self, session_id: str):
        self._refresh_or_reconnect_session(session_id)

    def _remote_refresh_node(self, session_id: str, path: str, item: QTreeWidgetItem):
        session = self.sessions.get(session_id)
        if not session:
            return
        if not self._ensure_site_credentials(session.site):
            return
        session.status_label.setText(f"Refreshing: {session.site.name}")
        self._list_remote_dir(session_id, path, item, retry_on_failure=True)

    def _refresh_remote_path_context(self, session_id: str, path: str | None):
        session = self.sessions.get(session_id)
        if not session:
            return
        refresh_path = path or session.panel.current_path
        if refresh_path == session.panel.current_path:
            self._remote_refresh(session_id)
            return
        item = session.panel.find_item_by_path(refresh_path)
        if item is not None:
            self._remote_refresh_node(session_id, refresh_path, item)
            return
        self._remote_refresh(session_id)

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
        thread.op_done.connect(lambda sid=session_id, path=parent_path: self._refresh_remote_path_context(sid, path))
        thread.op_failed.connect(lambda msg: self._op_error("mkdir", msg))
        self._start_thread(thread)

    def _remote_delete(self, session_id: str, entry: RemoteEntry):
        self._remote_delete_entries(session_id, [entry])

    def _remote_delete_entries(self, session_id: str, entries: list[RemoteEntry]):
        session = self.sessions.get(session_id)
        entries = self._prune_nested_remote_entries(entries)
        if not session or not entries:
            return
        label = entries[0].name if len(entries) == 1 else f"{len(entries)} items"
        has_dirs = any(entry.is_dir for entry in entries)
        detail = " (folders are removed recursively)" if has_dirs else ""
        answer = QMessageBox.question(
            self,
            "Delete Remote",
            f"Delete {label} from {session.site.name}?{detail}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        parent_path = get_remote_parent(entries[0].path) if len(entries) == 1 else session.panel.current_path
        parent_path = parent_path or session.panel.current_path
        thread = RemoteDeleteManyThread(session.site, entries)
        thread.op_done.connect(lambda sid=session_id, path=parent_path: self._refresh_remote_path_context(sid, path))
        thread.op_failed.connect(lambda msg: self._op_error("delete", msg))
        self._start_thread(thread)

    @staticmethod
    def _prune_nested_remote_entries(entries: list[RemoteEntry]) -> list[RemoteEntry]:
        unique: dict[str, RemoteEntry] = {}
        for entry in entries:
            normalized = normalize_remote_path(entry.path)
            unique.setdefault(normalized, entry)
        roots: list[RemoteEntry] = []
        root_paths: list[str] = []
        for path, entry in sorted(unique.items(), key=lambda item: (item[0].count("/"), item[0])):
            if any(
                root_path == "/" or path == root_path or path.startswith(f"{root_path}/")
                for root_path in root_paths
            ):
                continue
            roots.append(entry)
            root_paths.append(path.rstrip("/") or "/")
        return roots

    def _remote_rename(self, session_id: str, entry: RemoteEntry, new_name: str):
        session = self.sessions.get(session_id)
        if not session:
            return
        parent = get_remote_parent(entry.path) or session.panel.current_path
        new_path = join_remote_path(parent, new_name)
        thread = RemoteOpThread(session.site, "rename", entry.path, new_path)
        thread.op_done.connect(lambda sid=session_id, path=parent: self._refresh_remote_path_context(sid, path))
        thread.op_failed.connect(lambda msg: self._op_error("rename", msg))
        self._start_thread(thread)

    def _upload_files(self, session_id: str, target_item: QTreeWidgetItem = None):
        self._upload_paths(session_id, self.local_panel.get_selected_paths(), target_item)

    def _upload_local_paths_to_active_remote(self, paths: list[str]):
        session = self._current_session()
        if not session:
            QMessageBox.warning(self, "No Remote Session", "Open or select a remote session first.")
            return
        self._activate_and_run(session.session_id, self._upload_paths, paths)

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
        task = TaskScheduler.create_folder_upload_task(
            local_dir,
            remote_dir,
            0,
            0,
            dst_site=session.site,
            dst_session_id=session.session_id,
            dst_display_name=session.site.name,
        )
        task.preparing = True
        task.current_file = "Scanning local directory..."
        self.scheduler.add_task(task)
        thread = ScanLocalDirThread(local_dir)

        def on_scanned(_path: str, total_files: int, total_bytes: int, task_id=task.task_id):
            self.scheduler.finish_preparing_task(task_id, total_files, total_bytes)

        def on_failed(path: str, message: str, task_id=task.task_id):
            self.scheduler.fail_preparing_task(task_id, f"Local scan failed ({path}): {message}")
            self._log(f"Local scan failed ({path}): {message}")

        thread.scan_completed.connect(on_scanned)
        thread.scan_failed.connect(on_failed)
        self._start_thread(thread)

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
        local_dir = os.path.join(local_parent, os.path.basename(remote_dir.rstrip("/")))
        task = TaskScheduler.create_folder_download_task(
            remote_dir,
            local_dir,
            0,
            0,
            src_site=session.site,
            src_session_id=session.session_id,
            src_display_name=session.site.name,
        )
        task.preparing = True
        task.current_file = "Scanning remote directory..."
        self.scheduler.add_task(task)
        thread = ScanRemoteDirThread(session.site, remote_dir)

        def on_scanned(_path: str, total_files: int, total_bytes: int, task_id=task.task_id):
            self.scheduler.finish_preparing_task(task_id, total_files, total_bytes)

        def on_failed(path: str, msg: str, task_id=task.task_id):
            self.scheduler.fail_preparing_task(task_id, f"Download scan failed ({path}): {msg}")
            self._log(f"Download scan failed ({path}): {msg}")

        thread.scan_completed.connect(on_scanned)
        thread.scan_failed.connect(on_failed)
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
        task = TaskScheduler.create_folder_remote_to_remote_task(
            src_dir,
            dst_dir,
            0,
            0,
            src_site=src_session.site,
            dst_site=dst_session.site,
            src_session_id=src_session.session_id,
            dst_session_id=dst_session.session_id,
        )
        task.preparing = True
        task.current_file = "Scanning remote directory..."
        self.scheduler.add_task(task)
        thread = ScanRemoteDirThread(src_session.site, src_dir)

        def on_scanned(_path: str, total_files: int, total_bytes: int, task_id=task.task_id):
            self.scheduler.finish_preparing_task(task_id, total_files, total_bytes)

        def on_failed(path: str, msg: str, task_id=task.task_id):
            self.scheduler.fail_preparing_task(task_id, f"Remote transfer scan failed ({path}): {msg}")
            self._log(f"Remote transfer scan failed ({path}): {msg}")

        thread.scan_completed.connect(on_scanned)
        thread.scan_failed.connect(on_failed)
        self._start_thread(thread)

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
        if session_id == self._active_session_id:
            return
        previous_session_id = self._active_session_id
        self._active_session_id = session_id
        self._update_active_session_styles(previous_session_id, session_id)

    def _update_active_session_styles(
        self,
        previous_session_id: str | None = None,
        current_session_id: str | None = None,
    ):
        target_ids = {
            sid
            for sid in (previous_session_id, current_session_id, self._active_session_id)
            if sid is not None
        }
        if not target_ids:
            target_ids = set(self.sessions.keys())
        for session_id in target_ids:
            session = self.sessions.get(session_id)
            if not session:
                continue
            session.container.setProperty("active", session_id == self._active_session_id)
            session.container.style().unpolish(session.container)
            session.container.style().polish(session.container)

    def _refresh_remote_area(self):
        has_sessions = bool(self.sessions)
        self.remote_empty_state.setVisible(not has_sessions)
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
        if not self.isVisible():
            return
        tasks = self.scheduler.get_all_tasks()
        self.task_center.set_tasks(tasks)
        self._update_top_bar_status(tasks)

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

    def _on_local_file_selected(self, path: str):
        try:
            if os.name == "nt":
                os.startfile(path)
            else:
                opened = QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                if not opened:
                    raise OSError(f"Unable to open {path}")
        except Exception as exc:
            self._log(f"open local file failed: {exc}")
            QMessageBox.critical(self, "Open File Error", str(exc))

    def _op_error(self, op: str, msg: str):
        self._log(f"{op} failed: {msg}")
        QMessageBox.critical(self, f"{op} Error", msg)

    def _load_saved_sites(self):
        saved = self.site_store.load()
        self.sites = saved
        for site in saved:
            self.site_list.addItem(site.name)
        self._update_site_action_buttons()
        self._update_top_bar_status(self.scheduler.get_all_tasks())

    def _save_sites(self):
        self.site_store.save(self.sites)

    def _update_site_action_buttons(self):
        has_site = bool(self._selected_sites())
        self.btn_edit_site.setEnabled(has_site)
        self.btn_remove_site.setEnabled(has_site)
        self.btn_check_connection.setEnabled(has_site)
        self.btn_new_session.setEnabled(has_site)
        self.btn_remove_session.setEnabled(bool(self._selected_session_ids()))
        self._update_top_bar_status(self.scheduler.get_all_tasks())

    def _update_top_bar_status(self, tasks):
        active_tasks = sum(1 for task in tasks if task.status in ("pending", "running", "paused"))
        snapshot = (len(self.sites), len(self.sessions), active_tasks)
        if snapshot == self._topbar_snapshot:
            return
        self._topbar_snapshot = snapshot
        self.topbar_sites_label.setText(f"Sites: {snapshot[0]}")
        self.topbar_sessions_label.setText(f"Sessions: {snapshot[1]}")
        self.topbar_tasks_label.setText(f"Active Tasks: {snapshot[2]}")

    def _log(self, msg: str):
        self.log_text.append(msg)
        self.logger.info(msg)

    def closeEvent(self, event):
        active_tasks = [
            task for task in self.scheduler.get_all_tasks()
            if task.status in ("pending", "running", "paused")
        ]
        if active_tasks:
            answer = QMessageBox.question(
                self,
                "Transfers In Progress",
                f"{len(active_tasks)} transfer(s) are still active. Close anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        self._task_timer.stop()
        self.scheduler.stop()
        self._save_sites()
        # Stop background QThreads before Qt tears the window down; a running
        # QThread whose object is destroyed aborts the process.
        for thread in list(self._bg_threads):
            if isValid(thread) and thread.isRunning():
                thread.requestInterruption()
                thread.quit()
        for thread in list(self._bg_threads):
            if isValid(thread) and thread.isRunning():
                thread.wait(3000)
        event.accept()
