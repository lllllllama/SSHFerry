"""Parallel SFTP engine for accelerated transfer using multiple connections."""
from dataclasses import dataclass
import logging
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from queue import Empty, Queue
from typing import Callable, Optional, Tuple

from src.engines.sftp_engine import SftpEngine
from src.shared.errors import ErrorCode, SSHFerryError
from src.shared.models import SiteConfig
from src.shared.paths import ensure_in_sandbox, normalize_remote_path


@dataclass(frozen=True)
class ParallelPreset:
    """Preset tuned for large-file transfer throughput."""

    workers: int
    chunk_size: int


PARALLEL_PRESETS: dict[str, ParallelPreset] = {
    "low": ParallelPreset(workers=4, chunk_size=2 * 1024 * 1024),
    "medium": ParallelPreset(workers=10, chunk_size=4 * 1024 * 1024),
    "high": ParallelPreset(workers=16, chunk_size=8 * 1024 * 1024),
}
DEFAULT_PARALLEL_THRESHOLD_BYTES = 50 * 1024 * 1024  # 50 MB


def _env_int(name: str, default: int, min_value: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
        return max(min_value, value)
    except ValueError:
        return default


def _env_float(name: str, default: float, min_value: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = float(raw)
        return max(min_value, value)
    except ValueError:
        return default


class ParallelSftpEngine:
    """
    Manages parallel file transfers using multiple persistent SFTP connections.
    """
    _host_worker_caps: dict[str, int] = {}
    _host_cap_lock = threading.Lock()

    def __init__(
        self,
        site_config: SiteConfig,
        logger: Optional[logging.Logger] = None,
        max_workers: Optional[int] = None,
        chunk_size: Optional[int] = None,
        preset_name: Optional[str] = None,
    ):
        self.site_config = site_config
        self.logger = logger or logging.getLogger(__name__)
        preset = PARALLEL_PRESETS.get(preset_name or "", PARALLEL_PRESETS["medium"])
        self.max_workers = max_workers if max_workers is not None else preset.workers
        self.chunk_size = chunk_size if chunk_size is not None else preset.chunk_size
        self.min_workers = 2
        self.warmup_batch_size = 4
        self.warmup_delay_seconds = 0.08
        self.connect_retries = 3
        self.connect_backoff_seconds = 0.4
        self.degrade_after_failures = 2
        self.max_chunk_retries = 4
        self.max_workers = _env_int("SSHFERRY_PARALLEL_WORKERS", self.max_workers, 1)
        self.chunk_size = _env_int("SSHFERRY_PARALLEL_CHUNK_BYTES", self.chunk_size, 64 * 1024)
        self.warmup_batch_size = _env_int("SSHFERRY_PARALLEL_WARMUP_BATCH", self.warmup_batch_size, 1)
        self.warmup_delay_seconds = _env_float(
            "SSHFERRY_PARALLEL_WARMUP_DELAY",
            self.warmup_delay_seconds,
            0.0,
        )
        self.max_chunk_retries = _env_int(
            "SSHFERRY_PARALLEL_MAX_CHUNK_RETRIES",
            self.max_chunk_retries,
            0,
        )
        self.host_key = f"{site_config.username}@{site_config.host}:{site_config.port}"

    def _connect_with_retry(self, eng: SftpEngine) -> bool:
        """Connect engine with retry/backoff for transient SSH handshake errors."""
        for attempt in range(1, self.connect_retries + 1):
            try:
                eng.connect()
                return True
            except Exception as e:
                if attempt >= self.connect_retries:
                    self.logger.error(f"Worker connection failed after retries: {e}")
                    return False
                delay = self.connect_backoff_seconds * (2 ** (attempt - 1))
                time.sleep(delay)
        return False

    def _get_effective_worker_count(self, num_chunks: int) -> int:
        """Resolve worker count with host-level adaptive cap."""
        with self._host_cap_lock:
            cap = self._host_worker_caps.get(self.host_key, self.max_workers)
        return min(self.max_workers, cap, max(1, num_chunks))

    def _degrade_host_worker_cap(self, current_target: int) -> int:
        """Lower host-level worker cap after repeated connect failures."""
        new_cap = max(self.min_workers, current_target // 2)
        with self._host_cap_lock:
            old_cap = self._host_worker_caps.get(self.host_key, self.max_workers)
            if new_cap < old_cap:
                self._host_worker_caps[self.host_key] = new_cap
                self.logger.warning(
                    f"Adaptive parallel cap: {self.host_key} workers {old_cap} -> {new_cap}"
                )
        return new_cap

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        callback: Optional[Callable] = None,
        check_interrupt: Optional[Callable] = None,
    ) -> None:
        """
        Upload file in parallel using persistent connections.
        """
        ensure_in_sandbox(remote_path, self.site_config.remote_root)
        normalized_remote_path = normalize_remote_path(remote_path)
        file_size = os.path.getsize(local_path)
        
        if file_size < self.chunk_size:
            # Fallback for small files
            engine = SftpEngine(self.site_config, self.logger)
            engine.connect()
            try:
                engine.upload_file(local_path, normalized_remote_path, callback, check_interrupt)
            finally:
                engine.disconnect()
            return

        # Prepare chunks
        num_chunks = math.ceil(file_size / self.chunk_size)
        queue: Queue[Tuple[int, int]] = Queue()
        for i in range(num_chunks):
            offset = i * self.chunk_size
            length = min(self.chunk_size, file_size - offset)
            queue.put((offset, length))

        # Shared state
        bytes_transferred = 0
        lock = threading.Lock()
        interrupt_event = threading.Event()
        last_reported = 0
        completed_chunks = 0
        chunk_failures: dict[int, int] = {}
        last_error: list[str] = []

        # Pre-allocate remote file
        init_engine = SftpEngine(self.site_config, self.logger)
        if not self._connect_with_retry(init_engine):
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, "Failed to establish initial upload connection")
        try:
            with init_engine.sftp_client.open(normalized_remote_path, "wb") as f:
                if hasattr(f, "set_pipelined"):
                    f.set_pipelined(True)
                try:
                    f.truncate(file_size)
                except Exception:
                    pass
        finally:
            init_engine.disconnect()

        # Worker function
        connect_failures = 0
        def worker_loop():
            nonlocal connect_failures
            eng = SftpEngine(self.site_config, self.logger)
            try:
                if not self._connect_with_retry(eng):
                    with lock:
                        connect_failures += 1
                    return
                with open(local_path, 'rb') as f:
                    with eng.sftp_client.open(normalized_remote_path, 'r+b') as rf:
                        if hasattr(rf, "set_pipelined"):
                            rf.set_pipelined(True)
                        while not interrupt_event.is_set():
                            try:
                                offset, length = queue.get(timeout=0.5)
                            except Empty:
                                if queue.empty():
                                    break
                                continue

                            if check_interrupt and check_interrupt():
                                interrupt_event.set()
                                return

                            if interrupt_event.is_set():
                                return

                            try:
                                f.seek(offset)
                                data = f.read(length)
                                rf.seek(offset)
                                rf.write(data)

                                report_now = False
                                report_value = 0
                                with lock:
                                    nonlocal bytes_transferred, last_reported, completed_chunks
                                    written = len(data)
                                    bytes_transferred += written
                                    completed_chunks += 1
                                    if callback and (
                                        bytes_transferred == file_size
                                        or bytes_transferred - last_reported >= self.chunk_size
                                    ):
                                        last_reported = bytes_transferred
                                        report_now = True
                                        report_value = bytes_transferred
                                if report_now:
                                    callback(report_value, file_size)
                            except Exception as e:
                                should_abort = False
                                with lock:
                                    retry_count = chunk_failures.get(offset, 0) + 1
                                    chunk_failures[offset] = retry_count
                                    if retry_count > self.max_chunk_retries:
                                        should_abort = True
                                        last_error[:] = [str(e)]
                                if should_abort:
                                    interrupt_event.set()
                                    self.logger.error(
                                        f"Upload chunk failed repeatedly at offset {offset}: {e}"
                                    )
                                    return
                                self.logger.warning(
                                    f"Upload chunk failed at offset {offset}, retry {retry_count}/{self.max_chunk_retries}: {e}"
                                )
                                queue.put((offset, length))
                                continue
                            finally:
                                queue.task_done()

            except Exception as e:
                self.logger.error(f"Upload worker failed: {e}")
            finally:
                eng.disconnect()

        worker_count = self._get_effective_worker_count(num_chunks)
        target_workers = worker_count
        launched_workers = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            while launched_workers < target_workers:
                batch = min(self.warmup_batch_size, target_workers - launched_workers)
                for _ in range(batch):
                    futures.append(executor.submit(worker_loop))
                    launched_workers += 1
                time.sleep(self.warmup_delay_seconds)
                with lock:
                    if connect_failures >= self.degrade_after_failures and target_workers > self.min_workers:
                        target_workers = self._degrade_host_worker_cap(target_workers)
            wait(futures)
            
            # Check for errors
            if check_interrupt and check_interrupt():
                raise InterruptedError("Transfer interrupted")
            if interrupt_event.is_set() and last_error:
                raise SSHFerryError(
                    ErrorCode.TRANSFER_FAILED,
                    f"Parallel upload failed: {last_error[0]}",
                )
            if bytes_transferred < file_size or completed_chunks < num_chunks:
                raise SSHFerryError(ErrorCode.TRANSFER_FAILED, "Parallel upload failed")

    def download_file(
        self,
        remote_path: str,
        local_path: str,
        callback: Optional[Callable] = None,
        check_interrupt: Optional[Callable] = None,
    ) -> None:
        """
        Download file in parallel.
        """
        ensure_in_sandbox(remote_path, self.site_config.remote_root)
        normalized_remote_path = normalize_remote_path(remote_path)
        # Get size
        init_engine = SftpEngine(self.site_config, self.logger)
        init_engine.connect()
        try:
            attr = init_engine.stat(normalized_remote_path)
            file_size = attr.size
        finally:
            init_engine.disconnect()

        if file_size < self.chunk_size:
            engine = SftpEngine(self.site_config, self.logger)
            engine.connect()
            try:
                engine.download_file(normalized_remote_path, local_path, callback, check_interrupt)
            finally:
                engine.disconnect()
            return

        # Pre-allocate local
        parent_dir = os.path.dirname(local_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(local_path, 'wb') as f:
            f.truncate(file_size)

        num_chunks = math.ceil(file_size / self.chunk_size)
        queue: Queue[Tuple[int, int]] = Queue()
        for i in range(num_chunks):
            offset = i * self.chunk_size
            length = min(self.chunk_size, file_size - offset)
            queue.put((offset, length))

        bytes_transferred = 0
        lock = threading.Lock()
        interrupt_event = threading.Event()
        last_reported = 0
        completed_chunks = 0
        connect_failures = 0
        chunk_failures: dict[int, int] = {}
        last_error: list[str] = []

        def worker_loop():
            nonlocal connect_failures
            eng = SftpEngine(self.site_config, self.logger)
            try:
                if not self._connect_with_retry(eng):
                    with lock:
                        connect_failures += 1
                    return
                with eng.sftp_client.open(normalized_remote_path, 'rb') as rf:
                    with open(local_path, 'r+b') as f:
                        while not interrupt_event.is_set():
                            try:
                                offset, length = queue.get(timeout=0.5)
                            except Empty:
                                if queue.empty():
                                    break
                                continue

                            if check_interrupt and check_interrupt():
                                interrupt_event.set()
                                return

                            if interrupt_event.is_set():
                                return

                            try:
                                rf.seek(offset)
                                data = rf.read(length)
                                f.seek(offset)
                                f.write(data)

                                report_now = False
                                report_value = 0
                                with lock:
                                    nonlocal bytes_transferred, last_reported, completed_chunks
                                    downloaded = len(data)
                                    bytes_transferred += downloaded
                                    completed_chunks += 1
                                    if callback and (
                                        bytes_transferred == file_size
                                        or bytes_transferred - last_reported >= self.chunk_size
                                    ):
                                        last_reported = bytes_transferred
                                        report_now = True
                                        report_value = bytes_transferred
                                if report_now:
                                    callback(report_value, file_size)
                            except Exception as e:
                                should_abort = False
                                with lock:
                                    retry_count = chunk_failures.get(offset, 0) + 1
                                    chunk_failures[offset] = retry_count
                                    if retry_count > self.max_chunk_retries:
                                        should_abort = True
                                        last_error[:] = [str(e)]
                                if should_abort:
                                    interrupt_event.set()
                                    self.logger.error(
                                        f"Download chunk failed repeatedly at offset {offset}: {e}"
                                    )
                                    return
                                self.logger.warning(
                                    f"Download chunk failed at offset {offset}, retry {retry_count}/{self.max_chunk_retries}: {e}"
                                )
                                queue.put((offset, length))
                                continue
                            finally:
                                queue.task_done()
            except Exception as e:
                self.logger.error(f"Download worker failed: {e}")
            finally:
                eng.disconnect()

        worker_count = self._get_effective_worker_count(num_chunks)
        target_workers = worker_count
        launched_workers = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            while launched_workers < target_workers:
                batch = min(self.warmup_batch_size, target_workers - launched_workers)
                for _ in range(batch):
                    futures.append(executor.submit(worker_loop))
                    launched_workers += 1
                time.sleep(self.warmup_delay_seconds)
                with lock:
                    if connect_failures >= self.degrade_after_failures and target_workers > self.min_workers:
                        target_workers = self._degrade_host_worker_cap(target_workers)
            wait(futures)
            
            if check_interrupt and check_interrupt():
                raise InterruptedError("Transfer interrupted")
            if interrupt_event.is_set() and last_error:
                raise SSHFerryError(
                    ErrorCode.TRANSFER_FAILED,
                    f"Parallel download failed: {last_error[0]}",
                )
            if bytes_transferred < file_size or completed_chunks < num_chunks:
                raise SSHFerryError(ErrorCode.TRANSFER_FAILED, "Parallel download failed")
