"""Task scheduler for managing local/remote and remote/remote tasks."""
from collections import defaultdict
from dataclasses import replace
import logging
import os
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock, Thread
from typing import Dict, List, Optional

from src.core.task_state import assert_transition
from src.engines.parallel_sftp_engine import DEFAULT_PARALLEL_THRESHOLD_BYTES, ParallelSftpEngine
from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine
from src.engines.scp_engine import ScpEngine
from src.engines.sftp_engine import SftpEngine
from src.services.metrics import MetricsCollector, TransferRecord
from src.shared.errors import ErrorCode, SSHFerryError
from src.shared.logging_ import log_task_event
from src.shared.models import SiteConfig, Task


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
        parallel_threshold: int = DEFAULT_PARALLEL_THRESHOLD_BYTES,
        logger: Optional[logging.Logger] = None,
    ):
        self.site_config = site_config
        self.max_workers = max_workers
        self.max_workers_sftp = max_workers_sftp
        self.max_workers_scp = max_workers_scp
        self.max_workers_parallel = max_workers_parallel
        self.parallel_preset = parallel_preset
        self.parallel_upload_preset = parallel_upload_preset or parallel_preset
        self.parallel_download_preset = parallel_download_preset or parallel_preset
        self.parallel_threshold = parallel_threshold
        self.logger = logger or logging.getLogger(__name__)

        self.tasks: Dict[str, Task] = {}
        self.task_lock = Lock()
        self.task_queue: List[str] = []
        self.queued_task_ids: set[str] = set()
        self.active_task_ids: set[str] = set()
        self.active_by_protocol: dict[str, int] = defaultdict(int)
        self.protocol_limits = {
            "sftp": max_workers_sftp,
            "scp": max_workers_scp,
            "parallel": max_workers_parallel,
        }
        self._rr_protocols = ["sftp", "scp", "parallel"]
        self._rr_index = 0
        self._last_scheduler_stats_log = 0.0

        self.executor = ThreadPoolExecutor(max_workers=max_workers)
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
            if task.task_id not in self.queued_task_ids:
                self.task_queue.append(task.task_id)
                self.queued_task_ids.add(task.task_id)
        self.logger.info("Added task %s: %s %s -> %s", task.task_id, task.kind, task.src, task.dst)
        return task.task_id

    def get_task(self, task_id: str) -> Optional[Task]:
        with self.task_lock:
            return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[Task]:
        with self.task_lock:
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
                return True
            if task.status == "running":
                task.interrupted = True
                return True
            if task.status == "paused":
                self._set_task_status_locked(task, "canceled")
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
        return task.engine if task.engine in ("sftp", "scp", "parallel") else "sftp"

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
            self._set_task_status_locked(task, "running")
            task.start_time = time.time()

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
        except SSHFerryError as exc:
            with self.task_lock:
                self._set_task_status_locked(task, "failed")
                task.end_time = time.time()
                task.error_code = exc.code
                task.error_message = exc.message
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
        except Exception as exc:
            with self.task_lock:
                self._set_task_status_locked(task, "failed")
                task.end_time = time.time()
                task.error_code = ErrorCode.UNKNOWN_ERROR
                task.error_message = str(exc)
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
        def callback(bytes_transferred, bytes_total):
            with self.task_lock:
                task.bytes_done = bytes_transferred
                task.bytes_total = bytes_total
                if task.start_time:
                    elapsed = time.time() - task.start_time
                    if elapsed > 0:
                        task.speed = bytes_transferred / elapsed

        return callback

    def _interrupt_checker(self, task: Task):
        def check_interrupt():
            if task.paused:
                with self.task_lock:
                    task.status = "paused"
                raise InterruptedError("Task paused")
            return task.interrupted

        return check_interrupt

    def _handle_interrupted(self, task: Task) -> None:
        with self.task_lock:
            if task.paused:
                self._set_task_status_locked(task, "paused")
            else:
                self._set_task_status_locked(task, "canceled")

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
                if os.path.exists(task.dst):
                    local_size = os.path.getsize(task.dst)
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
        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            self.logger,
            parallel_threshold=self.parallel_threshold,
            relay_download_preset=self.parallel_download_preset,
            relay_upload_preset=self.parallel_upload_preset,
        )
        engine.transfer_file(
            task.src,
            task.dst,
            callback=self._progress_callback(task),
            check_interrupt=self._interrupt_checker(task),
        )

    def _execute_remote_to_remote_folder(self, task: Task):
        src_site = self._require_site(task.src_site_snapshot, "remote source")
        dst_site = self._require_site(task.dst_site_snapshot, "remote destination")
        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            self.logger,
            parallel_threshold=self.parallel_threshold,
            relay_download_preset=self.parallel_download_preset,
            relay_upload_preset=self.parallel_upload_preset,
        )
        engine.transfer_dir(
            task.src,
            task.dst,
            callback=self._progress_callback(task),
            check_interrupt=self._interrupt_checker(task),
        )
        if not task.subtask_count:
            task.subtask_count = 1
            task.subtask_done = 1

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
                        task.bytes_done = min(task.bytes_total, base_bytes + bytes_transferred)
                        if task.start_time:
                            elapsed = time.time() - task.start_time
                            if elapsed > 0:
                                task.speed = task.bytes_done / elapsed

                engine.upload_file(full_path, remote_path, callback=progress_callback, check_interrupt=check_interrupt, offset=offset)
                with self.task_lock:
                    task.subtask_done += 1
                    task.bytes_done = min(task.bytes_total, base_bytes + file_size)
            elif os.path.isdir(full_path):
                self._upload_dir_recursive(engine, task, full_path, remote_path)

    def _download_dir_recursive(self, engine: SftpEngine, task: Task, remote_dir: str, local_dir: str):
        os.makedirs(local_dir, exist_ok=True)
        entries = engine.list_dir(remote_dir)
        check_interrupt = self._interrupt_checker(task)
        for entry in entries:
            if check_interrupt():
                raise InterruptedError("Task interrupted")
            local_path = os.path.join(local_dir, entry.name)
            if entry.is_dir:
                self._download_dir_recursive(engine, task, entry.path, local_path)
                continue
            offset = 0
            skip_file = False
            if os.path.exists(local_path):
                local_size = os.path.getsize(local_path)
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
                    task.bytes_done = min(task.bytes_total, base_bytes + bytes_transferred)
                    if task.start_time:
                        elapsed = time.time() - task.start_time
                        if elapsed > 0:
                            task.speed = task.bytes_done / elapsed

            engine.download_file(entry.path, local_path, callback=progress_callback, check_interrupt=check_interrupt, offset=offset)
            with self.task_lock:
                task.subtask_done += 1
                task.bytes_done = min(task.bytes_total, base_bytes + entry.size)

    def _metric_preset_for_task(self, task: Task) -> str:
        if task.engine != "parallel":
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
