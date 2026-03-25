"""Remote-to-remote transfer engine with direct, relay, and dual-path modes."""
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from queue import Empty, Queue
from typing import Callable, Optional

from src.engines.parallel_sftp_engine import (
    DEFAULT_PARALLEL_THRESHOLD_BYTES,
    PARALLEL_PRESETS,
    ParallelSftpEngine,
)
from src.engines.sftp_engine import SftpEngine
from src.shared.errors import ErrorCode, SSHFerryError
from src.shared.models import SiteConfig
from src.shared.paths import ensure_in_sandbox, normalize_remote_path
from src.shared.remote_scan import scan_remote_tree_via_shell


class RemoteToRemoteTransferEngine:
    """Transfer files/folders between two remote SSH sites."""

    def __init__(
        self,
        src_site: SiteConfig,
        dst_site: SiteConfig,
        logger,
        parallel_threshold: int = DEFAULT_PARALLEL_THRESHOLD_BYTES,
        dualpath_threshold: int | None = None,
        dualpath_chunk_size: int | None = None,
        relay_download_preset: str = "high",
        relay_upload_preset: str = "medium",
    ):
        self.src_site = src_site
        self.dst_site = dst_site
        self.logger = logger
        self.parallel_threshold = parallel_threshold
        self.dualpath_threshold = dualpath_threshold or max(parallel_threshold, 128 * 1024 * 1024)
        self.dualpath_chunk_size = max(
            1024 * 1024,
            dualpath_chunk_size or int(os.getenv("SSHFERRY_REMOTE_DUALPATH_CHUNK_BYTES", str(32 * 1024 * 1024))),
        )
        self.relay_download_preset = relay_download_preset
        self.relay_upload_preset = relay_upload_preset
        self.folder_file_workers = max(1, int(os.getenv("SSHFERRY_FOLDER_FILE_WORKERS", "3") or "3"))
        self.folder_parallel_file_slots = max(1, int(os.getenv("SSHFERRY_FOLDER_PARALLEL_FILE_SLOTS", "1") or "1"))
        self.folder_large_file_workers = max(
            1,
            int(os.getenv("SSHFERRY_REMOTE_DIR_LARGE_FILE_WORKERS", "2") or "2"),
        )
        self.folder_bundle_workers = max(
            1,
            int(os.getenv("SSHFERRY_REMOTE_DIR_BUNDLE_WORKERS", "4") or "4"),
        )
        self.dir_bundle_enabled = os.getenv(
            "SSHFERRY_REMOTE_DIR_ARCHIVE_ENABLED",
            "1",
        ).strip().lower() not in ("0", "false", "no", "off")
        self.dir_bundle_file_count_threshold = max(
            1,
            int(os.getenv("SSHFERRY_REMOTE_DIR_ARCHIVE_FILE_COUNT_THRESHOLD", "32") or "32"),
        )
        self.dir_bundle_max_bytes = max(
            1024 * 1024,
            int(os.getenv("SSHFERRY_REMOTE_DIR_ARCHIVE_MAX_BYTES", str(256 * 1024 * 1024)) or str(256 * 1024 * 1024)),
        )
        self.dir_bundle_max_files = max(
            1,
            int(os.getenv("SSHFERRY_REMOTE_DIR_ARCHIVE_MAX_FILES", "256") or "256"),
        )
        self.dualpath_enabled = os.getenv("SSHFERRY_REMOTE_DUALPATH_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")
        self.dualpath_max_dup_chunks = max(1, int(os.getenv("SSHFERRY_REMOTE_DUALPATH_MAX_DUP_CHUNKS", "1") or "1"))
        self.dualpath_slow_factor = max(1.1, float(os.getenv("SSHFERRY_REMOTE_DUALPATH_SLOW_FACTOR", "1.8") or "1.8"))
        self.dualpath_min_sample_seconds = max(
            0.2,
            float(os.getenv("SSHFERRY_REMOTE_DUALPATH_MIN_SAMPLE_SECONDS", "1.5") or "1.5"),
        )
        self.dualpath_initial_lanes = max(1, min(2, int(os.getenv("SSHFERRY_REMOTE_DUALPATH_INITIAL_LANES", "1") or "1")))
        self.dualpath_lane_ramp_delay_seconds = max(
            0.0,
            float(os.getenv("SSHFERRY_REMOTE_DUALPATH_RAMP_DELAY_SECONDS", "0.5") or "0.5"),
        )
        self.dualpath_report_granularity = max(
            64 * 1024,
            int(os.getenv("SSHFERRY_REMOTE_DUALPATH_REPORT_BYTES", str(1024 * 1024)) or str(1024 * 1024)),
        )
        self.direct_ephemeral_key_enabled = os.getenv(
            "SSHFERRY_REMOTE_DIRECT_EPHEMERAL_KEY_ENABLED",
            "1",
        ).strip().lower() not in ("0", "false", "no", "off")
        self.direct_progress_poll_interval_seconds = max(
            0.1,
            float(os.getenv("SSHFERRY_REMOTE_DIRECT_PROGRESS_POLL_SECONDS", "0.5") or "0.5"),
        )
        self._cached_direct_auth: dict[str, str] | None = None
        self._cached_direct_auth_mode: str | None = None
        self._direct_auth_lock = threading.Lock()

    def transfer_file(
        self,
        src_path: str,
        dst_path: str,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
        resume_offset: int = 0,
        requested_engine: str | None = None,
        cleanup_cached_auth: bool = True,
    ) -> str:
        """Transfer one file. Returns transfer mode used: direct or relay."""
        try:
            normalized_src = normalize_remote_path(src_path)
            normalized_dst = normalize_remote_path(dst_path)
            ensure_in_sandbox(normalized_src, self.src_site.remote_root)
            ensure_in_sandbox(normalized_dst, self.dst_site.remote_root)
            total = self._remote_file_size(normalized_src)
            resume_offset = max(0, min(resume_offset, total))
            requested_engine = (requested_engine or "auto").strip().lower()
            if resume_offset >= total and total > 0:
                if callback:
                    callback(total, total)
                self.logger.info(
                    "remote_transfer_mode mode=bridge_resume_complete src=%s dst=%s bytes=%s resume_offset=%s",
                    normalized_src,
                    normalized_dst,
                    total,
                    resume_offset,
                )
                return "bridge_resume_complete"
            if resume_offset > 0:
                if self._can_attempt_direct_copy():
                    try:
                        self._transfer_file_direct_resume(
                            normalized_src,
                            normalized_dst,
                            total,
                            resume_offset,
                            callback=callback,
                            check_interrupt=check_interrupt,
                        )
                        self.logger.info(
                            "remote_transfer_mode mode=direct_resume src=%s dst=%s bytes=%s resume_offset=%s",
                            normalized_src,
                            normalized_dst,
                            total,
                            resume_offset,
                        )
                        return "direct_resume"
                    except SSHFerryError as exc:
                        self.logger.warning(
                            "remote_direct_resume_failed src=%s dst=%s resume_offset=%s reason=%s; falling back",
                            normalized_src,
                            normalized_dst,
                            resume_offset,
                            exc.message,
                        )
                self.logger.info(
                    "remote_transfer_mode mode=bridge_resume src=%s dst=%s bytes=%s resume_offset=%s",
                    normalized_src,
                    normalized_dst,
                    total,
                    resume_offset,
                )
                self._transfer_file_relay(
                    normalized_src,
                    normalized_dst,
                    callback=callback,
                    check_interrupt=check_interrupt,
                    total=total,
                    offset=resume_offset,
                )
                return "bridge_resume"
            if requested_engine == "dualpath" and self.dualpath_enabled:
                self.logger.info(
                    "remote_transfer_mode mode=dualpath_forced src=%s dst=%s bytes=%s",
                    normalized_src,
                    normalized_dst,
                    total,
                )
                self._transfer_file_dualpath(
                    normalized_src,
                    normalized_dst,
                    total,
                    callback=callback,
                    check_interrupt=check_interrupt,
                )
                return "dualpath"
            direct_unavailable_reason = self._direct_unavailable_reason()
            if self._can_attempt_direct_copy():
                try:
                    self._transfer_file_direct(normalized_src, normalized_dst, callback=callback, check_interrupt=check_interrupt)
                    self.logger.info(
                        "remote_transfer_mode mode=direct src=%s dst=%s bytes=%s",
                        normalized_src,
                        normalized_dst,
                        total,
                    )
                    return "direct"
                except SSHFerryError as exc:
                    self.logger.warning(
                        "remote_direct_failed src=%s dst=%s reason=%s; falling back",
                        normalized_src,
                        normalized_dst,
                        exc.message,
                    )
            if self.dualpath_enabled and total >= self.dualpath_threshold:
                self.logger.info(
                    "remote_transfer_mode mode=dualpath src=%s dst=%s bytes=%s direct_available=%s direct_reason=%s",
                    normalized_src,
                    normalized_dst,
                    total,
                    self._can_attempt_direct_copy(),
                    direct_unavailable_reason or "direct_failed_or_skipped",
                )
                self._transfer_file_dualpath(
                    normalized_src,
                    normalized_dst,
                    total,
                    callback=callback,
                    check_interrupt=check_interrupt,
                )
                return "dualpath"
            if total >= self.parallel_threshold:
                self.logger.info(
                    "remote_transfer_mode mode=parallel_bridge src=%s dst=%s bytes=%s direct_available=%s direct_reason=%s",
                    normalized_src,
                    normalized_dst,
                    total,
                    self._can_attempt_direct_copy(),
                    direct_unavailable_reason or "direct_failed_or_skipped",
                )
                self._transfer_file_parallel_bridge(
                    normalized_src,
                    normalized_dst,
                    total,
                    callback=callback,
                    check_interrupt=check_interrupt,
                )
                return "parallel_bridge"
            self.logger.info(
                "remote_transfer_mode mode=bridge src=%s dst=%s bytes=%s direct_available=%s direct_reason=%s",
                normalized_src,
                normalized_dst,
                total,
                self._can_attempt_direct_copy(),
                direct_unavailable_reason or "direct_failed_or_skipped",
            )
            self._transfer_file_relay(
                normalized_src,
                normalized_dst,
                callback=callback,
                check_interrupt=check_interrupt,
                total=total,
            )
            return "bridge"
        finally:
            if cleanup_cached_auth:
                self._cleanup_cached_direct_auth()

    def transfer_dir(
        self,
        src_dir: str,
        dst_dir: str,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
        item_callback: Optional[Callable[[str, str, int], None]] = None,
    ) -> str:
        """Transfer a directory recursively. Returns transfer mode used."""
        try:
            normalized_src = normalize_remote_path(src_dir)
            normalized_dst = normalize_remote_path(dst_dir)
            ensure_in_sandbox(normalized_src, self.src_site.remote_root)
            ensure_in_sandbox(normalized_dst, self.dst_site.remote_root)
            dir_plan = self._plan_remote_dir_transfer(normalized_src, normalized_dst)
            if self._should_use_mixed_dir_transfer(dir_plan):
                try:
                    self._transfer_dir_mixed(
                        normalized_src,
                        normalized_dst,
                        dir_plan,
                        callback=callback,
                        check_interrupt=check_interrupt,
                        item_callback=item_callback,
                    )
                    return "dir_mixed"
                except SSHFerryError as exc:
                    self.logger.warning(
                        "remote_mixed_dir_failed src=%s dst=%s reason=%s; falling back",
                        normalized_src,
                        normalized_dst,
                        exc.message,
                    )
            try:
                self._transfer_dir_direct(
                    normalized_src,
                    normalized_dst,
                    callback=callback,
                    check_interrupt=check_interrupt,
                )
                return "direct"
            except SSHFerryError as exc:
                self.logger.warning("remote_direct_dir_failed src=%s dst=%s reason=%s", normalized_src, normalized_dst, exc.message)
                self._transfer_dir_relay(
                    normalized_src,
                    normalized_dst,
                    callback=callback,
                    check_interrupt=check_interrupt,
                    item_callback=item_callback,
                )
                return "bridge"
        finally:
            self._cleanup_cached_direct_auth()

    def _transfer_file_direct(
        self,
        src_path: str,
        dst_path: str,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> None:
        """Attempt remote-to-remote direct copy via scp from source host."""
        direct_reason = self._direct_unavailable_reason()
        if direct_reason:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, f"Direct remote copy unavailable: {direct_reason}")
        src_engine = SftpEngine(self.src_site, self.logger)
        dst_engine = SftpEngine(self.dst_site, self.logger)
        direct_auth: dict[str, str] | None = None
        try:
            src_engine.connect()
            dst_engine.connect()
            src_stat = src_engine.stat(src_path)
            total = src_stat.size
            if callback:
                callback(0, total)
            if check_interrupt and check_interrupt():
                raise InterruptedError("Task interrupted")

            direct_auth = self._prepare_direct_auth(src_engine, dst_engine)
            self._probe_direct_connectivity(src_engine, dst_path, direct_auth=direct_auth)
            cmd = self._build_direct_scp_command(src_path, dst_path, direct_auth=direct_auth)
            self.logger.info(
                "remote_direct_exec phase=scp src=%s dst=%s auth=%s command=%s",
                src_path,
                dst_path,
                self._direct_auth_label(direct_auth),
                self._summarize_command(cmd),
            )
            exit_code, std_out, std_err = self._exec_remote_command_with_progress(
                src_engine,
                dst_engine,
                cmd,
                dst_path,
                total,
                callback=callback,
                check_interrupt=check_interrupt,
            )
            if exit_code != 0:
                raise SSHFerryError(
                    ErrorCode.TRANSFER_FAILED,
                    self._format_direct_failure("scp", exit_code, std_out, std_err),
                )
            if callback:
                callback(total, total)
        except InterruptedError:
            self.logger.info(
                "remote_direct_interrupted src=%s dst=%s auth=%s reason=interrupted",
                src_path,
                dst_path,
                self._direct_auth_label(direct_auth),
            )
            raise
        finally:
            dst_engine.disconnect()
            src_engine.disconnect()

    def _transfer_file_direct_resume(
        self,
        src_path: str,
        dst_path: str,
        total: int,
        resume_offset: int,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> None:
        direct_reason = self._direct_unavailable_reason()
        if direct_reason:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, f"Direct remote copy unavailable: {direct_reason}")
        src_engine = SftpEngine(self.src_site, self.logger)
        dst_engine = SftpEngine(self.dst_site, self.logger)
        direct_auth: dict[str, str] | None = None
        try:
            src_engine.connect()
            dst_engine.connect()
            if callback:
                callback(resume_offset, total)
            if check_interrupt and check_interrupt():
                raise InterruptedError("Task interrupted")

            direct_auth = self._prepare_direct_auth(src_engine, dst_engine)
            self._probe_direct_connectivity(src_engine, dst_path, direct_auth=direct_auth)
            cmd = self._build_direct_resume_command(src_path, dst_path, resume_offset, direct_auth=direct_auth)
            self.logger.info(
                "remote_direct_exec phase=scp_resume src=%s dst=%s auth=%s resume_offset=%s command=%s",
                src_path,
                dst_path,
                self._direct_auth_label(direct_auth),
                resume_offset,
                self._summarize_command(cmd),
            )
            exit_code, std_out, std_err = self._exec_remote_command_with_progress(
                src_engine,
                dst_engine,
                cmd,
                dst_path,
                total,
                callback=callback,
                check_interrupt=check_interrupt,
            )
            if exit_code != 0:
                raise SSHFerryError(
                    ErrorCode.TRANSFER_FAILED,
                    self._format_direct_failure("scp_resume", exit_code, std_out, std_err),
                )
            if callback:
                callback(total, total)
        except InterruptedError:
            self.logger.info(
                "remote_direct_resume_interrupted src=%s dst=%s auth=%s reason=interrupted",
                src_path,
                dst_path,
                self._direct_auth_label(direct_auth),
            )
            raise
        finally:
            dst_engine.disconnect()
            src_engine.disconnect()

    def _transfer_dir_direct(
        self,
        src_dir: str,
        dst_dir: str,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> None:
        direct_reason = self._direct_unavailable_reason()
        if direct_reason:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, f"Direct remote copy unavailable: {direct_reason}")
        src_engine = SftpEngine(self.src_site, self.logger)
        dst_engine = SftpEngine(self.dst_site, self.logger)
        direct_auth: dict[str, str] | None = None
        try:
            src_engine.connect()
            dst_engine.connect()
            total = self._remote_dir_size(src_engine, src_dir)
            try:
                dst_engine.mkdir(dst_dir)
            except SSHFerryError:
                pass
            if callback:
                callback(0, total)
            if check_interrupt and check_interrupt():
                raise InterruptedError("Task interrupted")
            direct_auth = self._prepare_direct_auth(src_engine, dst_engine)
            self._probe_direct_connectivity(src_engine, dst_dir, direct_auth=direct_auth)
            cmd = self._build_direct_scp_command(src_dir, dst_dir, recursive=True, direct_auth=direct_auth)
            self.logger.info(
                "remote_direct_exec phase=scp_dir src=%s dst=%s auth=%s command=%s",
                src_dir,
                dst_dir,
                self._direct_auth_label(direct_auth),
                self._summarize_command(cmd),
            )
            exit_code, std_out, std_err = self._exec_remote_command_with_directory_progress(
                src_engine,
                dst_engine,
                cmd,
                dst_dir,
                total,
                callback=callback,
                check_interrupt=check_interrupt,
            )
            if exit_code != 0:
                raise SSHFerryError(
                    ErrorCode.TRANSFER_FAILED,
                    self._format_direct_failure("scp_dir", exit_code, std_out, std_err),
                )
            if callback:
                callback(total, total)
        except InterruptedError:
            self.logger.info(
                "remote_direct_dir_interrupted src=%s dst=%s auth=%s reason=interrupted",
                src_dir,
                dst_dir,
                self._direct_auth_label(direct_auth),
            )
            raise
        finally:
            dst_engine.disconnect()
            src_engine.disconnect()

    def _transfer_file_relay(
        self,
        src_path: str,
        dst_path: str,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
        total: int | None = None,
        offset: int = 0,
    ) -> None:
        src_engine = SftpEngine(self.src_site, self.logger)
        dst_engine = SftpEngine(self.dst_site, self.logger)
        try:
            src_engine.connect()
            dst_engine.connect()
            total = total if total is not None else src_engine.stat(src_path).size
            self._stream_file_between_engines(
                src_engine,
                dst_engine,
                src_path,
                dst_path,
                total,
                callback=callback,
                check_interrupt=check_interrupt,
                offset=offset,
            )
        finally:
            dst_engine.disconnect()
            src_engine.disconnect()

    def _transfer_dir_relay(
        self,
        src_dir: str,
        dst_dir: str,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
        item_callback: Optional[Callable[[str, str, int], None]] = None,
    ) -> int:
        src_engine = SftpEngine(self.src_site, self.logger)
        dst_engine = SftpEngine(self.dst_site, self.logger)
        try:
            src_engine.connect()
            dst_engine.connect()
            total = self._remote_dir_size(src_engine, src_dir)
            if callback:
                callback(0, total)
            return self._stream_dir_between_engines(
                src_engine,
                dst_engine,
                src_dir,
                dst_dir,
                total,
                callback,
                check_interrupt,
                item_callback,
            )
        finally:
            dst_engine.disconnect()
            src_engine.disconnect()

    def _stream_dir_between_engines(
        self,
        src_engine: SftpEngine,
        dst_engine: SftpEngine,
        src_dir: str,
        dst_dir: str,
        total: int,
        callback: Optional[Callable[[int, int], None]],
        check_interrupt: Optional[Callable[[], bool]],
        item_callback: Optional[Callable[[str, str, int], None]] = None,
    ) -> int:
        items: list[tuple[str, str, bool, int]] = []

        def walk(current_src: str, current_dst: str) -> None:
            for entry in src_engine.list_dir(current_src):
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Task interrupted")
                target_path = f"{current_dst.rstrip('/')}/{entry.name}"
                if entry.is_dir:
                    items.append((entry.path, target_path, True, 0))
                    walk(entry.path, target_path)
                else:
                    items.append((entry.path, target_path, False, entry.size))

        walk(src_dir, dst_dir)

        for directory in [dst_dir, *[item[1] for item in items if item[2]]]:
            try:
                dst_engine.mkdir(directory)
            except SSHFerryError:
                pass

        files = [item for item in items if not item[2]]
        queue: Queue[tuple[str, str, int]] = Queue()
        for src_path, dst_path, _is_dir, size in files:
            queue.put((src_path, dst_path, size))

        bytes_done = 0
        transferred: dict[str, int] = {}
        progress_lock = threading.Lock()
        stop_state = {"triggered": False}
        first_error: list[Exception] = []
        parallel_slots = {"active": 0}
        parallel_lock = threading.Lock()

        def add_progress(file_key: str, absolute_done: int) -> None:
            nonlocal bytes_done
            with progress_lock:
                previous = transferred.get(file_key, 0)
                delta = max(0, absolute_done - previous)
                transferred[file_key] = absolute_done
                bytes_done = min(total, bytes_done + delta)
                if callback:
                    callback(bytes_done, total)

        def acquire_parallel_slot() -> None:
            while True:
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Task interrupted")
                with parallel_lock:
                    if parallel_slots["active"] < self.folder_parallel_file_slots:
                        parallel_slots["active"] += 1
                        return
                threading.Event().wait(0.02)

        def release_parallel_slot() -> None:
            with parallel_lock:
                parallel_slots["active"] = max(0, parallel_slots["active"] - 1)

        def worker() -> None:
            while not stop_state["triggered"]:
                try:
                    src_path, dst_path, size = queue.get(timeout=0.1)
                except Empty:
                    if queue.empty():
                        break
                    continue
                try:
                    if check_interrupt and check_interrupt():
                        stop_state["triggered"] = True
                        return
                    if size >= self.parallel_threshold:
                        if item_callback:
                            item_callback("start", os.path.basename(src_path), 1)
                        acquire_parallel_slot()
                        try:
                            self._transfer_file_parallel_bridge(
                                src_path,
                                dst_path,
                                size,
                                callback=lambda done, _total, key=src_path: add_progress(key, done),
                                check_interrupt=check_interrupt,
                            )
                        finally:
                            release_parallel_slot()
                        if item_callback:
                            item_callback("complete", os.path.basename(src_path), 1)
                    else:
                        if item_callback:
                            item_callback("start", os.path.basename(src_path), 1)
                        worker_src = SftpEngine(self.src_site, self.logger)
                        worker_dst = SftpEngine(self.dst_site, self.logger)
                        try:
                            worker_src.connect()
                            worker_dst.connect()
                            self._stream_file_between_engines(
                                worker_src,
                                worker_dst,
                                src_path,
                                dst_path,
                                size,
                                callback=lambda done, _total, key=src_path: add_progress(key, done),
                                check_interrupt=check_interrupt,
                            )
                        finally:
                            worker_dst.disconnect()
                            worker_src.disconnect()
                        if item_callback:
                            item_callback("complete", os.path.basename(src_path), 1)
                    add_progress(src_path, size)
                except Exception as exc:
                    if not first_error:
                        first_error.append(exc)
                    stop_state["triggered"] = True
                    return
                finally:
                    queue.task_done()

        worker_count = max(1, min(self.folder_file_workers, max(1, len(files))))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(worker) for _ in range(worker_count)]
            wait(futures)

        if first_error:
            raise first_error[0]
        return bytes_done

    def _transfer_dir_mixed(
        self,
        src_dir: str,
        dst_dir: str,
        dir_plan: dict[str, object],
        *,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
        item_callback: Optional[Callable[[str, str, int], None]] = None,
    ) -> int:
        try:
            total = int(dir_plan["total_bytes"])
            large_files: list[dict[str, object]] = list(dir_plan["large_files"])
            small_batches: list[dict[str, object]] = list(dir_plan["small_batches"])
            directories: list[str] = list(dir_plan["directories"])

            self._ensure_remote_directories_for_plan(dst_dir, directories)
            if small_batches:
                self._warm_cached_direct_auth()
                self._probe_direct_bundle_support(dst_dir)

            if callback:
                callback(0, total)

            transferred: dict[str, int] = {}
            progress_lock = threading.Lock()
            stop_state = {"triggered": False}
            first_error: list[Exception] = []
            large_slots = threading.Semaphore(self.folder_large_file_workers)
            bundle_slots = threading.Semaphore(self.folder_bundle_workers)

            def add_progress(work_key: str, absolute_done: int) -> None:
                with progress_lock:
                    previous = transferred.get(work_key, 0)
                    delta = max(0, absolute_done - previous)
                    transferred[work_key] = absolute_done
                    current_done = min(total, sum(transferred.values()))
                if callback:
                    callback(current_done, total)

            def run_large_file(file_plan: dict[str, object]) -> None:
                work_key = str(file_plan["src"])
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Task interrupted")
                with large_slots:
                    if item_callback:
                        item_callback("start", os.path.basename(str(file_plan["src"])), 1)
                    self.logger.info(
                        "remote_dir_mode mode=dir_large_file src=%s dst=%s bytes=%s",
                        file_plan["src"],
                        file_plan["dst"],
                        file_plan["size"],
                    )
                    self.transfer_file(
                        str(file_plan["src"]),
                        str(file_plan["dst"]),
                        callback=lambda done, _total, key=work_key: add_progress(key, done),
                        check_interrupt=check_interrupt,
                        cleanup_cached_auth=False,
                    )
                    add_progress(work_key, int(file_plan["size"]))
                    if item_callback:
                        item_callback("complete", os.path.basename(str(file_plan["src"])), 1)

            def run_small_bundle(batch_plan: dict[str, object]) -> None:
                work_key = str(batch_plan["bundle_id"])
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Task interrupted")
                with bundle_slots:
                    bundle_label = f"{len(batch_plan['files'])} files"
                    if item_callback:
                        item_callback("start", bundle_label, 0)
                    self.logger.info(
                        "remote_dir_mode mode=dir_small_bundle src=%s dst=%s files=%s bytes=%s bundle=%s",
                        src_dir,
                        dst_dir,
                        len(batch_plan["files"]),
                        batch_plan["total_bytes"],
                        batch_plan["bundle_id"],
                    )
                    self._transfer_small_file_bundle(
                        src_dir,
                        dst_dir,
                        batch_plan["files"],
                        bundle_id=work_key,
                        progress_callback=lambda done, _total, key=work_key: add_progress(key, done),
                        check_interrupt=check_interrupt,
                    )
                    add_progress(work_key, int(batch_plan["total_bytes"]))
                    if item_callback:
                        item_callback("complete", bundle_label, len(batch_plan["files"]))

            def worker(job: tuple[str, dict[str, object]]) -> None:
                if stop_state["triggered"]:
                    return
                try:
                    job_type, payload = job
                    if job_type == "large":
                        run_large_file(payload)
                    else:
                        run_small_bundle(payload)
                except Exception as exc:
                    if not first_error:
                        first_error.append(exc)
                    stop_state["triggered"] = True
                    raise

            jobs: list[tuple[str, dict[str, object]]] = [("large", item) for item in large_files]
            jobs.extend(("bundle", item) for item in small_batches)
            if not jobs:
                return 0

            worker_count = max(
                1,
                min(len(jobs), self.folder_large_file_workers + self.folder_bundle_workers),
            )
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = [executor.submit(worker, job) for job in jobs]
                wait(futures)

            if first_error:
                error = first_error[0]
                if isinstance(error, InterruptedError):
                    raise error
                if isinstance(error, SSHFerryError):
                    raise error
                raise SSHFerryError(ErrorCode.TRANSFER_FAILED, str(error))
            return sum(transferred.values())
        finally:
            self._cleanup_cached_direct_auth()

    def _stream_file_between_engines(
        self,
        src_engine: SftpEngine,
        dst_engine: SftpEngine,
        src_path: str,
        dst_path: str,
        total: int,
        callback: Optional[Callable[[int, int], None]],
        check_interrupt: Optional[Callable[[], bool]],
        offset: int = 0,
    ) -> None:
        chunk_size = 4 * 1024 * 1024
        bytes_done = max(0, min(offset, total))
        with src_engine.sftp_client.open(src_path, "rb") as src_file:
            if offset:
                src_file.seek(offset)
            dst_mode = "wb"
            if offset > 0:
                dst_mode = "r+b"
            with dst_engine.sftp_client.open(dst_path, dst_mode) as dst_file:
                if hasattr(dst_file, "set_pipelined"):
                    dst_file.set_pipelined(True)
                if offset > 0:
                    dst_file.seek(offset)
                if callback and offset > 0:
                    callback(bytes_done, total)
                while True:
                    if check_interrupt and check_interrupt():
                        raise InterruptedError("Task interrupted")
                    chunk = src_file.read(chunk_size)
                    if not chunk:
                        break
                    dst_file.write(chunk)
                    bytes_done += len(chunk)
                    if callback:
                        callback(min(total, bytes_done), total)

    def _transfer_file_dualpath(
        self,
        src_path: str,
        dst_path: str,
        total: int,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> None:
        chunk_size = self.dualpath_chunk_size
        chunk_count = max(1, math.ceil(total / chunk_size))
        dst_dir = self._remote_parent_dir(dst_path)
        dst_name = os.path.basename(dst_path.rstrip("/")) or "file"
        transfer_id = f"{int(time.time() * 1000)}-{threading.get_ident()}"
        part_dir = normalize_remote_path(f"{dst_dir.rstrip('/')}/.sshferry-dualpath-{dst_name}-{transfer_id}")
        tmp_path = normalize_remote_path(f"{dst_path}.sshferry.tmp.{transfer_id}")
        chunks = [
            {
                "index": index,
                "offset": index * chunk_size,
                "length": min(chunk_size, total - index * chunk_size),
                "status": "pending",
                "attempts": 0,
                "leases": set(),
                "winner": None,
            }
            for index in range(chunk_count)
        ]
        lane_stats = {
            "direct": {"avg_rate": 0.0, "current_chunk": None, "current_started": 0.0, "current_bytes": 0},
            "relay": {"avg_rate": 0.0, "current_chunk": None, "current_started": 0.0, "current_bytes": 0},
        }
        lane_alive = {"direct": True, "relay": True}
        winner_paths: dict[int, str] = {}
        created_paths: set[str] = set()
        bytes_done = 0
        duplicate_chunks = 0
        last_reported = 0
        lock = threading.Lock()
        stop_event = threading.Event()
        first_error: list[Exception] = []

        setup_engine = SftpEngine(self.dst_site, self.logger)
        try:
            setup_engine.connect()
            try:
                setup_engine.mkdir(part_dir)
            except SSHFerryError:
                pass
        finally:
            setup_engine.disconnect()

        def log_lane(message: str, *args) -> None:
            self.logger.info("dualpath " + message, *args)

        def chunk_part_path(index: int, lane: str) -> str:
            return normalize_remote_path(f"{part_dir}/{index:08d}.{lane}.part")

        def estimate_progress_locked() -> int:
            in_flight: dict[int, int] = {}
            for lane_name in ("direct", "relay"):
                stats = lane_stats[lane_name]
                chunk_index = stats["current_chunk"]
                if chunk_index is None:
                    continue
                chunk = chunks[chunk_index]
                if chunk["status"] == "done":
                    continue
                in_flight[chunk_index] = max(in_flight.get(chunk_index, 0), stats["current_bytes"])
            return min(total, bytes_done + sum(in_flight.values()))

        def report_progress(force: bool = False) -> None:
            nonlocal last_reported
            if not callback:
                return
            with lock:
                estimate = estimate_progress_locked()
                if not force and estimate - last_reported < self.dualpath_report_granularity and estimate != total:
                    return
                last_reported = estimate
            callback(estimate, total)

        def update_lane_progress(lane: str, index: int, transferred: int) -> None:
            with lock:
                stats = lane_stats[lane]
                if stats["current_chunk"] != index:
                    return
                stats["current_bytes"] = max(stats["current_bytes"], transferred)
            report_progress()

        def mark_chunk_done(index: int, lane: str, part_path: str) -> None:
            nonlocal bytes_done, duplicate_chunks
            report_now = None
            with lock:
                chunk = chunks[index]
                if lane not in chunk["leases"]:
                    return
                chunk["leases"].discard(lane)
                stats = lane_stats[lane]
                elapsed = max(0.001, time.time() - stats["current_started"])
                stats["avg_rate"] = chunk["length"] / elapsed
                stats["current_chunk"] = None
                stats["current_started"] = 0.0
                stats["current_bytes"] = 0
                if chunk["status"] == "done":
                    if not chunk["leases"] and duplicate_chunks > 0:
                        duplicate_chunks -= 1
                    return
                chunk["status"] = "done"
                chunk["winner"] = lane
                winner_paths[index] = part_path
                created_paths.add(part_path)
                bytes_done += chunk["length"]
                report_now = min(total, bytes_done)
                if chunk["leases"] and duplicate_chunks > 0:
                    duplicate_chunks -= 1
            log_lane(
                "chunk_done lane=%s index=%s bytes=%s lane_rate=%.2fMBps direct_avg=%.2fMBps relay_avg=%.2fMBps",
                lane,
                index,
                chunks[index]["length"],
                lane_stats[lane]["avg_rate"] / (1024 * 1024),
                lane_stats["direct"]["avg_rate"] / (1024 * 1024),
                lane_stats["relay"]["avg_rate"] / (1024 * 1024),
            )
            if report_now is not None:
                report_progress(force=True)

        def mark_chunk_failed(index: int, lane: str, exc: Exception) -> None:
            nonlocal duplicate_chunks
            with lock:
                chunk = chunks[index]
                if lane in chunk["leases"]:
                    chunk["leases"].discard(lane)
                stats = lane_stats[lane]
                stats["current_chunk"] = None
                stats["current_started"] = 0.0
                stats["current_bytes"] = 0
                if chunk["status"] == "done":
                    if duplicate_chunks > 0 and not chunk["leases"]:
                        duplicate_chunks -= 1
                    return
                chunk["attempts"] += 1
                if chunk["attempts"] > 4:
                    first_error.append(exc)
                    stop_event.set()
                    return
                if duplicate_chunks > 0 and not chunk["leases"]:
                    duplicate_chunks -= 1
                if not chunk["leases"]:
                    chunk["status"] = "pending"
            self.logger.warning("dualpath chunk_failed lane=%s index=%s error=%s", lane, index, exc)

        def lease_next_chunk(lane: str) -> tuple[dict, bool] | tuple[None, None]:
            nonlocal duplicate_chunks
            other_lane = "relay" if lane == "direct" else "direct"
            while not stop_event.is_set():
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Task interrupted")
                with lock:
                    for chunk in chunks:
                        if chunk["status"] == "pending":
                            chunk["status"] = "inflight"
                            chunk["leases"].add(lane)
                            lane_stats[lane]["current_chunk"] = chunk["index"]
                            lane_stats[lane]["current_started"] = time.time()
                            lane_stats[lane]["current_bytes"] = 0
                            return chunk, False
                    if all(chunk["status"] == "done" for chunk in chunks):
                        return None, None
                    if (
                        duplicate_chunks < self.dualpath_max_dup_chunks
                        and lane_alive.get(other_lane, False)
                        and lane_stats[lane]["avg_rate"] > 0
                    ):
                        for chunk in chunks:
                            if chunk["status"] != "inflight" or lane in chunk["leases"] or len(chunk["leases"]) != 1:
                                continue
                            holder = next(iter(chunk["leases"]))
                            holder_stats = lane_stats[holder]
                            if holder_stats["current_chunk"] != chunk["index"]:
                                continue
                            elapsed = time.time() - holder_stats["current_started"]
                            if elapsed < self.dualpath_min_sample_seconds:
                                continue
                            holder_rate = holder_stats["current_bytes"] / max(elapsed, 0.001)
                            if holder_rate <= 0:
                                continue
                            if lane_stats[lane]["avg_rate"] <= holder_rate * self.dualpath_slow_factor:
                                continue
                            chunk["leases"].add(lane)
                            duplicate_chunks += 1
                            lane_stats[lane]["current_chunk"] = chunk["index"]
                            lane_stats[lane]["current_started"] = time.time()
                            lane_stats[lane]["current_bytes"] = 0
                            self.logger.info(
                                "dualpath chunk_duplicate chunk=%s holder=%s challenger=%s holder_rate=%.2f challenger_rate=%.2f",
                                chunk["index"],
                                holder,
                                lane,
                                holder_rate,
                                lane_stats[lane]["avg_rate"],
                            )
                            return chunk, True
                time.sleep(0.05)
            return None, None

        def direct_lane() -> None:
            try:
                src_engine = SftpEngine(self.src_site, self.logger)
                dst_engine = SftpEngine(self.dst_site, self.logger)
                src_engine.connect()
                dst_engine.connect()
                try:
                    while not stop_event.is_set():
                        chunk, _duplicate = lease_next_chunk("direct")
                        if chunk is None:
                            break
                        part_path = chunk_part_path(chunk["index"], "direct")
                        created_paths.add(part_path)
                        try:
                            self._stream_chunk_via_direct_lane(
                                src_engine,
                                dst_engine,
                                src_path,
                                part_path,
                                chunk["index"],
                                chunk["length"],
                                progress=lambda transferred, idx=chunk["index"]: update_lane_progress("direct", idx, transferred),
                                check_interrupt=check_interrupt,
                            )
                            mark_chunk_done(chunk["index"], "direct", part_path)
                        except Exception as exc:
                            mark_chunk_failed(chunk["index"], "direct", exc)
                            if stop_event.is_set():
                                break
                finally:
                    dst_engine.disconnect()
                    src_engine.disconnect()
            except Exception as exc:
                lane_alive["direct"] = False
                self.logger.warning("dualpath lane_down lane=direct error=%s", exc)
                if not lane_alive["relay"]:
                    first_error.append(exc)
                    stop_event.set()

        def relay_lane() -> None:
            try:
                if self.dualpath_initial_lanes < 2 and self.dualpath_lane_ramp_delay_seconds > 0:
                    time.sleep(self.dualpath_lane_ramp_delay_seconds)
                src_engine = SftpEngine(self.src_site, self.logger)
                dst_engine = SftpEngine(self.dst_site, self.logger)
                src_engine.connect()
                dst_engine.connect()
                try:
                    while not stop_event.is_set():
                        chunk, _duplicate = lease_next_chunk("relay")
                        if chunk is None:
                            break
                        part_path = chunk_part_path(chunk["index"], "relay")
                        created_paths.add(part_path)
                        try:
                            self._stream_chunk_via_relay_lane(
                                src_engine,
                                dst_engine,
                                src_path,
                                part_path,
                                chunk["offset"],
                                chunk["length"],
                                progress=lambda transferred, idx=chunk["index"]: update_lane_progress("relay", idx, transferred),
                                check_interrupt=check_interrupt,
                            )
                            mark_chunk_done(chunk["index"], "relay", part_path)
                        except Exception as exc:
                            mark_chunk_failed(chunk["index"], "relay", exc)
                            if stop_event.is_set():
                                break
                finally:
                    dst_engine.disconnect()
                    src_engine.disconnect()
            except Exception as exc:
                lane_alive["relay"] = False
                self.logger.warning("dualpath lane_down lane=relay error=%s", exc)
                if not lane_alive["direct"]:
                    first_error.append(exc)
                    stop_event.set()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(direct_lane), executor.submit(relay_lane)]
            wait(futures)

        if check_interrupt and check_interrupt():
            raise InterruptedError("Task interrupted")
        if stop_event.is_set() and first_error:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, f"Dual-path transfer failed: {first_error[0]}")
        if len(winner_paths) != chunk_count:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, "Dual-path transfer incomplete")

        merge_engine = SftpEngine(self.dst_site, self.logger)
        try:
            merge_engine.connect()
            self._merge_remote_parts(merge_engine, winner_paths, tmp_path, dst_path)
        finally:
            merge_engine.disconnect()
        self._cleanup_remote_parts(created_paths, part_dir, tmp_path)
        report_progress(force=True)

    def _stream_chunk_via_direct_lane(
        self,
        src_engine: SftpEngine,
        dst_engine: SftpEngine,
        src_path: str,
        dst_part_path: str,
        chunk_index: int,
        expected_length: int,
        *,
        progress: Optional[Callable[[int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> None:
        cmd = (
            f"dd if={self._shell_quote(src_path)} "
            f"bs={self.dualpath_chunk_size} skip={chunk_index} count=1 status=none"
        )
        _stdin, stdout, stderr = src_engine.ssh_client.exec_command(cmd)
        transferred = 0
        with dst_engine.sftp_client.open(dst_part_path, "wb") as dst_file:
            if hasattr(dst_file, "set_pipelined"):
                dst_file.set_pipelined(True)
            while transferred < expected_length:
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Task interrupted")
                chunk = stdout.read(min(1024 * 1024, expected_length - transferred))
                if not chunk:
                    break
                dst_file.write(chunk)
                transferred += len(chunk)
                if progress:
                    progress(transferred)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            err = stderr.read().decode("utf-8", errors="replace").strip() or "direct chunk stream failed"
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, err)
        if transferred != expected_length:
            raise SSHFerryError(
                ErrorCode.TRANSFER_FAILED,
                f"Direct chunk incomplete: expected {expected_length}, got {transferred}",
            )

    def _stream_chunk_via_relay_lane(
        self,
        src_engine: SftpEngine,
        dst_engine: SftpEngine,
        src_path: str,
        dst_part_path: str,
        offset: int,
        expected_length: int,
        *,
        progress: Optional[Callable[[int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> None:
        remaining = expected_length
        transferred = 0
        with src_engine.sftp_client.open(src_path, "rb") as src_file:
            src_file.seek(offset)
            with dst_engine.sftp_client.open(dst_part_path, "wb") as dst_file:
                if hasattr(dst_file, "set_pipelined"):
                    dst_file.set_pipelined(True)
                while remaining > 0:
                    if check_interrupt and check_interrupt():
                        raise InterruptedError("Task interrupted")
                    data = src_file.read(min(4 * 1024 * 1024, remaining))
                    if not data:
                        break
                    dst_file.write(data)
                    transferred += len(data)
                    remaining -= len(data)
                    if progress:
                        progress(transferred)
        if transferred != expected_length:
            raise SSHFerryError(
                ErrorCode.TRANSFER_FAILED,
                f"Relay chunk incomplete: expected {expected_length}, got {transferred}",
            )

    def _merge_remote_parts(
        self,
        dst_engine: SftpEngine,
        winner_paths: dict[int, str],
        tmp_path: str,
        final_path: str,
    ) -> None:
        with dst_engine.sftp_client.open(tmp_path, "wb") as merged:
            if hasattr(merged, "set_pipelined"):
                merged.set_pipelined(True)
            for index in sorted(winner_paths):
                with dst_engine.sftp_client.open(winner_paths[index], "rb") as part_file:
                    while True:
                        data = part_file.read(4 * 1024 * 1024)
                        if not data:
                            break
                        merged.write(data)
        try:
            dst_engine.remove_file(final_path)
        except Exception:
            pass
        dst_engine.rename(tmp_path, final_path)

    def _cleanup_remote_parts(self, created_paths: set[str], part_dir: str, tmp_path: str) -> None:
        cleanup_engine = SftpEngine(self.dst_site, self.logger)
        try:
            cleanup_engine.connect()
            for path in sorted(created_paths):
                try:
                    cleanup_engine.remove_file(path)
                except Exception:
                    pass
            try:
                cleanup_engine.remove_file(tmp_path)
            except Exception:
                pass
            try:
                cleanup_engine.remove_dir(part_dir)
            except Exception:
                pass
        finally:
            cleanup_engine.disconnect()

    @staticmethod
    def _remote_parent_dir(remote_path: str) -> str:
        normalized = normalize_remote_path(remote_path)
        if normalized == "/":
            return "/"
        parent = normalized.rsplit("/", 1)[0]
        return parent or "/"

    def _transfer_file_parallel_bridge(
        self,
        src_path: str,
        dst_path: str,
        total: int,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> None:
        settings = self._parallel_bridge_settings()
        worker_count = max(1, min(settings["workers"], math.ceil(total / settings["chunk_size"])))
        chunk_size = settings["chunk_size"]
        queue: Queue[tuple[int, int]] = Queue()
        for index in range(math.ceil(total / chunk_size)):
            offset = index * chunk_size
            length = min(chunk_size, total - offset)
            queue.put((offset, length))

        bytes_done = 0
        completed_chunks = 0
        interrupt_event = threading.Event()
        lock = threading.Lock()
        last_error: list[str] = []
        retry_counts: dict[int, int] = {}
        max_retries = 4

        init_dst = SftpEngine(self.dst_site, self.logger)
        init_dst.connect()
        try:
            with init_dst.sftp_client.open(dst_path, "wb") as dst_file:
                if hasattr(dst_file, "set_pipelined"):
                    dst_file.set_pipelined(True)
                try:
                    dst_file.truncate(total)
                except Exception:
                    pass
        finally:
            init_dst.disconnect()

        def worker() -> None:
            src_engine = SftpEngine(self.src_site, self.logger)
            dst_engine = SftpEngine(self.dst_site, self.logger)
            try:
                src_engine.connect()
                dst_engine.connect()
                with src_engine.sftp_client.open(src_path, "rb") as src_file:
                    with dst_engine.sftp_client.open(dst_path, "r+b") as dst_file:
                        if hasattr(dst_file, "set_pipelined"):
                            dst_file.set_pipelined(True)
                        while not interrupt_event.is_set():
                            try:
                                offset, length = queue.get(timeout=0.3)
                            except Empty:
                                if queue.empty():
                                    break
                                continue
                            try:
                                if check_interrupt and check_interrupt():
                                    interrupt_event.set()
                                    return
                                src_file.seek(offset)
                                data = src_file.read(length)
                                if len(data) != length:
                                    raise IOError(
                                        f"Remote chunk read size mismatch at offset {offset}: expected {length}, got {len(data)}"
                                    )
                                dst_file.seek(offset)
                                dst_file.write(data)
                                with lock:
                                    nonlocal bytes_done, completed_chunks
                                    bytes_done += len(data)
                                    completed_chunks += 1
                                    current_done = bytes_done
                                if callback:
                                    callback(min(total, current_done), total)
                            except Exception as exc:
                                should_abort = False
                                with lock:
                                    retry = retry_counts.get(offset, 0) + 1
                                    retry_counts[offset] = retry
                                    if retry > max_retries:
                                        should_abort = True
                                        last_error[:] = [str(exc)]
                                if should_abort:
                                    interrupt_event.set()
                                    return
                                queue.put((offset, length))
                            finally:
                                queue.task_done()
            finally:
                dst_engine.disconnect()
                src_engine.disconnect()

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(worker) for _ in range(worker_count)]
            wait(futures)

        if check_interrupt and check_interrupt():
            raise InterruptedError("Task interrupted")
        if interrupt_event.is_set() and last_error:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, f"Parallel bridge failed: {last_error[0]}")
        if bytes_done < total or completed_chunks < math.ceil(total / chunk_size):
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, "Parallel bridge transfer incomplete")

    def _parallel_bridge_settings(self) -> dict[str, int]:
        download_preset = PARALLEL_PRESETS.get(self.relay_download_preset, PARALLEL_PRESETS["high"])
        upload_preset = PARALLEL_PRESETS.get(self.relay_upload_preset, PARALLEL_PRESETS["medium"])
        src_parallel = ParallelSftpEngine(
            self.src_site,
            self.logger,
            max_workers=download_preset.workers,
            chunk_size=download_preset.chunk_size,
        )
        dst_parallel = ParallelSftpEngine(
            self.dst_site,
            self.logger,
            max_workers=upload_preset.workers,
            chunk_size=upload_preset.chunk_size,
        )
        return {
            "workers": min(src_parallel.max_workers, dst_parallel.max_workers),
            "chunk_size": min(src_parallel.chunk_size, dst_parallel.chunk_size),
        }

    def _remote_file_size(self, src_path: str) -> int:
        src_engine = SftpEngine(self.src_site, self.logger)
        try:
            src_engine.connect()
            return src_engine.stat(src_path).size
        finally:
            src_engine.disconnect()

    def _remote_dir_size(self, engine: SftpEngine, remote_dir: str) -> int:
        total = 0
        for entry in engine.list_dir(remote_dir):
            if entry.is_dir:
                total += self._remote_dir_size(engine, entry.path)
            else:
                total += entry.size
        return total

    def _plan_remote_dir_transfer(self, src_dir: str, dst_dir: str) -> dict[str, object]:
        src_engine = SftpEngine(self.src_site, self.logger)
        try:
            src_engine.connect()
            files, directories = self._scan_remote_dir_entries(src_engine, src_dir, dst_dir)
        finally:
            src_engine.disconnect()

        total_bytes = sum(int(item["size"]) for item in files)
        large_files: list[dict[str, object]] = []
        small_files: list[dict[str, object]] = []
        for item in files:
            if int(item["size"]) >= self.parallel_threshold:
                large_files.append(item)
            else:
                small_files.append(item)

        small_batches = self._build_small_file_batches(small_files)
        return {
            "total_bytes": total_bytes,
            "total_files": len(files),
            "directories": directories,
            "large_files": large_files,
            "small_files": small_files,
            "small_batches": small_batches,
        }

    def _scan_remote_dir_entries(
        self,
        src_engine: SftpEngine,
        src_dir: str,
        dst_dir: str,
    ) -> tuple[list[dict[str, object]], list[str]]:
        shell_entries = scan_remote_tree_via_shell(src_engine, src_dir)
        if shell_entries is not None:
            files: list[dict[str, object]] = []
            directories: list[str] = []
            for entry in shell_entries:
                if entry.is_dir:
                    directories.append(entry.rel_path)
                    continue
                files.append(
                    {
                        "src": self._join_remote_path(src_dir, entry.rel_path),
                        "dst": self._join_remote_path(dst_dir, entry.rel_path),
                        "rel_path": entry.rel_path,
                        "size": entry.size,
                    }
                )
            return files, directories

        files: list[dict[str, object]] = []
        directories: list[str] = []
        normalized_root = normalize_remote_path(src_dir).rstrip("/") or "/"
        visited: set[str] = set()

        def walk(current_src: str) -> None:
            canonical_src = self._canonical_remote_walk_path(src_engine, current_src)
            if canonical_src in visited:
                return
            visited.add(canonical_src)
            for entry in src_engine.list_dir(current_src):
                relative_path = self._relative_remote_path(normalized_root, entry.path)
                if entry.is_dir:
                    directories.append(relative_path)
                    walk(entry.path)
                else:
                    files.append(
                        {
                            "src": entry.path,
                            "dst": self._join_remote_path(dst_dir, relative_path),
                            "rel_path": relative_path,
                            "size": int(entry.size),
                        }
                    )

        walk(src_dir)
        return files, directories

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

    def _build_small_file_batches(self, files: list[dict[str, object]]) -> list[dict[str, object]]:
        batches: list[dict[str, object]] = []
        current_files: list[dict[str, object]] = []
        current_bytes = 0
        for item in files:
            item_size = int(item["size"])
            if current_files and (
                current_bytes + item_size > self.dir_bundle_max_bytes
                or len(current_files) >= self.dir_bundle_max_files
            ):
                batch_index = len(batches)
                batches.append(
                    {
                        "bundle_id": f"bundle-{batch_index}",
                        "files": current_files,
                        "total_bytes": current_bytes,
                    }
                )
                current_files = []
                current_bytes = 0
            current_files.append(item)
            current_bytes += item_size
        if current_files:
            batch_index = len(batches)
            batches.append(
                {
                    "bundle_id": f"bundle-{batch_index}",
                    "files": current_files,
                    "total_bytes": current_bytes,
                }
            )
        return batches

    def _should_use_mixed_dir_transfer(self, dir_plan: dict[str, object]) -> bool:
        if not self.dir_bundle_enabled:
            return False
        large_count = len(dir_plan["large_files"])
        small_count = len(dir_plan["small_files"])
        if large_count and small_count:
            return True
        if large_count:
            return True
        return small_count >= self.dir_bundle_file_count_threshold

    def _ensure_remote_directories_for_plan(self, dst_dir: str, relative_directories: list[str]) -> None:
        dst_engine = SftpEngine(self.dst_site, self.logger)
        try:
            dst_engine.connect()
            directories = [dst_dir]
            directories.extend(self._join_remote_path(dst_dir, relative_path) for relative_path in relative_directories if relative_path)
            for directory in sorted(set(directories), key=lambda value: (value.count("/"), value)):
                try:
                    dst_engine.mkdir(directory)
                except SSHFerryError:
                    pass
        finally:
            dst_engine.disconnect()

    def _probe_direct_bundle_support(self, dst_dir: str) -> None:
        if not self._can_attempt_direct_copy():
            raise SSHFerryError(
                ErrorCode.TRANSFER_FAILED,
                f"Direct remote copy unavailable: {self._direct_unavailable_reason()}",
            )
        src_engine = SftpEngine(self.src_site, self.logger)
        dst_engine = SftpEngine(self.dst_site, self.logger)
        direct_auth: dict[str, str] | None = None
        try:
            src_engine.connect()
            dst_engine.connect()
            direct_auth = self._prepare_direct_auth(src_engine, dst_engine)
            self._probe_direct_connectivity(src_engine, dst_dir, direct_auth=direct_auth)
            probe_cmd = self._build_direct_bundle_probe_command(dst_dir, direct_auth=direct_auth)
            self.logger.info(
                "remote_direct_exec phase=bundle_probe dst=%s auth=%s command=%s",
                dst_dir,
                self._direct_auth_label(direct_auth),
                self._summarize_command(probe_cmd),
            )
            exit_code, std_out, std_err = self._exec_remote_command(src_engine, probe_cmd)
            if exit_code != 0 or "SSHFERRY_DIRECT_BUNDLE_OK" not in std_out:
                raise SSHFerryError(
                    ErrorCode.TRANSFER_FAILED,
                    self._format_direct_failure("bundle_probe", exit_code, std_out, std_err),
                )
        finally:
            dst_engine.disconnect()
            src_engine.disconnect()

    def _transfer_small_file_bundle(
        self,
        src_dir: str,
        dst_dir: str,
        files: list[dict[str, object]],
        *,
        bundle_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> None:
        if not files:
            return
        src_engine = SftpEngine(self.src_site, self.logger)
        dst_engine = SftpEngine(self.dst_site, self.logger)
        direct_auth: dict[str, str] | None = None
        temp_dir = self._join_remote_path(
            dst_dir,
            f".sshferry-bundle-{bundle_id}-{int(time.time() * 1000)}-{threading.get_ident()}",
        )
        try:
            src_engine.connect()
            dst_engine.connect()
            if check_interrupt and check_interrupt():
                raise InterruptedError("Task interrupted")
            direct_auth = self._prepare_direct_auth(src_engine, dst_engine)
            command = self._build_direct_bundle_command(
                src_dir,
                dst_dir,
                temp_dir,
                [str(item["rel_path"]) for item in files],
                direct_auth=direct_auth,
            )
            self.logger.info(
                "remote_direct_exec phase=bundle src=%s dst=%s auth=%s bundle=%s files=%s command=%s",
                src_dir,
                dst_dir,
                self._direct_auth_label(direct_auth),
                bundle_id,
                len(files),
                self._summarize_command(command),
            )
            total_bytes = sum(int(item["size"]) for item in files)
            exit_code, std_out, std_err = self._exec_remote_command_with_directory_progress(
                src_engine,
                dst_engine,
                command,
                temp_dir,
                total_bytes,
                callback=progress_callback,
                check_interrupt=check_interrupt,
            )
            if exit_code != 0 or "SSHFERRY_BUNDLE_OK" not in std_out:
                raise SSHFerryError(
                    ErrorCode.TRANSFER_FAILED,
                    self._format_direct_failure("bundle", exit_code, std_out, std_err),
                )
            self.logger.info(
                "remote_dir_mode mode=dir_bundle_extract dst=%s bundle=%s files=%s",
                dst_dir,
                bundle_id,
                len(files),
            )
        finally:
            try:
                self._cleanup_remote_temp_dir(dst_engine, temp_dir)
            except Exception:
                pass
            dst_engine.disconnect()
            src_engine.disconnect()

    def _cleanup_remote_temp_dir(self, dst_engine: SftpEngine, temp_dir: str) -> None:
        if not getattr(dst_engine, "ssh_client", None):
            return
        cleanup_cmd = f"sh -lc 'rm -rf -- {self._shell_quote(temp_dir)}'"
        try:
            self._exec_remote_command(dst_engine, cleanup_cmd)
        except Exception:
            pass

    @staticmethod
    def _shell_quote(text: str) -> str:
        return "'" + text.replace("'", "'\"'\"'") + "'"

    @staticmethod
    def _relative_remote_path(root_path: str, child_path: str) -> str:
        normalized_root = normalize_remote_path(root_path).rstrip("/")
        normalized_child = normalize_remote_path(child_path)
        prefix = f"{normalized_root}/" if normalized_root else "/"
        if normalized_child.startswith(prefix):
            return normalized_child[len(prefix):]
        if normalized_child == normalized_root:
            return ""
        return normalized_child.lstrip("/")

    @staticmethod
    def _join_remote_path(base_path: str, relative_path: str) -> str:
        normalized_base = normalize_remote_path(base_path)
        if not relative_path:
            return normalized_base
        return normalize_remote_path(f"{normalized_base.rstrip('/')}/{relative_path.lstrip('/')}")

    def _build_direct_ssh_probe_command(
        self,
        remote_path_hint: str,
        *,
        direct_auth: dict[str, str] | None = None,
    ) -> str:
        parent = self._remote_parent_dir(remote_path_hint)
        destination = f"{self.dst_site.username}@{self.dst_site.host}"
        args = ["ssh"]
        args.extend(["-p", str(self.dst_site.port), "-o", "BatchMode=yes"])
        strict_hostkey = os.getenv("SSHFERRY_STRICT_HOSTKEY", "").strip().lower() in ("1", "true", "yes", "on")
        if not strict_hostkey:
            args.extend(["-o", "StrictHostKeyChecking=no"])
        if self.dst_site.proxy_jump:
            args.extend(["-o", f"ProxyJump={self.dst_site.proxy_jump}"])
        remote_ssh_config = self._remote_usable_path(self.dst_site.ssh_config_path)
        if remote_ssh_config:
            args.extend(["-F", remote_ssh_config])
        remote_key_path = self._direct_auth_key_path(direct_auth)
        if remote_key_path:
            args.extend(["-i", remote_key_path])
        for option in self.dst_site.ssh_options:
            normalized = (option or "").strip()
            if not normalized:
                continue
            if normalized.startswith("-o "):
                normalized = normalized[3:].strip()
            elif normalized.startswith("-o") and len(normalized) > 2:
                normalized = normalized[2:].strip()
            args.extend(["-o", normalized])
        probe_cmd = f"sh -lc 'test -d {self._shell_quote(parent)} && printf SSHFERRY_DIRECT_OK'"
        args.extend(["--", destination, probe_cmd])
        quoted_args = " ".join(self._shell_quote(arg) for arg in args)
        return f"command -v ssh >/dev/null 2>&1 && {quoted_args}"

    def _build_direct_bundle_probe_command(
        self,
        remote_path_hint: str,
        *,
        direct_auth: dict[str, str] | None = None,
    ) -> str:
        parent = self._remote_parent_dir(remote_path_hint)
        destination = f"{self.dst_site.username}@{self.dst_site.host}"
        args = ["ssh"]
        args.extend(["-p", str(self.dst_site.port), "-o", "BatchMode=yes"])
        strict_hostkey = os.getenv("SSHFERRY_STRICT_HOSTKEY", "").strip().lower() in ("1", "true", "yes", "on")
        if not strict_hostkey:
            args.extend(["-o", "StrictHostKeyChecking=no"])
        if self.dst_site.proxy_jump:
            args.extend(["-o", f"ProxyJump={self.dst_site.proxy_jump}"])
        remote_ssh_config = self._remote_usable_path(self.dst_site.ssh_config_path)
        if remote_ssh_config:
            args.extend(["-F", remote_ssh_config])
        remote_key_path = self._direct_auth_key_path(direct_auth)
        if remote_key_path:
            args.extend(["-i", remote_key_path])
        for option in self.dst_site.ssh_options:
            normalized = (option or "").strip()
            if not normalized:
                continue
            if normalized.startswith("-o "):
                normalized = normalized[3:].strip()
            elif normalized.startswith("-o") and len(normalized) > 2:
                normalized = normalized[2:].strip()
            args.extend(["-o", normalized])
        probe_cmd = (
            "sh -lc 'command -v tar >/dev/null 2>&1 && "
            f"test -d {self._shell_quote(parent)} && printf SSHFERRY_DIRECT_BUNDLE_OK'"
        )
        args.extend(["--", destination, probe_cmd])
        quoted_args = " ".join(self._shell_quote(arg) for arg in args)
        return f"command -v tar >/dev/null 2>&1 && command -v ssh >/dev/null 2>&1 && {quoted_args}"

    def _build_direct_scp_command(
        self,
        src_path: str,
        dst_path: str,
        recursive: bool = False,
        *,
        direct_auth: dict[str, str] | None = None,
    ) -> str:
        destination = f"{self.dst_site.username}@{self.dst_site.host}:{dst_path}"
        args = ["scp", "-q"]
        if recursive:
            args.append("-r")
        args.extend(["-P", str(self.dst_site.port), "-o", "BatchMode=yes"])
        strict_hostkey = os.getenv("SSHFERRY_STRICT_HOSTKEY", "").strip().lower() in ("1", "true", "yes", "on")
        if not strict_hostkey:
            args.extend(["-o", "StrictHostKeyChecking=no"])
        if self.dst_site.proxy_jump:
            args.extend(["-o", f"ProxyJump={self.dst_site.proxy_jump}"])
        remote_ssh_config = self._remote_usable_path(self.dst_site.ssh_config_path)
        if remote_ssh_config:
            args.extend(["-F", remote_ssh_config])
        remote_key_path = self._direct_auth_key_path(direct_auth)
        if remote_key_path:
            args.extend(["-i", remote_key_path])
        for option in self.dst_site.ssh_options:
            normalized = (option or "").strip()
            if not normalized:
                continue
            if normalized.startswith("-o "):
                normalized = normalized[3:].strip()
            elif normalized.startswith("-o") and len(normalized) > 2:
                normalized = normalized[2:].strip()
            args.extend(["-o", normalized])
        args.extend(["--", src_path, destination])
        quoted_args = " ".join(self._shell_quote(arg) for arg in args)
        return f"command -v scp >/dev/null 2>&1 && {quoted_args}"

    def _build_direct_resume_command(
        self,
        src_path: str,
        dst_path: str,
        resume_offset: int,
        *,
        direct_auth: dict[str, str] | None = None,
    ) -> str:
        destination = f"{self.dst_site.username}@{self.dst_site.host}"
        ssh_args = ["ssh", "-p", str(self.dst_site.port), "-o", "BatchMode=yes"]
        strict_hostkey = os.getenv("SSHFERRY_STRICT_HOSTKEY", "").strip().lower() in ("1", "true", "yes", "on")
        if not strict_hostkey:
            ssh_args.extend(["-o", "StrictHostKeyChecking=no"])
        if self.dst_site.proxy_jump:
            ssh_args.extend(["-o", f"ProxyJump={self.dst_site.proxy_jump}"])
        remote_ssh_config = self._remote_usable_path(self.dst_site.ssh_config_path)
        if remote_ssh_config:
            ssh_args.extend(["-F", remote_ssh_config])
        remote_key_path = self._direct_auth_key_path(direct_auth)
        if remote_key_path:
            ssh_args.extend(["-i", remote_key_path])
        for option in self.dst_site.ssh_options:
            normalized = (option or "").strip()
            if not normalized:
                continue
            if normalized.startswith("-o "):
                normalized = normalized[3:].strip()
            elif normalized.startswith("-o") and len(normalized) > 2:
                normalized = normalized[2:].strip()
            ssh_args.extend(["-o", normalized])
        source_cmd = f"tail -c +$(({resume_offset} + 1)) {self._shell_quote(src_path)}"
        target_cmd = f"sh -lc 'cat >> {self._shell_quote(dst_path)}'"
        ssh_args.extend(["--", destination, target_cmd])
        quoted_ssh = " ".join(self._shell_quote(arg) for arg in ssh_args)
        return f"command -v tail >/dev/null 2>&1 && {source_cmd} | {quoted_ssh}"

    def _build_direct_bundle_command(
        self,
        src_dir: str,
        dst_dir: str,
        temp_dir: str,
        relative_paths: list[str],
        *,
        direct_auth: dict[str, str] | None = None,
    ) -> str:
        destination = f"{self.dst_site.username}@{self.dst_site.host}"
        ssh_args = ["ssh", "-p", str(self.dst_site.port), "-o", "BatchMode=yes"]
        strict_hostkey = os.getenv("SSHFERRY_STRICT_HOSTKEY", "").strip().lower() in ("1", "true", "yes", "on")
        if not strict_hostkey:
            ssh_args.extend(["-o", "StrictHostKeyChecking=no"])
        if self.dst_site.proxy_jump:
            ssh_args.extend(["-o", f"ProxyJump={self.dst_site.proxy_jump}"])
        remote_ssh_config = self._remote_usable_path(self.dst_site.ssh_config_path)
        if remote_ssh_config:
            ssh_args.extend(["-F", remote_ssh_config])
        remote_key_path = self._direct_auth_key_path(direct_auth)
        if remote_key_path:
            ssh_args.extend(["-i", remote_key_path])
        for option in self.dst_site.ssh_options:
            normalized = (option or "").strip()
            if not normalized:
                continue
            if normalized.startswith("-o "):
                normalized = normalized[3:].strip()
            elif normalized.startswith("-o") and len(normalized) > 2:
                normalized = normalized[2:].strip()
            ssh_args.extend(["-o", normalized])
        dst_cmd = (
            "set -e; "
            f"tmp={self._shell_quote(temp_dir)}; "
            f"dst={self._shell_quote(dst_dir)}; "
            "rm -rf -- \"$tmp\"; "
            "mkdir -p \"$tmp\" \"$dst\"; "
            "tar -xf - -C \"$tmp\"; "
            "(cd \"$tmp\" && tar -cf - .) | (cd \"$dst\" && tar -xf -); "
            "rm -rf -- \"$tmp\"; "
            "printf SSHFERRY_BUNDLE_OK"
        )
        ssh_args.extend(["--", destination, f"sh -lc {self._shell_quote(dst_cmd)}"])
        quoted_ssh = " ".join(self._shell_quote(arg) for arg in ssh_args)

        src_args = ["tar", "-cf", "-", "-C", src_dir, "--", *relative_paths]
        quoted_src = " ".join(self._shell_quote(arg) for arg in src_args)
        return f"command -v tar >/dev/null 2>&1 && {quoted_src} | {quoted_ssh}"

    def _probe_direct_connectivity(
        self,
        src_engine: SftpEngine,
        remote_path_hint: str,
        *,
        direct_auth: dict[str, str] | None = None,
    ) -> None:
        probe_cmd = self._build_direct_ssh_probe_command(remote_path_hint, direct_auth=direct_auth)
        self.logger.info(
            "remote_direct_exec phase=probe dst=%s auth=%s command=%s",
            remote_path_hint,
            self._direct_auth_label(direct_auth),
            self._summarize_command(probe_cmd),
        )
        exit_code, std_out, std_err = self._exec_remote_command(src_engine, probe_cmd)
        if exit_code != 0 or "SSHFERRY_DIRECT_OK" not in std_out:
            raise SSHFerryError(
                ErrorCode.TRANSFER_FAILED,
                self._format_direct_failure("probe", exit_code, std_out, std_err),
            )

    def _exec_remote_command(self, src_engine: SftpEngine, command: str) -> tuple[int, str, str]:
        _stdin, stdout, stderr = src_engine.ssh_client.exec_command(command)
        exit_code = stdout.channel.recv_exit_status()
        std_out = stdout.read().decode("utf-8", errors="replace").strip()
        std_err = stderr.read().decode("utf-8", errors="replace").strip()
        return exit_code, std_out, std_err

    def _exec_remote_command_with_progress(
        self,
        src_engine: SftpEngine,
        dst_engine: SftpEngine,
        command: str,
        dst_path: str,
        total: int,
        *,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> tuple[int, str, str]:
        _stdin, stdout, stderr = src_engine.ssh_client.exec_command(command)
        channel = stdout.channel
        last_reported = 0
        while not channel.exit_status_ready():
            if check_interrupt and check_interrupt():
                try:
                    channel.close()
                except Exception:
                    pass
                raise InterruptedError("Task interrupted")
            if callback:
                try:
                    remote_size = max(0, min(total, dst_engine.stat(dst_path).size))
                except Exception:
                    remote_size = last_reported
                if remote_size > last_reported:
                    last_reported = remote_size
                    callback(remote_size, total)
            time.sleep(self.direct_progress_poll_interval_seconds)
        exit_code = channel.recv_exit_status()
        std_out = stdout.read().decode("utf-8", errors="replace").strip()
        std_err = stderr.read().decode("utf-8", errors="replace").strip()
        if callback and exit_code == 0 and last_reported < total:
            callback(total, total)
        return exit_code, std_out, std_err

    def _exec_remote_command_with_directory_progress(
        self,
        src_engine: SftpEngine,
        dst_engine: SftpEngine,
        command: str,
        dst_dir: str,
        total: int,
        *,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> tuple[int, str, str]:
        _stdin, stdout, stderr = src_engine.ssh_client.exec_command(command)
        channel = stdout.channel
        last_reported = 0
        while not channel.exit_status_ready():
            if check_interrupt and check_interrupt():
                try:
                    channel.close()
                except Exception:
                    pass
                raise InterruptedError("Task interrupted")
            if callback:
                try:
                    remote_size = max(0, min(total, self._remote_dir_size(dst_engine, dst_dir)))
                except Exception:
                    remote_size = last_reported
                if remote_size > last_reported:
                    last_reported = remote_size
                    callback(remote_size, total)
            time.sleep(self.direct_progress_poll_interval_seconds)
        exit_code = channel.recv_exit_status()
        std_out = stdout.read().decode("utf-8", errors="replace").strip()
        std_err = stderr.read().decode("utf-8", errors="replace").strip()
        if callback and exit_code == 0 and last_reported < total:
            callback(total, total)
        return exit_code, std_out, std_err

    def _format_direct_failure(self, phase: str, exit_code: int, std_out: str, std_err: str) -> str:
        parts = [f"direct {phase} failed", f"exit={exit_code}"]
        err_tail = self._trim_remote_output(std_err)
        out_tail = self._trim_remote_output(std_out)
        if err_tail:
            parts.append(f"stderr={err_tail}")
        if out_tail:
            parts.append(f"stdout={out_tail}")
        return " ".join(parts)

    @staticmethod
    def _trim_remote_output(output: str, max_chars: int = 240) -> str:
        normalized = " ".join((output or "").split())
        if len(normalized) <= max_chars:
            return normalized
        return "..." + normalized[-max_chars:]

    @staticmethod
    def _summarize_command(command: str, max_chars: int = 260) -> str:
        compact = " ".join(command.split())
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 3] + "..."

    def _prepare_direct_auth(
        self,
        src_engine: SftpEngine,
        dst_engine: SftpEngine,
        *,
        reuse_cached: bool = True,
    ) -> dict[str, str] | None:
        with self._direct_auth_lock:
            if reuse_cached and self._cached_direct_auth is not None:
                return self._cached_direct_auth
            remote_key_path = self._remote_usable_path(self.dst_site.key_path)
            if remote_key_path:
                direct_auth = {"mode": "site_key", "key_path": remote_key_path}
                if reuse_cached:
                    self._cached_direct_auth = direct_auth
                    self._cached_direct_auth_mode = "site_key"
                return direct_auth
            if not self.direct_ephemeral_key_enabled:
                return None
            direct_auth = self._bootstrap_ephemeral_direct_key(src_engine, dst_engine)
            if reuse_cached:
                self._cached_direct_auth = direct_auth
                self._cached_direct_auth_mode = direct_auth.get("mode")
            return direct_auth

    def _cleanup_cached_direct_auth(self) -> None:
        with self._direct_auth_lock:
            direct_auth = self._cached_direct_auth
            self._cached_direct_auth = None
            self._cached_direct_auth_mode = None
        if not direct_auth or direct_auth.get("mode") != "ephemeral_key":
            return
        src_engine = SftpEngine(self.src_site, self.logger)
        dst_engine = SftpEngine(self.dst_site, self.logger)
        try:
            src_engine.connect()
            dst_engine.connect()
            self._cleanup_direct_auth(src_engine, dst_engine, direct_auth)
        except Exception as exc:
            self.logger.warning("remote_direct_cleanup_failed mode=cached auth=%s error=%s", self._direct_auth_label(direct_auth), exc)
        finally:
            dst_engine.disconnect()
            src_engine.disconnect()

    def _warm_cached_direct_auth(self) -> dict[str, str] | None:
        with self._direct_auth_lock:
            cached = self._cached_direct_auth
        if cached is not None:
            return cached
        src_engine = SftpEngine(self.src_site, self.logger)
        dst_engine = SftpEngine(self.dst_site, self.logger)
        try:
            src_engine.connect()
            dst_engine.connect()
            return self._prepare_direct_auth(src_engine, dst_engine)
        finally:
            dst_engine.disconnect()
            src_engine.disconnect()

    def _bootstrap_ephemeral_direct_key(
        self,
        src_engine: SftpEngine,
        dst_engine: SftpEngine,
    ) -> dict[str, str]:
        transfer_id = f"{int(time.time() * 1000)}-{threading.get_ident()}"
        marker = f"sshferry-direct-{transfer_id}"
        key_path = f"/tmp/{marker}"
        create_cmd = (
            "umask 077 && "
            f"ssh-keygen -q -t ed25519 -N '' -C {self._shell_quote(marker)} "
            f"-f {self._shell_quote(key_path)} < /dev/null && "
            f"cat {self._shell_quote(key_path + '.pub')}"
        )
        exit_code, std_out, std_err = self._exec_remote_command(src_engine, create_cmd)
        if exit_code != 0:
            raise SSHFerryError(
                ErrorCode.TRANSFER_FAILED,
                self._format_direct_failure("bootstrap_keygen", exit_code, std_out, std_err),
            )
        public_key = next((line.strip() for line in reversed(std_out.splitlines()) if line.strip()), "")
        if "ssh-ed25519 " not in public_key and "ssh-rsa " not in public_key:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, "direct bootstrap failed: generated public key missing")

        install_cmd = (
            "umask 077 && mkdir -p ~/.ssh && touch ~/.ssh/authorized_keys && "
            "chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys && "
            f"printf '%s\\n' {self._shell_quote('restrict ' + public_key)} >> ~/.ssh/authorized_keys"
        )
        exit_code, std_out, std_err = self._exec_remote_command(dst_engine, install_cmd)
        if exit_code != 0:
            try:
                self._exec_remote_command(src_engine, f"rm -f -- {self._shell_quote(key_path)} {self._shell_quote(key_path + '.pub')}")
            except Exception:
                pass
            raise SSHFerryError(
                ErrorCode.TRANSFER_FAILED,
                self._format_direct_failure("bootstrap_authorize", exit_code, std_out, std_err),
            )
        self.logger.info(
            "remote_direct_bootstrap mode=ephemeral_key src=%s dst=%s marker=%s",
            self.src_site.host,
            self.dst_site.host,
            marker,
        )
        return {"mode": "ephemeral_key", "key_path": key_path, "marker": marker}

    def _cleanup_direct_auth(
        self,
        src_engine: SftpEngine,
        dst_engine: SftpEngine,
        direct_auth: dict[str, str],
    ) -> None:
        marker = direct_auth.get("marker")
        key_path = direct_auth.get("key_path")
        if marker:
            cleanup_cmd = (
                "if [ -f ~/.ssh/authorized_keys ]; then "
                f"grep -vF -- {self._shell_quote(marker)} ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.sshferry.tmp || true; "
                "mv ~/.ssh/authorized_keys.sshferry.tmp ~/.ssh/authorized_keys; "
                "chmod 600 ~/.ssh/authorized_keys; "
                "fi"
            )
            try:
                self._exec_remote_command(dst_engine, cleanup_cmd)
            except Exception as exc:
                self.logger.warning("remote_direct_cleanup_failed target=dst marker=%s error=%s", marker, exc)
        if key_path:
            try:
                self._exec_remote_command(
                    src_engine,
                    f"rm -f -- {self._shell_quote(key_path)} {self._shell_quote(key_path + '.pub')}",
                )
            except Exception as exc:
                self.logger.warning("remote_direct_cleanup_failed target=src key=%s error=%s", key_path, exc)

    @staticmethod
    def _direct_auth_label(direct_auth: dict[str, str] | None) -> str:
        if not direct_auth:
            return "default"
        return direct_auth.get("mode", "default")

    def _direct_auth_key_path(self, direct_auth: dict[str, str] | None) -> str | None:
        if direct_auth and direct_auth.get("key_path"):
            return direct_auth["key_path"]
        return self._remote_usable_path(self.dst_site.key_path)

    @staticmethod
    def _remote_usable_path(path_value: str | None) -> str | None:
        normalized = (path_value or "").strip()
        if not normalized:
            return None
        if ":\\" in normalized or normalized[:2].endswith(":"):
            return None
        if "\\" in normalized:
            return None
        return normalized

    def _can_attempt_direct_copy(self) -> bool:
        return self._direct_unavailable_reason() is None

    def _direct_unavailable_reason(self) -> str | None:
        if not self.dst_site.host:
            return "destination_host_missing"
        if not self.dst_site.username:
            return "destination_username_missing"
        if self.dst_site.port <= 0:
            return "destination_port_invalid"
        return None
