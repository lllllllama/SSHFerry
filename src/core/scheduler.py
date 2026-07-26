"""Task scheduler for managing local/remote and remote/remote tasks."""
from collections import defaultdict
from dataclasses import replace
import logging
import os
from pathlib import Path, PurePosixPath
import shlex
import tarfile
import tempfile
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, wait
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Callable, Dict, List, Optional

from src.core.task_state import assert_transition
from src.engines.parallel_sftp_engine import DEFAULT_PARALLEL_THRESHOLD_BYTES, ParallelSftpEngine
from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine
from src.engines.scp_engine import ScpEngine
from src.engines.sftp_engine import SftpEngine
from src.services.metrics import MetricsCollector, TransferRecord
from src.shared.errors import ErrorCode, SSHFerryError
from src.shared.logging_ import log_task_event
from src.shared.models import SiteConfig, Task
from src.shared.paths import normalize_remote_path, to_local_fs_path
from src.shared.remote_scan import scan_remote_tree_via_shell


def _env_int(name: str, default: int, min_value: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return max(min_value, int(raw))
    except ValueError:
        return default


def _env_preset(name: str, default: str) -> str:
    raw = os.getenv(name, "").strip().lower()
    return raw or default


class TaskScheduler:
    """Threaded scheduler for file operations and transfer tasks."""

    def __init__(
        self,
        site_config: Optional[SiteConfig] = None,
        max_workers: int = 3,
        max_workers_sftp: int = 3,
        max_workers_scp: int = 2,
        max_workers_parallel: int = 1,
        parallel_preset: str = "high",
        parallel_upload_preset: str = "medium",
        parallel_download_preset: str = "high",
        remote_relay_download_preset: str | None = None,
        remote_relay_upload_preset: str | None = None,
        parallel_threshold: int = DEFAULT_PARALLEL_THRESHOLD_BYTES,
        logger: Optional[logging.Logger] = None,
        activity_service=None,
        workspace_root: str | os.PathLike[str] | None = None,
    ):
        self.site_config = site_config
        self.max_workers = _env_int("SSHFERRY_MAX_WORKERS_TOTAL", max_workers, 1)
        self.max_workers_sftp = _env_int("SSHFERRY_MAX_WORKERS_SFTP", max_workers_sftp, 1)
        self.max_workers_scp = _env_int("SSHFERRY_MAX_WORKERS_SCP", max_workers_scp, 1)
        self.max_workers_parallel = _env_int("SSHFERRY_MAX_WORKERS_PARALLEL", max_workers_parallel, 1)
        self.parallel_preset = _env_preset("SSHFERRY_PARALLEL_PRESET", parallel_preset)
        self.parallel_upload_preset = _env_preset(
            "SSHFERRY_PARALLEL_UPLOAD_PRESET",
            parallel_upload_preset or self.parallel_preset,
        )
        self.parallel_download_preset = _env_preset(
            "SSHFERRY_PARALLEL_DOWNLOAD_PRESET",
            parallel_download_preset or self.parallel_preset,
        )
        self.remote_relay_download_preset = _env_preset(
            "SSHFERRY_REMOTE_RELAY_DOWNLOAD_PRESET",
            remote_relay_download_preset or self.parallel_download_preset,
        )
        self.remote_relay_upload_preset = _env_preset(
            "SSHFERRY_REMOTE_RELAY_UPLOAD_PRESET",
            remote_relay_upload_preset or self.parallel_upload_preset,
        )
        self.parallel_threshold = _env_int(
            "SSHFERRY_PARALLEL_THRESHOLD_BYTES",
            parallel_threshold,
            1,
        )
        self.remote_dualpath_threshold = _env_int(
            "SSHFERRY_REMOTE_DUALPATH_THRESHOLD_BYTES",
            max(self.parallel_threshold, 128 * 1024 * 1024),
            1,
        )
        self.remote_dualpath_chunk_size = _env_int(
            "SSHFERRY_REMOTE_DUALPATH_CHUNK_BYTES",
            32 * 1024 * 1024,
            1024 * 1024,
        )
        self.speed_window_seconds = max(
            0.5,
            float(os.getenv("SSHFERRY_SPEED_WINDOW_SECONDS", "4.0") or "4.0"),
        )
        self.progress_update_interval_seconds = max(
            0.0,
            float(os.getenv("SSHFERRY_PROGRESS_UPDATE_INTERVAL_SECONDS", "0.2") or "0.2"),
        )
        self.progress_update_min_bytes = _env_int(
            "SSHFERRY_PROGRESS_UPDATE_MIN_BYTES",
            2 * 1024 * 1024,
            0,
        )
        self.folder_file_workers = _env_int("SSHFERRY_FOLDER_FILE_WORKERS", 3, 1)
        self.folder_bundle_workers = _env_int("SSHFERRY_FOLDER_BUNDLE_WORKERS", 4, 1)
        self.folder_parallel_file_slots = _env_int("SSHFERRY_FOLDER_PARALLEL_FILE_SLOTS", 1, 1)
        self.folder_bundle_enabled = os.getenv("SSHFERRY_FOLDER_ARCHIVE_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")
        self.folder_bundle_file_count_threshold = _env_int("SSHFERRY_FOLDER_ARCHIVE_FILE_COUNT_THRESHOLD", 32, 1)
        self.folder_bundle_max_bytes = _env_int("SSHFERRY_FOLDER_ARCHIVE_MAX_BYTES", 256 * 1024 * 1024, 1024 * 1024)
        self.folder_bundle_max_files = _env_int("SSHFERRY_FOLDER_ARCHIVE_MAX_FILES", 256, 1)
        self.folder_bundle_parallel_threshold = _env_int(
            "SSHFERRY_FOLDER_ARCHIVE_PARALLEL_THRESHOLD_BYTES",
            max(self.parallel_threshold, 256 * 1024 * 1024),
            1024 * 1024,
        )
        self.folder_bundle_parallel_upload_preset = _env_preset(
            "SSHFERRY_FOLDER_ARCHIVE_PARALLEL_UPLOAD_PRESET",
            "medium",
        )
        self.folder_bundle_parallel_download_preset = _env_preset(
            "SSHFERRY_FOLDER_ARCHIVE_PARALLEL_DOWNLOAD_PRESET",
            "medium",
        )
        self.logger = logger or logging.getLogger(__name__)
        self.activity_service = activity_service
        self.workspace_root = Path(workspace_root).expanduser().resolve(strict=False) if workspace_root is not None else None

        self.tasks: Dict[str, Task] = {}
        self.task_lock = Lock()
        self.task_queue: List[str] = []
        self.queued_task_ids: set[str] = set()
        self.active_task_ids: set[str] = set()
        self.active_by_protocol: dict[str, int] = defaultdict(int)
        self.protocol_limits = {
            "sftp": self.max_workers_sftp,
            "scp": self.max_workers_scp,
            "parallel": self.max_workers_parallel,
            "dualpath": self.max_workers_parallel,
        }
        self._rr_protocols = ["sftp", "scp", "parallel", "dualpath"]
        self._rr_index = 0
        self._last_scheduler_stats_log = 0.0

        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.futures: Dict[str, Future] = {}
        self.running = False
        self.scheduler_thread: Optional[Thread] = None
        self.metrics = MetricsCollector()

    def start(self):
        if self.running:
            return
        self.running = True
        self.scheduler_thread = Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        self.logger.info("Task scheduler started")

    def stop(self):
        self.running = False
        with self.task_lock:
            for task_id in self.active_task_ids:
                task = self.tasks.get(task_id)
                if task and task.status in ("running", "paused", "pending"):
                    task.interrupted = True
                    task.paused = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.logger.info("Task scheduler stopped")

    def add_task(self, task: Task) -> str:
        task = self._normalize_task(task)
        with self.task_lock:
            self.tasks[task.task_id] = task
            if task.status == "pending" and not task.preparing and task.task_id not in self.queued_task_ids:
                self.task_queue.append(task.task_id)
                self.queued_task_ids.add(task.task_id)
        self.logger.info("Added task %s: %s %s -> %s", task.task_id, task.kind, task.src, task.dst)
        return task.task_id

    def finish_preparing_task(self, task_id: str, total_files: int, total_bytes: int) -> bool:
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task or task.is_finished:
                return False
            task.subtask_count = max(1, total_files)
            task.bytes_total = total_bytes
            task.preparing = False
            if task.current_file.startswith("Preparing"):
                task.current_file = ""
            if task.status == "pending" and task.task_id not in self.queued_task_ids:
                self.task_queue.append(task.task_id)
                self.queued_task_ids.add(task.task_id)
            return True

    def fail_preparing_task(self, task_id: str, message: str) -> bool:
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task or task.is_finished:
                return False
            task.preparing = False
            task.current_file = ""
            task.error_message = message
            task.error_code = ErrorCode.UNKNOWN_ERROR
            self._set_task_status_locked(task, "failed")
            if task_id in self.queued_task_ids:
                self.task_queue = [tid for tid in self.task_queue if tid != task_id]
                self.queued_task_ids.discard(task_id)
            return True

    def get_task(self, task_id: str) -> Optional[Task]:
        with self.task_lock:
            task = self.tasks.get(task_id)
            if task and task.status == "running":
                self._refresh_task_speed_locked(task)
            return task

    def get_all_tasks(self) -> List[Task]:
        with self.task_lock:
            for task in self.tasks.values():
                if task.status == "running":
                    self._refresh_task_speed_locked(task)
            return [replace(task) for task in self.tasks.values()]

    def pending_task_count(self) -> int:
        with self.task_lock:
            return len(self.task_queue)

    def cancel_task(self, task_id: str) -> bool:
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            if task.status == "pending":
                self._set_task_status_locked(task, "canceled")
                task.paused = False
                return True
            if task.status == "running":
                task.interrupted = True
                task.paused = False
                return True
            if task.status == "paused":
                self._set_task_status_locked(task, "canceled")
                # Straggler engine threads may still be mid-flight; make sure
                # they observe the cancel instead of re-pausing.
                task.interrupted = True
                task.paused = False
                return True
        return False

    def pause_task(self, task_id: str) -> bool:
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task or task.status != "running":
                return False
            task.paused = True
            return True

    def resume_task(self, task_id: str) -> bool:
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task or task.status != "paused":
                return False
            self._set_task_status_locked(task, "pending")
            task.paused = False
            task.interrupted = False
            task.speed = 0.0
            task.avg_speed = 0.0
            task.speed_samples.clear()
            if task.kind == "folder_transfer":
                task.bytes_done = 0
                task.subtask_done = 0
                task.current_file = ""
            if task_id not in self.queued_task_ids:
                self.task_queue.append(task_id)
                self.queued_task_ids.add(task_id)
            return True

    def restart_task(self, task_id: str) -> bool:
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task or task.status not in ("failed", "canceled", "done", "skipped"):
                return False
            self._set_task_status_locked(task, "pending")
            task.bytes_done = 0
            task.speed = 0.0
            task.avg_speed = 0.0
            task.speed_samples.clear()
            task.error_code = None
            task.error_message = None
            task.start_time = None
            task.end_time = None
            task.interrupted = False
            task.paused = False
            task.skipped = False
            task.subtask_done = 0
            task.current_file = ""
            if task_id not in self.queued_task_ids:
                self.task_queue.append(task_id)
                self.queued_task_ids.add(task_id)
            return True

    def _scheduler_loop(self):
        while self.running:
            try:
                with self.task_lock:
                    selected = self._select_next_runnable_task_locked()
                if not selected:
                    self._maybe_log_scheduler_stats()
                    time.sleep(0.1)
                    continue
                task_id, task, protocol = selected
                future = self.executor.submit(self._execute_task, task)
                with self.task_lock:
                    self.futures[task_id] = future
                    self.active_task_ids.add(task_id)
                    self.active_by_protocol[protocol] += 1
                future.add_done_callback(
                    lambda _fut, tid=task_id, proto=protocol: self._on_future_done(tid, proto)
                )
                self._maybe_log_scheduler_stats()
            except Exception as exc:
                self.logger.error("Scheduler loop error: %s", exc)
                time.sleep(1)

    def _on_future_done(self, task_id: str, protocol: str):
        with self.task_lock:
            self.active_task_ids.discard(task_id)
            self.active_by_protocol[protocol] = max(0, self.active_by_protocol[protocol] - 1)

    def _select_next_runnable_task_locked(self) -> Optional[tuple[str, Task, str]]:
        if not self.task_queue or len(self.active_task_ids) >= self.max_workers:
            return None
        protocol_order = [
            self._rr_protocols[(self._rr_index + i) % len(self._rr_protocols)]
            for i in range(len(self._rr_protocols))
        ]
        for protocol in protocol_order:
            if self.active_by_protocol.get(protocol, 0) >= self.protocol_limits.get(protocol, self.max_workers):
                continue
            for idx, task_id in enumerate(self.task_queue):
                task = self.tasks.get(task_id)
                if not task or task.status != "pending":
                    continue
                if task.preparing:
                    continue
                if self._task_protocol(task) != protocol:
                    continue
                self.task_queue.pop(idx)
                self.queued_task_ids.discard(task_id)
                self._rr_index = (self._rr_protocols.index(protocol) + 1) % len(self._rr_protocols)
                return task_id, task, protocol
        self.task_queue = [tid for tid in self.task_queue if self.tasks.get(tid) and self.tasks[tid].status == "pending"]
        self.queued_task_ids = set(self.task_queue)
        return None

    def _task_protocol(self, task: Task) -> str:
        return task.engine if task.engine in ("sftp", "scp", "parallel", "dualpath") else "sftp"

    def _maybe_log_scheduler_stats(self) -> None:
        now = time.time()
        if now - self._last_scheduler_stats_log < 2.0:
            return
        self._last_scheduler_stats_log = now
        with self.task_lock:
            queued = len(self.task_queue)
            active_total = len(self.active_task_ids)
            active_sftp = self.active_by_protocol.get("sftp", 0)
            active_scp = self.active_by_protocol.get("scp", 0)
            active_parallel = self.active_by_protocol.get("parallel", 0)
        self.logger.debug(
            "scheduler_stats queue=%s active_total=%s active_sftp=%s active_scp=%s active_parallel=%s",
            queued,
            active_total,
            active_sftp,
            active_scp,
            active_parallel,
        )

    def _set_task_status_locked(self, task: Task, target: str) -> None:
        if task.status == target:
            return
        try:
            assert_transition(task.status, target)
        except ValueError:
            self.logger.warning(
                "Illegal task state transition observed: %s -> %s (task=%s)",
                task.status,
                target,
                task.task_id[:8],
            )
        task.status = target

    def _normalize_task(self, task: Task) -> Task:
        if task.kind in ("upload", "folder_upload") and task.src_site_snapshot is None and self.site_config:
            task.dst_site_snapshot = task.dst_site_snapshot or self.site_config
            task.dst_display_name = task.dst_display_name or self.site_config.name
            task.dst_session_id = task.dst_session_id or self.site_config.name
        if task.kind in ("download", "folder_download") and task.src_site_snapshot is None and self.site_config:
            task.src_site_snapshot = task.src_site_snapshot or self.site_config
            task.src_display_name = task.src_display_name or self.site_config.name
            task.src_session_id = task.src_session_id or self.site_config.name

        if task.kind == "upload":
            task.kind = "file_transfer"
            task.src_endpoint_type = "local"
            task.dst_endpoint_type = "remote"
        elif task.kind == "download":
            task.kind = "file_transfer"
            task.src_endpoint_type = "remote"
            task.dst_endpoint_type = "local"
        elif task.kind == "folder_upload":
            task.kind = "folder_transfer"
            task.src_endpoint_type = "local"
            task.dst_endpoint_type = "remote"
        elif task.kind == "folder_download":
            task.kind = "folder_transfer"
            task.src_endpoint_type = "remote"
            task.dst_endpoint_type = "local"

        if task.src_endpoint_type == "remote" and not task.src_site_snapshot and self.site_config:
            task.src_site_snapshot = self.site_config
            task.src_display_name = task.src_display_name or self.site_config.name
            task.src_session_id = task.src_session_id or self.site_config.name
        if task.dst_endpoint_type == "remote" and not task.dst_site_snapshot and self.site_config:
            task.dst_site_snapshot = self.site_config
            task.dst_display_name = task.dst_display_name or self.site_config.name
            task.dst_session_id = task.dst_session_id or self.site_config.name
        return task

    def _execute_task(self, task: Task):
        with self.task_lock:
            if task.status != "pending":
                # Canceled (or otherwise finalized) between dequeue and
                # dispatch; do not resurrect it to running.
                return
            self._set_task_status_locked(task, "running")
            task.start_time = time.time()
            task.speed = 0.0
            task.avg_speed = 0.0
            task.speed_samples.clear()
            task.speed_samples.append((task.start_time, task.bytes_done))

        remote_site = task.dst_site_snapshot or task.src_site_snapshot or self.site_config
        log_task_event(
            self.logger,
            task.task_id,
            task.engine,
            task.kind,
            "running",
            remote_site.host if remote_site else None,
            remote_site.port if remote_site else None,
            remote_site.username if remote_site else None,
            task.src_endpoint.label,
            task.dst_endpoint.label,
        )
        try:
            if task.kind == "file_transfer":
                self._execute_file_transfer(task)
            elif task.kind == "folder_transfer":
                self._execute_folder_transfer(task)
            elif task.kind == "delete":
                self._execute_delete(task)
            elif task.kind == "mkdir":
                self._execute_mkdir(task)
            elif task.kind == "rename":
                self._execute_rename(task)
            else:
                raise ValueError(f"Unknown task kind: {task.kind}")

            with self.task_lock:
                if task.status == "running":
                    self._set_task_status_locked(task, "done")
                    task.end_time = time.time()
                    task.bytes_done = task.bytes_total
                    task.avg_speed = self._finalize_task_speed_locked(task)
                    task.speed = task.avg_speed

            if task.kind in ("file_transfer", "folder_transfer") and task.status == "done":
                duration = time.time() - (task.start_time or time.time())
                self.metrics.record(
                    TransferRecord(
                        preset=self._metric_preset_for_task(task),
                        bytes_transferred=task.bytes_done,
                        duration_seconds=max(0.1, duration),
                        success=True,
                        timestamp=time.time(),
                    )
                )
            log_task_event(
                self.logger,
                task.task_id,
                task.engine,
                task.kind,
                task.status,
                src=task.src_endpoint.label,
                dst=task.dst_endpoint.label,
                bytes_done=task.bytes_done,
                bytes_total=task.bytes_total,
            )
            self._publish_task_activity(task)
        except SSHFerryError as exc:
            with self.task_lock:
                self._set_task_status_locked(task, "failed")
                task.end_time = time.time()
                task.error_code = exc.code
                task.error_message = exc.message
                task.avg_speed = self._finalize_task_speed_locked(task)
                task.speed = task.avg_speed
            self._record_failed_metrics(task)
            log_task_event(
                self.logger,
                task.task_id,
                task.engine,
                task.kind,
                "failed",
                src=task.src_endpoint.label,
                dst=task.dst_endpoint.label,
                error_code=exc.code,
                message=exc.message,
            )
            self._publish_task_activity(task)
        except Exception as exc:
            with self.task_lock:
                self._set_task_status_locked(task, "failed")
                task.end_time = time.time()
                task.error_code = ErrorCode.UNKNOWN_ERROR
                task.error_message = str(exc)
                task.avg_speed = self._finalize_task_speed_locked(task)
                task.speed = task.avg_speed
            self._record_failed_metrics(task)
            log_task_event(
                self.logger,
                task.task_id,
                task.engine,
                task.kind,
                "failed",
                src=task.src_endpoint.label,
                dst=task.dst_endpoint.label,
                error_code=ErrorCode.UNKNOWN_ERROR,
                message=str(exc),
            )
            self._publish_task_activity(task)

    def _publish_task_activity(self, task: Task) -> None:
        if self.activity_service is None:
            return

        title_map = {
            "done": "Transfer completed",
            "failed": "Transfer failed",
            "canceled": "Transfer canceled",
            "paused": "Transfer paused",
            "skipped": "Transfer skipped",
        }
        level_map = {
            "done": "success",
            "failed": "error",
            "canceled": "warning",
            "paused": "warning",
            "skipped": "info",
        }
        if task.status not in title_map:
            return

        src_label = self._present_activity_label(task.src_endpoint_type, task.src, task.src_endpoint.label)
        dst_label = self._present_activity_label(task.dst_endpoint_type, task.dst, task.dst_endpoint.label)
        if task.kind in ("file_transfer", "folder_transfer", "rename") and task.src and task.dst:
            message = f"{src_label} -> {dst_label}"
        else:
            message = dst_label if task.dst else src_label
        if task.status == "failed" and task.error_message:
            message = f"{message}: {task.error_message}"

        self.activity_service.publish(
            user_id=task.owner_user_id,
            level=level_map[task.status],
            category='task',
            action=task.status,
            title=title_map[task.status],
            message=message,
        )

    def _present_activity_label(self, endpoint_type: str, path: str, fallback_label: str) -> str:
        if endpoint_type != "local" or self.workspace_root is None:
            return fallback_label

        try:
            actual_path = Path(path).expanduser().resolve(strict=False)
            relative = actual_path.relative_to(self.workspace_root)
        except Exception:
            return fallback_label

        parts = relative.parts
        workspace_parts = parts[1:] if len(parts) > 1 else ()
        virtual_path = "/" if not workspace_parts else "/" + PurePosixPath(*workspace_parts).as_posix().lstrip("/")
        return f"workspace:{virtual_path}"

    def _record_failed_metrics(self, task: Task) -> None:
        if task.kind not in ("file_transfer", "folder_transfer"):
            return
        duration = time.time() - (task.start_time or time.time())
        self.metrics.record(
            TransferRecord(
                preset=self._metric_preset_for_task(task),
                bytes_transferred=task.bytes_done,
                duration_seconds=max(0.1, duration),
                success=False,
                timestamp=time.time(),
            )
        )

    def _progress_callback(self, task: Task):
        return self._make_task_progress_updater(task)

    def _make_task_progress_updater(self, task: Task):
        state_lock = Lock()
        state = {
            "last_emit_time": 0.0,
            "last_emit_bytes": int(task.bytes_done),
        }

        def callback(
            bytes_transferred: int,
            bytes_total: int,
            *,
            current_file: str | None = None,
            force: bool = False,
        ) -> None:
            should_emit = force
            now = time.time()
            if not should_emit:
                with state_lock:
                    enough_time = (
                        self.progress_update_interval_seconds <= 0
                        or now - state["last_emit_time"] >= self.progress_update_interval_seconds
                    )
                    enough_bytes = (
                        self.progress_update_min_bytes <= 0
                        or bytes_transferred - state["last_emit_bytes"] >= self.progress_update_min_bytes
                    )
                    completed = bytes_total > 0 and bytes_transferred >= bytes_total
                    should_emit = completed or enough_time or enough_bytes
                    if not should_emit:
                        return
                    state["last_emit_time"] = now
                    state["last_emit_bytes"] = bytes_transferred
            else:
                with state_lock:
                    state["last_emit_time"] = now
                    state["last_emit_bytes"] = bytes_transferred

            with self.task_lock:
                self._record_task_progress_locked(task, bytes_transferred, bytes_total, now=now)
                if current_file is not None:
                    task.current_file = current_file

        return callback

    def _interrupt_checker(self, task: Task):
        def check_interrupt():
            if task.interrupted:
                return True
            if task.paused:
                with self.task_lock:
                    # Only a running task may move to paused here; a straggler
                    # thread must not flip a canceled/finished task back.
                    if task.status == "running":
                        self._set_task_status_locked(task, "paused")
                raise InterruptedError("Task paused")
            return task.interrupted

        return check_interrupt

    def _handle_interrupted(self, task: Task) -> None:
        with self.task_lock:
            # An explicit cancel wins over a pause observed at the same time.
            interruption_reason = "canceled" if task.interrupted else ("paused" if task.paused else "canceled")
            if interruption_reason == "paused":
                self._set_task_status_locked(task, "paused")
            else:
                task.paused = False
                self._set_task_status_locked(task, "canceled")
            task.end_time = time.time()
            task.avg_speed = self._finalize_task_speed_locked(task)
            task.speed = task.avg_speed
        self.logger.info(
            "task_interrupted task=%s kind=%s status=%s reason=%s bytes_done=%s bytes_total=%s",
            task.task_id[:8],
            task.kind,
            task.status,
            interruption_reason,
            task.bytes_done,
            task.bytes_total,
        )

    def _record_task_progress_locked(
        self,
        task: Task,
        bytes_transferred: int,
        bytes_total: int,
        *,
        now: float | None = None,
    ) -> None:
        if task.paused or task.status in ("paused", "canceled"):
            return
        now = time.time() if now is None else now
        task.bytes_done = bytes_transferred
        task.bytes_total = bytes_total
        if task.speed_samples and task.speed_samples[-1][1] == bytes_transferred:
            task.speed_samples[-1] = (now, bytes_transferred)
        else:
            task.speed_samples.append((now, bytes_transferred))
        self._refresh_task_speed_locked(task, now)

    def _refresh_task_speed_locked(self, task: Task, now: float | None = None) -> None:
        now = time.time() if now is None else now
        cutoff = now - self.speed_window_seconds
        while len(task.speed_samples) > 1 and task.speed_samples[0][0] < cutoff:
            task.speed_samples.popleft()
        if not task.speed_samples:
            task.speed = 0.0
            return
        last_time, last_bytes = task.speed_samples[-1]
        if now - last_time >= self.speed_window_seconds:
            task.speed = 0.0
            return
        first_time, first_bytes = task.speed_samples[0]
        elapsed = max(0.001, last_time - first_time)
        delta = max(0, last_bytes - first_bytes)
        task.speed = delta / elapsed if delta > 0 else 0.0

    def _finalize_task_speed_locked(self, task: Task) -> float:
        if not task.start_time or not task.end_time:
            return 0.0
        elapsed = max(0.001, task.end_time - task.start_time)
        return task.bytes_done / elapsed if task.bytes_done > 0 else 0.0

    def _execute_file_transfer(self, task: Task):
        try:
            if task.is_local_to_remote:
                if task.engine == "parallel":
                    self._execute_parallel_upload(task)
                elif task.engine == "scp":
                    self._execute_scp_upload(task)
                else:
                    self._execute_upload(task)
            elif task.is_remote_to_local:
                if task.engine == "parallel":
                    self._execute_parallel_download(task)
                elif task.engine == "scp":
                    self._execute_scp_download(task)
                else:
                    self._execute_download(task)
            elif task.is_remote_to_remote:
                self._execute_remote_to_remote_file(task)
            else:
                raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, "Unsupported transfer direction")
        except InterruptedError:
            self._handle_interrupted(task)

    def _execute_folder_transfer(self, task: Task):
        try:
            if task.is_local_to_remote:
                self._execute_folder_upload(task)
            elif task.is_remote_to_local:
                self._execute_folder_download(task)
            elif task.is_remote_to_remote:
                self._execute_remote_to_remote_folder(task)
            else:
                raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, "Unsupported folder transfer direction")
        except InterruptedError:
            self._handle_interrupted(task)

    def _execute_upload(self, task: Task):
        try:
            site = self._require_site(task.dst_site_snapshot or self.site_config, "upload destination")
            engine = SftpEngine(site, self.logger)
            engine.connect()
            try:
                local_size = os.path.getsize(task.src)
                offset = 0
                try:
                    remote_stat = engine.stat(task.dst)
                    if remote_stat.size == local_size:
                        with self.task_lock:
                            task.skipped = True
                            self._set_task_status_locked(task, "skipped")
                            task.bytes_done = local_size
                        return
                    if remote_stat.size < local_size:
                        offset = remote_stat.size
                except SSHFerryError as exc:
                    if exc.code != ErrorCode.PATH_NOT_FOUND:
                        raise
                engine.upload_file(
                    task.src,
                    task.dst,
                    callback=self._progress_callback(task),
                    check_interrupt=self._interrupt_checker(task),
                    offset=offset,
                )
            finally:
                engine.disconnect()
        except InterruptedError:
            self._handle_interrupted(task)

    def _execute_download(self, task: Task):
        try:
            site = self._require_site(task.src_site_snapshot or self.site_config, "download source")
            engine = SftpEngine(site, self.logger)
            engine.connect()
            try:
                try:
                    remote_stat = engine.stat(task.src)
                    remote_size = remote_stat.size
                except SSHFerryError:
                    remote_size = task.bytes_total
                offset = 0
                fs_dst = to_local_fs_path(task.dst)
                if os.path.exists(fs_dst):
                    local_size = os.path.getsize(fs_dst)
                    if local_size == remote_size:
                        with self.task_lock:
                            task.skipped = True
                            self._set_task_status_locked(task, "skipped")
                            task.bytes_done = remote_size
                        return
                    if local_size < remote_size:
                        offset = local_size
                engine.download_file(
                    task.src,
                    task.dst,
                    callback=self._progress_callback(task),
                    check_interrupt=self._interrupt_checker(task),
                    offset=offset,
                )
            finally:
                engine.disconnect()
        except InterruptedError:
            self._handle_interrupted(task)

    def _execute_parallel_upload(self, task: Task):
        try:
            site = self._require_site(task.dst_site_snapshot or self.site_config, "parallel upload destination")
            p_engine = ParallelSftpEngine(site, self.logger, preset_name=self.parallel_upload_preset)
            p_engine.upload_file(
                task.src,
                task.dst,
                callback=self._progress_callback(task),
                check_interrupt=self._interrupt_checker(task),
            )
        except InterruptedError:
            self._handle_interrupted(task)

    def _execute_parallel_download(self, task: Task):
        try:
            site = self._require_site(task.src_site_snapshot or self.site_config, "parallel download source")
            p_engine = ParallelSftpEngine(site, self.logger, preset_name=self.parallel_download_preset)
            p_engine.download_file(
                task.src,
                task.dst,
                callback=self._progress_callback(task),
                check_interrupt=self._interrupt_checker(task),
            )
        except InterruptedError:
            self._handle_interrupted(task)

    def _execute_scp_upload(self, task: Task):
        try:
            site = self._require_site(task.dst_site_snapshot or self.site_config, "scp upload destination")
            engine = ScpEngine(site, self.logger)
            try:
                engine.connect()
                engine.upload_file(
                    task.src,
                    task.dst,
                    callback=self._progress_callback(task),
                    check_interrupt=self._interrupt_checker(task),
                )
            finally:
                engine.disconnect()
        except SSHFerryError as exc:
            if task.paused or task.interrupted:
                raise
            self.logger.warning("fallback=scp_to_sftp task=%s reason=%s", task.task_id[:8], exc.message)
            try:
                self._execute_upload(task)
            except Exception as fallback_error:
                raise SSHFerryError(
                    ErrorCode.TRANSFER_FAILED,
                    f"SCP failed: {exc.message}; fallback SFTP failed: {fallback_error}",
                )
        except InterruptedError:
            self._handle_interrupted(task)

    def _execute_scp_download(self, task: Task):
        try:
            site = self._require_site(task.src_site_snapshot or self.site_config, "scp download source")
            engine = ScpEngine(site, self.logger)
            try:
                engine.connect()
                engine.download_file(
                    task.src,
                    task.dst,
                    callback=self._progress_callback(task),
                    check_interrupt=self._interrupt_checker(task),
                )
            finally:
                engine.disconnect()
        except SSHFerryError as exc:
            if task.paused or task.interrupted:
                raise
            self.logger.warning("fallback=scp_to_sftp task=%s reason=%s", task.task_id[:8], exc.message)
            try:
                self._execute_download(task)
            except Exception as fallback_error:
                raise SSHFerryError(
                    ErrorCode.TRANSFER_FAILED,
                    f"SCP failed: {exc.message}; fallback SFTP failed: {fallback_error}",
                )
        except InterruptedError:
            self._handle_interrupted(task)

    def _execute_remote_to_remote_file(self, task: Task):
        src_site = self._require_site(task.src_site_snapshot, "remote source")
        dst_site = self._require_site(task.dst_site_snapshot, "remote destination")
        resume_offset, skip_existing = self._remote_to_remote_resume_state(task, dst_site)
        if resume_offset > 0 and not skip_existing:
            self.logger.info(
                "task_remote_transfer_resume_detected task=%s src=%s dst=%s resume_offset=%s bytes_total=%s",
                task.task_id[:8],
                task.src,
                task.dst,
                resume_offset,
                task.bytes_total,
            )
        if skip_existing:
            with self.task_lock:
                task.skipped = True
                task.bytes_done = task.bytes_total
                task.end_time = time.time()
                task.speed = 0.0
                task.avg_speed = 0.0
                task.speed_samples.clear()
                self._set_task_status_locked(task, "skipped")
            self.logger.info(
                "task_remote_transfer_mode task=%s mode=skipped_existing src=%s dst=%s resume_offset=%s",
                task.task_id[:8],
                task.src,
                task.dst,
                resume_offset,
            )
            return
        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            self.logger,
            parallel_threshold=self.parallel_threshold,
            dualpath_threshold=self.remote_dualpath_threshold,
            dualpath_chunk_size=self.remote_dualpath_chunk_size,
            relay_download_preset=self.remote_relay_download_preset,
            relay_upload_preset=self.remote_relay_upload_preset,
        )
        mode = engine.transfer_file(
            task.src,
            task.dst,
            callback=self._progress_callback(task),
            check_interrupt=self._interrupt_checker(task),
            resume_offset=resume_offset,
            requested_engine=task.engine,
        )
        self.logger.info(
            "task_remote_transfer_mode task=%s mode=%s src=%s dst=%s resume_offset=%s",
            task.task_id[:8],
            mode,
            task.src,
            task.dst,
            resume_offset,
        )

    def _execute_remote_to_remote_folder(self, task: Task):
        src_site = self._require_site(task.src_site_snapshot, "remote source")
        dst_site = self._require_site(task.dst_site_snapshot, "remote destination")
        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            self.logger,
            parallel_threshold=self.parallel_threshold,
            dualpath_threshold=self.remote_dualpath_threshold,
            dualpath_chunk_size=self.remote_dualpath_chunk_size,
            relay_download_preset=self.remote_relay_download_preset,
            relay_upload_preset=self.remote_relay_upload_preset,
        )

        def folder_item_progress(event: str, label: str, count: int) -> None:
            with self.task_lock:
                if event == "start":
                    task.current_file = label
                    return
                if event == "complete":
                    if count > 0:
                        task.subtask_done = min(task.subtask_count, task.subtask_done + count)
                    task.current_file = label

        engine.transfer_dir(
            task.src,
            task.dst,
            callback=self._progress_callback(task),
            check_interrupt=self._interrupt_checker(task),
            item_callback=folder_item_progress,
        )
        with self.task_lock:
            if not task.subtask_count:
                task.subtask_count = 1
            task.subtask_done = task.subtask_count
            task.current_file = ""

    def _execute_delete(self, task: Task):
        site = self._require_site(task.src_site_snapshot or self.site_config, "delete target")
        engine = SftpEngine(site, self.logger)
        engine.connect()
        try:
            try:
                engine.remove_file(task.src)
            except SSHFerryError:
                engine.remove_dir(task.src)
        finally:
            engine.disconnect()

    def _execute_mkdir(self, task: Task):
        site = self._require_site(task.dst_site_snapshot or self.site_config, "mkdir target")
        engine = SftpEngine(site, self.logger)
        engine.connect()
        try:
            engine.mkdir(task.dst)
        finally:
            engine.disconnect()

    def _execute_rename(self, task: Task):
        site = self._require_site(task.src_site_snapshot or self.site_config, "rename target")
        engine = SftpEngine(site, self.logger)
        engine.connect()
        try:
            engine.rename(task.src, task.dst)
        finally:
            engine.disconnect()

    def _execute_folder_upload(self, task: Task):
        site = self._require_site(task.dst_site_snapshot or self.site_config, "folder upload destination")
        engine = SftpEngine(site, self.logger)
        engine.connect()
        try:
            self._upload_dir_recursive(engine, task, task.src, task.dst)
        finally:
            engine.disconnect()

    def _execute_folder_download(self, task: Task):
        site = self._require_site(task.src_site_snapshot or self.site_config, "folder download source")
        engine = SftpEngine(site, self.logger)
        engine.connect()
        try:
            self._download_dir_recursive(engine, task, task.src, task.dst)
        finally:
            engine.disconnect()

    def _upload_dir_recursive(self, engine: SftpEngine, task: Task, local_dir: str, remote_dir: str):
        if hasattr(engine, "site_config") or hasattr(engine, "connect"):
            self._execute_folder_upload_parallelized(engine, task, local_dir, remote_dir)
            return
        self._upload_dir_recursive_legacy(engine, task, local_dir, remote_dir)

    def _download_dir_recursive(self, engine: SftpEngine, task: Task, remote_dir: str, local_dir: str):
        if hasattr(engine, "site_config") or hasattr(engine, "connect"):
            self._execute_folder_download_parallelized(engine, task, remote_dir, local_dir)
            return
        self._download_dir_recursive_legacy(engine, task, remote_dir, local_dir)

    def _upload_dir_recursive_legacy(self, engine: SftpEngine, task: Task, local_dir: str, remote_dir: str):
        try:
            engine.mkdir(remote_dir)
        except SSHFerryError:
            existing = engine.stat(remote_dir)
            if not existing.is_dir:
                raise
        check_interrupt = self._interrupt_checker(task)
        for name in os.listdir(local_dir):
            if check_interrupt():
                raise InterruptedError("Task interrupted")
            full_path = os.path.join(local_dir, name)
            remote_path = f"{remote_dir.rstrip('/')}/{name}"
            if os.path.isfile(full_path):
                file_size = os.path.getsize(full_path)
                offset = 0
                skip_file = False
                try:
                    stats = engine.stat(remote_path)
                    if stats.size == file_size:
                        skip_file = True
                    elif stats.size < file_size:
                        offset = stats.size
                except SSHFerryError as exc:
                    if exc.code != ErrorCode.PATH_NOT_FOUND:
                        raise
                if skip_file:
                    with self.task_lock:
                        task.subtask_done += 1
                        task.bytes_done = min(task.bytes_total, task.bytes_done + file_size)
                    continue
                with self.task_lock:
                    task.current_file = name
                    base_bytes = task.bytes_done

                def progress_callback(bytes_transferred, _bytes_total):
                    with self.task_lock:
                        self._record_task_progress_locked(
                            task,
                            min(task.bytes_total, base_bytes + bytes_transferred),
                            task.bytes_total,
                        )

                engine.upload_file(full_path, remote_path, callback=progress_callback, check_interrupt=check_interrupt, offset=offset)
                with self.task_lock:
                    task.subtask_done += 1
                    task.bytes_done = min(task.bytes_total, base_bytes + file_size)
            elif os.path.isdir(full_path):
                self._upload_dir_recursive_legacy(engine, task, full_path, remote_path)

    def _download_dir_recursive_legacy(self, engine: SftpEngine, task: Task, remote_dir: str, local_dir: str):
        os.makedirs(to_local_fs_path(local_dir), exist_ok=True)
        entries = engine.list_dir(remote_dir)
        check_interrupt = self._interrupt_checker(task)
        for entry in entries:
            if check_interrupt():
                raise InterruptedError("Task interrupted")
            local_path = os.path.join(local_dir, entry.name)
            if entry.is_dir:
                self._download_dir_recursive_legacy(engine, task, entry.path, local_path)
                continue
            offset = 0
            skip_file = False
            fs_local_path = to_local_fs_path(local_path)
            if os.path.exists(fs_local_path):
                local_size = os.path.getsize(fs_local_path)
                if local_size == entry.size:
                    skip_file = True
                elif local_size < entry.size:
                    offset = local_size
            if skip_file:
                with self.task_lock:
                    task.subtask_done += 1
                    task.bytes_done += entry.size
                continue
            with self.task_lock:
                task.current_file = entry.name
                base_bytes = task.bytes_done

            def progress_callback(bytes_transferred, _bytes_total):
                with self.task_lock:
                    self._record_task_progress_locked(
                        task,
                        min(task.bytes_total, base_bytes + bytes_transferred),
                        task.bytes_total,
                    )

            engine.download_file(entry.path, local_path, callback=progress_callback, check_interrupt=check_interrupt, offset=offset)
            with self.task_lock:
                task.subtask_done += 1
                task.bytes_done = min(task.bytes_total, base_bytes + entry.size)

    def _execute_folder_upload_parallelized(self, engine: SftpEngine, task: Task, local_dir: str, remote_dir: str) -> None:
        file_items = self._scan_local_folder_tree(local_dir, remote_dir)
        self._ensure_remote_directories(engine, [remote_dir, *[item[1] for item in file_items if item[2]]])
        files = [item for item in file_items if not item[2]]
        file_plans = self._build_local_folder_file_plans(files, local_dir, direction="upload")
        mixed_plan = self._build_local_folder_mixed_plan(file_plans)
        if self._should_use_local_folder_mixed_transfer(mixed_plan):
            self._run_local_folder_transfer_mixed(
                task,
                mixed_plan,
                direction="upload",
                local_root=local_dir,
                remote_root=remote_dir,
                probe_engine=engine,
            )
            return
        self._run_local_folder_transfer_workers(task, files, direction="upload", probe_engine=engine)

    def _execute_folder_download_parallelized(self, engine: SftpEngine, task: Task, remote_dir: str, local_dir: str) -> None:
        file_items = self._scan_remote_folder_tree(engine, remote_dir, local_dir)
        self._ensure_local_directories([local_dir, *[item[1] for item in file_items if item[2]]])
        files = [item for item in file_items if not item[2]]
        file_plans = self._build_local_folder_file_plans(files, local_dir, direction="download")
        mixed_plan = self._build_local_folder_mixed_plan(file_plans)
        if self._should_use_local_folder_mixed_transfer(mixed_plan):
            self._run_local_folder_transfer_mixed(
                task,
                mixed_plan,
                direction="download",
                local_root=local_dir,
                remote_root=remote_dir,
                probe_engine=engine,
            )
            return
        self._run_local_folder_transfer_workers(task, files, direction="download")

    def _scan_local_folder_tree(self, local_dir: str, remote_dir: str) -> list[tuple[str, str, bool, int]]:
        items: list[tuple[str, str, bool, int]] = []
        for root, dir_names, file_names in os.walk(local_dir):
            # os.walk order is filesystem-dependent; sort for deterministic
            # traversal, bundling, and progress ordering across platforms.
            dir_names.sort()
            file_names.sort()
            rel_root = os.path.relpath(root, local_dir)
            current_remote = remote_dir if rel_root == "." else f"{remote_dir.rstrip('/')}/{rel_root.replace(os.sep, '/')}"
            for dir_name in dir_names:
                items.append((os.path.join(root, dir_name), f"{current_remote.rstrip('/')}/{dir_name}", True, 0))
            for file_name in file_names:
                full_path = os.path.join(root, file_name)
                items.append((full_path, f"{current_remote.rstrip('/')}/{file_name}", False, os.path.getsize(full_path)))
        return items

    def _scan_remote_folder_tree(self, engine: SftpEngine, remote_dir: str, local_dir: str) -> list[tuple[str, str, bool, int]]:
        shell_entries = scan_remote_tree_via_shell(engine, remote_dir)
        if shell_entries is not None:
            items: list[tuple[str, str, bool, int]] = []
            normalized_remote = PurePosixPath(remote_dir)
            for entry in shell_entries:
                target_local = os.path.join(local_dir, *entry.rel_path.split("/"))
                source_remote = str(normalized_remote / entry.rel_path)
                items.append((source_remote, target_local, entry.is_dir, entry.size))
            return items

        items: list[tuple[str, str, bool, int]] = []
        visited: set[str] = set()

        def walk(current_remote: str, current_local: str) -> None:
            canonical_remote = self._canonical_remote_walk_path(engine, current_remote)
            if canonical_remote in visited:
                return
            visited.add(canonical_remote)
            for entry in engine.list_dir(current_remote):
                target_local = os.path.join(current_local, entry.name)
                if entry.is_dir:
                    items.append((entry.path, target_local, True, 0))
                    walk(entry.path, target_local)
                else:
                    items.append((entry.path, target_local, False, entry.size))

        walk(remote_dir, local_dir)
        return items

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

    def _ensure_remote_directories(self, engine: SftpEngine, directories: list[str]) -> None:
        for directory in sorted(set(directories), key=lambda value: (value.count("/"), value)):
            try:
                engine.mkdir(directory)
            except SSHFerryError:
                try:
                    existing = engine.stat(directory)
                except SSHFerryError:
                    continue
                if not existing.is_dir:
                    raise

    @staticmethod
    def _ensure_local_directories(directories: list[str]) -> None:
        for directory in sorted(set(directories), key=lambda value: (value.count(os.sep), value)):
            os.makedirs(to_local_fs_path(directory), exist_ok=True)

    def _build_local_folder_file_plans(
        self,
        files: list[tuple[str, str, bool, int]],
        local_root: str,
        *,
        direction: str,
    ) -> list[dict[str, object]]:
        plans: list[dict[str, object]] = []
        for src_path, dst_path, _is_dir, size in files:
            local_path = src_path if direction == "upload" else dst_path
            rel_path = os.path.relpath(local_path, local_root).replace(os.sep, "/")
            plans.append(
                {
                    "src": src_path,
                    "dst": dst_path,
                    "size": size,
                    "rel_path": rel_path,
                    "tuple": (src_path, dst_path, False, size),
                }
            )
        return plans

    def _build_local_folder_mixed_plan(self, files: list[dict[str, object]]) -> dict[str, object]:
        large_files: list[dict[str, object]] = []
        small_files: list[dict[str, object]] = []
        for item in files:
            if int(item["size"]) >= self.parallel_threshold:
                large_files.append(item)
            else:
                small_files.append(item)
        batches: list[dict[str, object]] = []
        current_files: list[dict[str, object]] = []
        current_bytes = 0
        batch_index = 0
        for item in small_files:
            item_size = int(item["size"])
            if current_files and (
                current_bytes + item_size > self.folder_bundle_max_bytes
                or len(current_files) >= self.folder_bundle_max_files
            ):
                batches.append(
                    {
                        "bundle_id": f"bundle-{batch_index}",
                        "files": current_files,
                        "total_bytes": current_bytes,
                    }
                )
                batch_index += 1
                current_files = []
                current_bytes = 0
            current_files.append(item)
            current_bytes += item_size
        if current_files:
            batches.append(
                {
                    "bundle_id": f"bundle-{batch_index}",
                    "files": current_files,
                    "total_bytes": current_bytes,
                }
            )
        return {
            "large_files": large_files,
            "small_files": small_files,
            "small_batches": batches,
        }

    def _should_use_local_folder_mixed_transfer(self, mixed_plan: dict[str, object]) -> bool:
        if not self.folder_bundle_enabled:
            return False
        large_count = len(mixed_plan["large_files"])
        small_count = len(mixed_plan["small_files"])
        if large_count and small_count:
            return True
        if large_count:
            return True
        return small_count >= self.folder_bundle_file_count_threshold

    def _run_local_folder_transfer_mixed(
        self,
        task: Task,
        mixed_plan: dict[str, object],
        *,
        direction: str,
        local_root: str,
        remote_root: str,
        probe_engine: Optional[SftpEngine] = None,
    ) -> None:
        large_files = [item["tuple"] for item in mixed_plan["large_files"]]
        if large_files:
            self._run_local_folder_transfer_workers(
                task,
                large_files,
                direction=direction,
                probe_engine=probe_engine,
            )

        small_files = mixed_plan["small_files"]
        if not small_files:
            return

        site = self._require_site(
            task.dst_site_snapshot if direction == "upload" else task.src_site_snapshot,
            f"folder {direction} endpoint",
        )
        if direction == "upload" and self._remote_tree_appears_empty(probe_engine, remote_root):
            bundle_files = list(small_files)
            worker_files: list[tuple[str, str, bool, int]] = []
        else:
            bundle_files, worker_files = self._partition_local_folder_small_files(
                task,
                site,
                small_files,
                direction=direction,
                probe_engine=probe_engine,
            )
        if worker_files:
            self._run_local_folder_transfer_workers(
                task,
                worker_files,
                direction=direction,
                probe_engine=probe_engine,
            )
        if not bundle_files:
            return
        try:
            self._probe_remote_folder_bundle_support(site, engine=probe_engine)
        except SSHFerryError as exc:
            self.logger.warning(
                "folder_bundle_unavailable direction=%s root=%s reason=%s; falling back to per-file",
                direction,
                remote_root,
                exc.message,
            )
            self._run_local_folder_transfer_workers(
                task,
                [item["tuple"] for item in bundle_files],
                direction=direction,
                probe_engine=probe_engine,
            )
            return

        check_interrupt = self._interrupt_checker(task)
        transferred: dict[str, int] = {}
        progress_lock = Lock()
        small_batches = list(self._build_local_folder_mixed_plan(bundle_files)["small_batches"])
        aggregate_done = {"bytes": int(task.bytes_done)}
        progress_updater = self._make_task_progress_updater(task)

        def add_bundle_progress(bundle_key: str, label: str, absolute_done: int) -> None:
            with progress_lock:
                previous = transferred.get(bundle_key, 0)
                delta = max(0, absolute_done - previous)
                if delta <= 0:
                    return
                transferred[bundle_key] = absolute_done
                aggregate_done["bytes"] = min(task.bytes_total, aggregate_done["bytes"] + delta)
                current_done = aggregate_done["bytes"]
            progress_updater(current_done, task.bytes_total, current_file=label)

        def mark_bundle_complete(bundle_key: str, label: str, total_bytes: int, file_count: int) -> None:
            with progress_lock:
                previous = transferred.get(bundle_key, 0)
                if previous < total_bytes:
                    aggregate_done["bytes"] = min(task.bytes_total, aggregate_done["bytes"] + (total_bytes - previous))
                    transferred[bundle_key] = total_bytes
                current_done = aggregate_done["bytes"]
            with self.task_lock:
                self._record_task_progress_locked(task, current_done, task.bytes_total)
                task.subtask_done = min(task.subtask_count, task.subtask_done + file_count)
                task.current_file = label

        def transfer_one_batch(batch: dict[str, object], *, reuse_engine: Optional[SftpEngine] = None) -> None:
            if check_interrupt():
                raise InterruptedError("Task interrupted")
            bundle_label = f"{len(batch['files'])} files"
            bundle_key = str(batch["bundle_id"])
            try:
                if direction == "upload":
                    self._transfer_folder_upload_bundle(
                        task,
                        site,
                        local_root,
                        remote_root,
                        batch["files"],
                        engine=reuse_engine,
                        bundle_id=bundle_key,
                        add_progress=lambda done, _label=bundle_label, _key=bundle_key: add_bundle_progress(_key, _label, done),
                    )
                else:
                    self._transfer_folder_download_bundle(
                        task,
                        site,
                        remote_root,
                        local_root,
                        batch["files"],
                        engine=reuse_engine,
                        bundle_id=bundle_key,
                        add_progress=lambda done, _label=bundle_label, _key=bundle_key: add_bundle_progress(_key, _label, done),
                    )
                mark_bundle_complete(bundle_key, bundle_label, int(batch["total_bytes"]), len(batch["files"]))
            except SSHFerryError as exc:
                self.logger.warning(
                    "folder_bundle_failed direction=%s root=%s bundle=%s reason=%s; falling back to per-file for this batch",
                    direction,
                    remote_root,
                    bundle_key,
                    exc.message,
                )
                # Roll back the failed bundle's partial progress so the
                # per-file fallback does not double-count its bytes.
                with progress_lock:
                    previous = transferred.pop(bundle_key, 0)
                    if previous:
                        aggregate_done["bytes"] = max(0, aggregate_done["bytes"] - previous)
                    current_done = aggregate_done["bytes"]
                if previous:
                    progress_updater(current_done, task.bytes_total, force=True)
                self._run_local_folder_transfer_workers(
                    task,
                    [item["tuple"] for item in batch["files"]],
                    direction=direction,
                )

        bundle_worker_count = max(1, min(len(small_batches), self.folder_bundle_workers))
        if bundle_worker_count == 1:
            for batch in small_batches:
                transfer_one_batch(batch, reuse_engine=probe_engine)
            return

        with ThreadPoolExecutor(max_workers=bundle_worker_count) as executor:
            futures = [executor.submit(transfer_one_batch, batch) for batch in small_batches]
            wait(futures)
            for future in futures:
                future.result()

    def _partition_local_folder_small_files(
        self,
        task: Task,
        site: SiteConfig,
        files: list[dict[str, object]],
        *,
        direction: str,
        probe_engine: Optional[SftpEngine] = None,
    ) -> tuple[list[dict[str, object]], list[tuple[str, str, bool, int]]]:
        check_interrupt = self._interrupt_checker(task)
        bundle_files: list[dict[str, object]] = []
        worker_files: list[tuple[str, str, bool, int]] = []
        inspector = probe_engine if direction == "upload" and probe_engine is not None else None
        should_disconnect = False
        if direction == "upload" and inspector is None:
            inspector = SftpEngine(site, self.logger)
            should_disconnect = True
            if should_disconnect:
                inspector.connect()
        try:
            for item in files:
                if check_interrupt():
                    raise InterruptedError("Task interrupted")
                if direction == "upload":
                    skip_file, offset = self._inspect_upload_target_state(inspector, str(item["dst"]), int(item["size"]))
                else:
                    skip_file, offset = self._inspect_download_target_state(str(item["dst"]), int(item["size"]))
                if skip_file or offset > 0:
                    worker_files.append(item["tuple"])
                else:
                    bundle_files.append(item)
        finally:
            if should_disconnect and inspector is not None:
                inspector.disconnect()
        return bundle_files, worker_files

    def _remote_tree_appears_empty(self, engine: Optional[SftpEngine], remote_root: str) -> bool:
        if not self._can_reuse_bundle_engine(engine) or not getattr(engine, "ssh_client", None):
            return False
        check_cmd = (
            "sh -lc "
            + shlex.quote(
                f"if find {shlex.quote(remote_root)} -type f -print -quit 2>/dev/null | grep -q .; then "
                "printf 1; else printf 0; fi"
            )
        )
        try:
            exit_code, std_out, _std_err = self._exec_remote_shell(engine, check_cmd)
        except Exception:
            return False
        return exit_code == 0 and std_out.strip() == "0"

    def _run_local_folder_transfer_workers(
        self,
        task: Task,
        files: list[tuple[str, str, bool, int]],
        *,
        direction: str,
        probe_engine: Optional[SftpEngine] = None,
    ) -> None:
        queue: Queue[tuple[str, str, int]] = Queue()
        for src_path, dst_path, _is_dir, size in files:
            queue.put((src_path, dst_path, size))

        site = self._require_site(
            task.dst_site_snapshot if direction == "upload" else task.src_site_snapshot,
            f"folder {direction} endpoint",
        )
        progress_lock = Lock()
        stop_state = {"triggered": False}
        parallel_slots = Lock()
        slot_counter = {"active": 0}
        transferred: dict[str, int] = {}
        aggregate_done = {"bytes": int(task.bytes_done)}
        first_error: list[Exception] = []
        check_interrupt = self._interrupt_checker(task)
        progress_updater = self._make_task_progress_updater(task)

        def acquire_parallel_slot() -> None:
            while True:
                if check_interrupt():
                    raise InterruptedError("Task interrupted")
                with parallel_slots:
                    if slot_counter["active"] < self.folder_parallel_file_slots:
                        slot_counter["active"] += 1
                        return
                time.sleep(0.02)

        def release_parallel_slot() -> None:
            with parallel_slots:
                slot_counter["active"] = max(0, slot_counter["active"] - 1)

        def add_progress(file_key: str, absolute_done: int) -> None:
            label = os.path.basename(file_key)
            with progress_lock:
                previous = transferred.get(file_key, 0)
                delta = max(0, absolute_done - previous)
                if delta <= 0:
                    return
                transferred[file_key] = absolute_done
                aggregate_done["bytes"] = min(task.bytes_total, aggregate_done["bytes"] + delta)
                current_done = aggregate_done["bytes"]
            progress_updater(current_done, task.bytes_total, current_file=label)

        def mark_complete(file_key: str, file_size: int) -> None:
            label = os.path.basename(file_key)
            with progress_lock:
                previous = transferred.get(file_key, 0)
                if previous < file_size:
                    aggregate_done["bytes"] = min(task.bytes_total, aggregate_done["bytes"] + (file_size - previous))
                    transferred[file_key] = file_size
                current_done = aggregate_done["bytes"]
            with self.task_lock:
                self._record_task_progress_locked(task, current_done, task.bytes_total)
                task.subtask_done += 1
                task.current_file = label

        worker_count = max(1, min(self.folder_file_workers, max(1, len(files))))
        # paramiko's SFTPClient is not thread-safe: sharing the bootstrap
        # engine across concurrent workers (even for stat probes) can deadlock.
        # Only a single worker may reuse it.
        inspection_engine = probe_engine if worker_count == 1 else None

        def worker() -> None:
            # One persistent connection per worker instead of one SSH
            # handshake per file.
            worker_engine: Optional[SftpEngine] = None

            def get_engine() -> SftpEngine:
                nonlocal worker_engine
                if worker_engine is None:
                    engine = SftpEngine(site, self.logger)
                    engine.connect()
                    worker_engine = engine
                elif hasattr(worker_engine, "is_connected") and not worker_engine.is_connected():
                    worker_engine.connect()
                return worker_engine

            def reset_engine() -> None:
                nonlocal worker_engine
                if worker_engine is None:
                    return
                try:
                    worker_engine.disconnect()
                except Exception:
                    pass
                worker_engine = None

            try:
                while not stop_state["triggered"]:
                    try:
                        src_path, dst_path, file_size = queue.get(timeout=0.1)
                    except Empty:
                        if queue.empty():
                            break
                        continue
                    file_key = src_path
                    try:
                        if check_interrupt():
                            stop_state["triggered"] = True
                            # Surface the cancel; a silent return would let the
                            # task complete as "done" at 100%.
                            raise InterruptedError("Task interrupted")
                        attempts = 0
                        while True:
                            attempts += 1
                            try:
                                if direction == "upload":
                                    self._transfer_folder_upload_file(
                                        task,
                                        site,
                                        src_path,
                                        dst_path,
                                        file_size,
                                        file_key,
                                        add_progress,
                                        mark_complete,
                                        acquire_parallel_slot,
                                        release_parallel_slot,
                                        probe_engine=inspection_engine,
                                        engine_provider=get_engine,
                                    )
                                else:
                                    self._transfer_folder_download_file(
                                        task,
                                        site,
                                        src_path,
                                        dst_path,
                                        file_size,
                                        file_key,
                                        add_progress,
                                        mark_complete,
                                        acquire_parallel_slot,
                                        release_parallel_slot,
                                        engine_provider=get_engine,
                                    )
                                break
                            except InterruptedError:
                                raise
                            except SSHFerryError:
                                # The persistent connection may have dropped;
                                # retry once on a fresh one.
                                reset_engine()
                                if attempts >= 2:
                                    raise
                    except Exception as exc:
                        if not first_error:
                            first_error.append(exc)
                        stop_state["triggered"] = True
                        return
                    finally:
                        queue.task_done()
            finally:
                reset_engine()

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(worker) for _ in range(worker_count)]
            wait(futures)

        if first_error:
            raise first_error[0]

    def _transfer_folder_upload_file(
        self,
        task: Task,
        site: SiteConfig,
        local_path: str,
        remote_path: str,
        file_size: int,
        file_key: str,
        add_progress,
        mark_complete,
        acquire_parallel_slot,
        release_parallel_slot,
        probe_engine: Optional[SftpEngine] = None,
        engine_provider: Optional[Callable[[], SftpEngine]] = None,
    ) -> None:
        if probe_engine is not None:
            inspector = probe_engine
            should_disconnect = False
        elif engine_provider is not None:
            inspector = engine_provider()
            should_disconnect = False
        else:
            inspector = SftpEngine(site, self.logger)
            should_disconnect = True
            inspector.connect()
        try:
            skip_file, offset = self._inspect_upload_target_state(inspector, remote_path, file_size)
        finally:
            if should_disconnect:
                inspector.disconnect()
        if skip_file:
            add_progress(file_key, file_size)
            mark_complete(file_key, file_size)
            return
        if offset:
            add_progress(file_key, offset)
        if file_size >= self.parallel_threshold and offset == 0:
            acquire_parallel_slot()
            try:
                engine = ParallelSftpEngine(site, self.logger, preset_name=self.parallel_upload_preset)
                engine.upload_file(
                    local_path,
                    remote_path,
                    callback=lambda done, _total: add_progress(file_key, done),
                    check_interrupt=self._interrupt_checker(task),
                )
            finally:
                release_parallel_slot()
        else:
            if engine_provider is not None:
                engine_provider().upload_file(
                    local_path,
                    remote_path,
                    callback=lambda done, _total: add_progress(file_key, done),
                    check_interrupt=self._interrupt_checker(task),
                    offset=offset,
                )
            else:
                engine = SftpEngine(site, self.logger)
                engine.connect()
                try:
                    engine.upload_file(
                        local_path,
                        remote_path,
                        callback=lambda done, _total: add_progress(file_key, done),
                        check_interrupt=self._interrupt_checker(task),
                        offset=offset,
                    )
                finally:
                    engine.disconnect()
        mark_complete(file_key, file_size)

    def _transfer_folder_download_file(
        self,
        task: Task,
        site: SiteConfig,
        remote_path: str,
        local_path: str,
        file_size: int,
        file_key: str,
        add_progress,
        mark_complete,
        acquire_parallel_slot,
        release_parallel_slot,
        engine_provider: Optional[Callable[[], SftpEngine]] = None,
    ) -> None:
        skip_file, offset = self._inspect_download_target_state(local_path, file_size)
        if skip_file:
            add_progress(file_key, file_size)
            mark_complete(file_key, file_size)
            return
        if offset:
            add_progress(file_key, offset)
        if file_size >= self.parallel_threshold and offset == 0:
            acquire_parallel_slot()
            try:
                engine = ParallelSftpEngine(site, self.logger, preset_name=self.parallel_download_preset)
                engine.download_file(
                    remote_path,
                    local_path,
                    callback=lambda done, _total: add_progress(file_key, done),
                    check_interrupt=self._interrupt_checker(task),
                )
            finally:
                release_parallel_slot()
        else:
            if engine_provider is not None:
                engine_provider().download_file(
                    remote_path,
                    local_path,
                    callback=lambda done, _total: add_progress(file_key, done),
                    check_interrupt=self._interrupt_checker(task),
                    offset=offset,
                )
            else:
                engine = SftpEngine(site, self.logger)
                engine.connect()
                try:
                    engine.download_file(
                        remote_path,
                        local_path,
                        callback=lambda done, _total: add_progress(file_key, done),
                        check_interrupt=self._interrupt_checker(task),
                        offset=offset,
                    )
                finally:
                    engine.disconnect()
        mark_complete(file_key, file_size)

    def _probe_remote_folder_bundle_support(self, site: SiteConfig, engine: Optional[SftpEngine] = None) -> None:
        engine = engine if self._can_reuse_bundle_engine(engine) else SftpEngine(site, self.logger)
        should_disconnect = not self._can_reuse_bundle_engine(engine)
        try:
            if should_disconnect:
                engine.connect()
            if not getattr(engine, "ssh_client", None):
                raise SSHFerryError(ErrorCode.TRANSFER_FAILED, "Remote shell unavailable")
            exit_code, _std_out, std_err = self._exec_remote_shell(
                engine,
                "sh -lc 'command -v tar >/dev/null 2>&1'",
            )
            if exit_code != 0:
                raise SSHFerryError(
                    ErrorCode.TRANSFER_FAILED,
                    std_err.strip() or "Remote tar command unavailable",
                )
        finally:
            if should_disconnect:
                engine.disconnect()

    @staticmethod
    def _inspect_upload_target_state(engine: SftpEngine, remote_path: str, file_size: int) -> tuple[bool, int]:
        skip_file = False
        offset = 0
        try:
            stats = engine.stat(remote_path)
            if stats.size == file_size:
                skip_file = True
            elif stats.size < file_size:
                offset = stats.size
        except SSHFerryError as exc:
            if exc.code != ErrorCode.PATH_NOT_FOUND:
                raise
        return skip_file, offset

    @staticmethod
    def _inspect_download_target_state(local_path: str, file_size: int) -> tuple[bool, int]:
        skip_file = False
        offset = 0
        fs_local_path = to_local_fs_path(local_path)
        if os.path.exists(fs_local_path):
            local_size = os.path.getsize(fs_local_path)
            if local_size == file_size:
                skip_file = True
            elif local_size < file_size:
                offset = local_size
        return skip_file, offset

    def _transfer_folder_upload_bundle(
        self,
        task: Task,
        site: SiteConfig,
        local_dir: str,
        remote_dir: str,
        files: list[dict[str, object]],
        *,
        engine: Optional[SftpEngine] = None,
        bundle_id: str,
        add_progress,
    ) -> None:
        local_archive = None
        remote_archive = f"{remote_dir.rstrip('/')}/.sshferry-bundle-{bundle_id}-{int(time.time() * 1000)}.tar"
        check_interrupt = self._interrupt_checker(task)
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".tar") as temp_file:
                local_archive = temp_file.name
            with tarfile.open(local_archive, "w") as archive:
                for item in files:
                    if check_interrupt():
                        raise InterruptedError("Task interrupted")
                    archive.add(str(item["src"]), arcname=str(item["rel_path"]))
                if check_interrupt():
                    raise InterruptedError("Task interrupted")
            archive_size = max(1, os.path.getsize(local_archive))
            total_bytes = max(0, sum(int(item["size"]) for item in files))
            engine = engine if self._can_reuse_bundle_engine(engine) else SftpEngine(site, self.logger)
            should_disconnect = not self._can_reuse_bundle_engine(engine)
            try:
                if should_disconnect:
                    engine.connect()
                if archive_size >= self.folder_bundle_parallel_threshold:
                    parallel_engine = ParallelSftpEngine(
                        site,
                        self.logger,
                        preset_name=self.folder_bundle_parallel_upload_preset,
                    )
                    parallel_engine.upload_file(
                        local_archive,
                        remote_archive,
                        callback=lambda done, _total: add_progress(min(total_bytes, int(done * total_bytes / archive_size))),
                        check_interrupt=self._interrupt_checker(task),
                    )
                else:
                    engine.upload_file(
                        local_archive,
                        remote_archive,
                        callback=lambda done, _total: add_progress(min(total_bytes, int(done * total_bytes / archive_size))),
                        check_interrupt=self._interrupt_checker(task),
                    )
                extract_cmd = (
                    "sh -lc "
                    + shlex.quote(
                        f"mkdir -p -- {shlex.quote(remote_dir)} && "
                        f"tar -xf {shlex.quote(remote_archive)} -C {shlex.quote(remote_dir)} && "
                        f"rm -f -- {shlex.quote(remote_archive)}"
                    )
                )
                exit_code, _std_out, std_err = self._exec_remote_shell(engine, extract_cmd)
                if exit_code != 0:
                    raise SSHFerryError(ErrorCode.TRANSFER_FAILED, std_err.strip() or "Remote bundle extraction failed")
            finally:
                try:
                    engine.remove_file(remote_archive)
                except Exception:
                    pass
                if should_disconnect:
                    engine.disconnect()
        finally:
            if local_archive and os.path.exists(local_archive):
                os.remove(local_archive)

    def _transfer_folder_download_bundle(
        self,
        task: Task,
        site: SiteConfig,
        remote_dir: str,
        local_dir: str,
        files: list[dict[str, object]],
        *,
        engine: Optional[SftpEngine] = None,
        bundle_id: str,
        add_progress,
    ) -> None:
        local_archive = None
        remote_archive = f"{remote_dir.rstrip('/')}/.sshferry-bundle-{bundle_id}-{int(time.time() * 1000)}.tar"
        rel_paths = " ".join(shlex.quote(str(item["rel_path"])) for item in files)
        create_cmd = (
            "sh -lc "
            + shlex.quote(
                f"cd {shlex.quote(remote_dir)} && tar -cf {shlex.quote(remote_archive)} -- {rel_paths}"
            )
        )
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".tar") as temp_file:
                local_archive = temp_file.name
            engine = engine if self._can_reuse_bundle_engine(engine) else SftpEngine(site, self.logger)
            should_disconnect = not self._can_reuse_bundle_engine(engine)
            try:
                if should_disconnect:
                    engine.connect()
                exit_code, _std_out, std_err = self._exec_remote_shell(engine, create_cmd)
                if exit_code != 0:
                    raise SSHFerryError(ErrorCode.TRANSFER_FAILED, std_err.strip() or "Remote bundle creation failed")
                archive_size = max(1, engine.stat(remote_archive).size)
                total_bytes = max(0, sum(int(item["size"]) for item in files))
                if archive_size >= self.folder_bundle_parallel_threshold:
                    parallel_engine = ParallelSftpEngine(
                        site,
                        self.logger,
                        preset_name=self.folder_bundle_parallel_download_preset,
                    )
                    parallel_engine.download_file(
                        remote_archive,
                        local_archive,
                        callback=lambda done, _total: add_progress(min(total_bytes, int(done * total_bytes / archive_size))),
                        check_interrupt=self._interrupt_checker(task),
                    )
                else:
                    engine.download_file(
                        remote_archive,
                        local_archive,
                        callback=lambda done, _total: add_progress(min(total_bytes, int(done * total_bytes / archive_size))),
                        check_interrupt=self._interrupt_checker(task),
                    )
            finally:
                try:
                    engine.remove_file(remote_archive)
                except Exception:
                    pass
                if should_disconnect:
                    engine.disconnect()
            with tarfile.open(local_archive, "r") as archive:
                self._extract_bundle_archive(archive, to_local_fs_path(local_dir))
        finally:
            if local_archive and os.path.exists(local_archive):
                os.remove(local_archive)

    @staticmethod
    def _extract_bundle_archive(archive: tarfile.TarFile, destination: str) -> None:
        """Extract a remote-produced tar, refusing path-traversal members."""
        try:
            archive.extractall(destination, filter="data")
        except TypeError:
            # Python < 3.11.4 has no extraction filter; validate manually.
            members = []
            for member in archive.getmembers():
                name = member.name
                if name.startswith(("/", "\\")) or ".." in PurePosixPath(name).parts:
                    raise SSHFerryError(
                        ErrorCode.TRANSFER_FAILED,
                        f"Unsafe path in bundle archive: {name}",
                    )
                if member.issym() or member.islnk():
                    raise SSHFerryError(
                        ErrorCode.TRANSFER_FAILED,
                        f"Link member not allowed in bundle archive: {name}",
                    )
                members.append(member)
            archive.extractall(destination, members=members)

    @staticmethod
    def _can_reuse_bundle_engine(engine: Optional[SftpEngine]) -> bool:
        return bool(
            engine
            and getattr(engine, "ssh_client", None) is not None
            and getattr(engine, "sftp_client", None) is not None
        )

    @staticmethod
    def _exec_remote_shell(engine: SftpEngine, command: str) -> tuple[int, str, str]:
        if not getattr(engine, "ssh_client", None):
            raise SSHFerryError(ErrorCode.REMOTE_DISCONNECT, "Remote shell unavailable")
        _stdin, stdout, stderr = engine.ssh_client.exec_command(command)
        exit_code = stdout.channel.recv_exit_status()
        return (
            exit_code,
            stdout.read().decode(errors="replace"),
            stderr.read().decode(errors="replace"),
        )

    def _metric_preset_for_task(self, task: Task) -> str:
        if task.engine not in ("parallel", "dualpath"):
            return task.engine
        if task.is_local_to_remote:
            return self.parallel_upload_preset
        if task.is_remote_to_local:
            return self.parallel_download_preset
        return self.parallel_preset

    @staticmethod
    def _require_site(site: Optional[SiteConfig], label: str) -> SiteConfig:
        if not site:
            raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, f"Missing {label} site configuration")
        return site

    def _remote_to_remote_resume_state(self, task: Task, dst_site: SiteConfig) -> tuple[int, bool]:
        engine = SftpEngine(dst_site, self.logger)
        try:
            engine.connect()
            try:
                remote_stat = engine.stat(task.dst)
            except SSHFerryError as exc:
                if exc.code == ErrorCode.PATH_NOT_FOUND:
                    return 0, False
                raise
            remote_size = max(0, remote_stat.size)
            if remote_size == task.bytes_total and task.bytes_total > 0 and task.bytes_done > 0:
                self.logger.info(
                    "remote_resume_state task=%s dst=%s remote_size=%s action=skip_complete",
                    task.task_id[:8],
                    task.dst,
                    remote_size,
                )
                return task.bytes_total, True
            if task.bytes_done <= 0:
                if remote_size > 0:
                    self.logger.info(
                        "remote_resume_state task=%s dst=%s remote_size=%s action=ignore_no_local_progress",
                        task.task_id[:8],
                        task.dst,
                        remote_size,
                    )
                return 0, False
            if 0 < remote_size < task.bytes_total:
                with self.task_lock:
                    task.bytes_done = min(task.bytes_total, remote_size)
                self.logger.info(
                    "remote_resume_state task=%s dst=%s remote_size=%s action=resume_partial",
                    task.task_id[:8],
                    task.dst,
                    remote_size,
                )
                return remote_size, False
            if remote_size == task.bytes_total and task.bytes_done >= task.bytes_total:
                self.logger.info(
                    "remote_resume_state task=%s dst=%s remote_size=%s action=resume_complete",
                    task.task_id[:8],
                    task.dst,
                    remote_size,
                )
                return task.bytes_total, True
            self.logger.info(
                "remote_resume_state task=%s dst=%s remote_size=%s bytes_done=%s action=restart_from_zero",
                task.task_id[:8],
                task.dst,
                remote_size,
                task.bytes_done,
            )
            return 0, False
        finally:
            engine.disconnect()

    @staticmethod
    def create_upload_task(
        local_path: str,
        remote_path: str,
        file_size: int,
        engine: str = "sftp",
        auto_engine: bool = True,
        threshold: int = DEFAULT_PARALLEL_THRESHOLD_BYTES,
        dst_site: Optional[SiteConfig] = None,
        dst_session_id: Optional[str] = None,
        dst_display_name: Optional[str] = None,
    ) -> Task:
        if auto_engine and engine != "scp" and file_size >= threshold:
            engine = "parallel"
        return Task(
            task_id=str(uuid.uuid4()),
            kind="file_transfer",
            engine=engine,
            src=local_path,
            dst=remote_path,
            bytes_total=file_size,
            src_endpoint_type="local",
            dst_endpoint_type="remote",
            dst_session_id=dst_session_id,
            dst_site_snapshot=dst_site,
            dst_display_name=dst_display_name or (dst_site.name if dst_site else None),
            status="pending",
        )

    @staticmethod
    def create_download_task(
        remote_path: str,
        local_path: str,
        file_size: int,
        engine: str = "sftp",
        auto_engine: bool = True,
        threshold: int = DEFAULT_PARALLEL_THRESHOLD_BYTES,
        src_site: Optional[SiteConfig] = None,
        src_session_id: Optional[str] = None,
        src_display_name: Optional[str] = None,
    ) -> Task:
        if auto_engine and engine != "scp" and file_size >= threshold:
            engine = "parallel"
        return Task(
            task_id=str(uuid.uuid4()),
            kind="file_transfer",
            engine=engine,
            src=remote_path,
            dst=local_path,
            bytes_total=file_size,
            src_endpoint_type="remote",
            dst_endpoint_type="local",
            src_session_id=src_session_id,
            src_site_snapshot=src_site,
            src_display_name=src_display_name or (src_site.name if src_site else None),
            status="pending",
        )

    @staticmethod
    def create_remote_to_remote_task(
        src_path: str,
        dst_path: str,
        file_size: int,
        src_site: SiteConfig,
        dst_site: SiteConfig,
        src_session_id: Optional[str] = None,
        dst_session_id: Optional[str] = None,
        engine: str = "sftp",
    ) -> Task:
        return Task(
            task_id=str(uuid.uuid4()),
            kind="file_transfer",
            engine=engine,
            src=src_path,
            dst=dst_path,
            bytes_total=file_size,
            src_endpoint_type="remote",
            dst_endpoint_type="remote",
            src_session_id=src_session_id or src_site.name,
            dst_session_id=dst_session_id or dst_site.name,
            src_site_snapshot=src_site,
            dst_site_snapshot=dst_site,
            src_display_name=src_site.name,
            dst_display_name=dst_site.name,
            status="pending",
        )

    @staticmethod
    def create_mkdir_task(
        remote_path: str,
        engine: str = "sftp",
        dst_site: Optional[SiteConfig] = None,
        dst_session_id: Optional[str] = None,
        dst_display_name: Optional[str] = None,
    ) -> Task:
        return Task(
            task_id=str(uuid.uuid4()),
            kind="mkdir",
            engine=engine,
            src="",
            dst=remote_path,
            bytes_total=0,
            src_endpoint_type="local",
            dst_endpoint_type="remote",
            dst_session_id=dst_session_id,
            dst_site_snapshot=dst_site,
            dst_display_name=dst_display_name or (dst_site.name if dst_site else None),
            status="pending",
        )

    @staticmethod
    def create_delete_task(
        remote_path: str,
        engine: str = "sftp",
        src_site: Optional[SiteConfig] = None,
        src_session_id: Optional[str] = None,
        src_display_name: Optional[str] = None,
    ) -> Task:
        return Task(
            task_id=str(uuid.uuid4()),
            kind="delete",
            engine=engine,
            src=remote_path,
            dst="",
            bytes_total=0,
            src_endpoint_type="remote",
            dst_endpoint_type="local",
            src_session_id=src_session_id,
            src_site_snapshot=src_site,
            src_display_name=src_display_name or (src_site.name if src_site else None),
            status="pending",
        )

    @staticmethod
    def create_folder_upload_task(
        local_dir: str,
        remote_dir: str,
        total_files: int,
        total_bytes: int,
        engine: str = "sftp",
        dst_site: Optional[SiteConfig] = None,
        dst_session_id: Optional[str] = None,
        dst_display_name: Optional[str] = None,
    ) -> Task:
        return Task(
            task_id=str(uuid.uuid4()),
            kind="folder_transfer",
            engine=engine,
            src=local_dir,
            dst=remote_dir,
            bytes_total=total_bytes,
            subtask_count=total_files,
            src_endpoint_type="local",
            dst_endpoint_type="remote",
            dst_session_id=dst_session_id,
            dst_site_snapshot=dst_site,
            dst_display_name=dst_display_name or (dst_site.name if dst_site else None),
            status="pending",
        )

    @staticmethod
    def create_folder_download_task(
        remote_dir: str,
        local_dir: str,
        total_files: int,
        total_bytes: int,
        engine: str = "sftp",
        src_site: Optional[SiteConfig] = None,
        src_session_id: Optional[str] = None,
        src_display_name: Optional[str] = None,
    ) -> Task:
        return Task(
            task_id=str(uuid.uuid4()),
            kind="folder_transfer",
            engine=engine,
            src=remote_dir,
            dst=local_dir,
            bytes_total=total_bytes,
            subtask_count=total_files,
            src_endpoint_type="remote",
            dst_endpoint_type="local",
            src_session_id=src_session_id,
            src_site_snapshot=src_site,
            src_display_name=src_display_name or (src_site.name if src_site else None),
            status="pending",
        )

    @staticmethod
    def create_folder_remote_to_remote_task(
        src_dir: str,
        dst_dir: str,
        total_files: int,
        total_bytes: int,
        src_site: SiteConfig,
        dst_site: SiteConfig,
        src_session_id: Optional[str] = None,
        dst_session_id: Optional[str] = None,
        engine: str = "sftp",
    ) -> Task:
        return Task(
            task_id=str(uuid.uuid4()),
            kind="folder_transfer",
            engine=engine,
            src=src_dir,
            dst=dst_dir,
            bytes_total=total_bytes,
            subtask_count=total_files,
            src_endpoint_type="remote",
            dst_endpoint_type="remote",
            src_session_id=src_session_id or src_site.name,
            dst_session_id=dst_session_id or dst_site.name,
            src_site_snapshot=src_site,
            dst_site_snapshot=dst_site,
            src_display_name=src_site.name,
            dst_display_name=dst_site.name,
            status="pending",
        )
