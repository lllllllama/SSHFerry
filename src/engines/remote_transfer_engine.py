"""Remote-to-remote transfer engine with direct-copy attempt and relay fallback."""
import math
import os
import threading
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


class RemoteToRemoteTransferEngine:
    """Transfer files/folders between two remote SSH sites."""

    def __init__(
        self,
        src_site: SiteConfig,
        dst_site: SiteConfig,
        logger,
        parallel_threshold: int = DEFAULT_PARALLEL_THRESHOLD_BYTES,
        relay_download_preset: str = "high",
        relay_upload_preset: str = "medium",
    ):
        self.src_site = src_site
        self.dst_site = dst_site
        self.logger = logger
        self.parallel_threshold = parallel_threshold
        self.relay_download_preset = relay_download_preset
        self.relay_upload_preset = relay_upload_preset

    def transfer_file(
        self,
        src_path: str,
        dst_path: str,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> str:
        """Transfer one file. Returns transfer mode used: direct or relay."""
        normalized_src = normalize_remote_path(src_path)
        normalized_dst = normalize_remote_path(dst_path)
        ensure_in_sandbox(normalized_src, self.src_site.remote_root)
        ensure_in_sandbox(normalized_dst, self.dst_site.remote_root)
        total = self._remote_file_size(normalized_src)
        if total >= self.parallel_threshold:
            self._transfer_file_parallel_bridge(
                normalized_src,
                normalized_dst,
                total,
                callback=callback,
                check_interrupt=check_interrupt,
            )
            return "parallel_bridge"
        try:
            self._transfer_file_direct(normalized_src, normalized_dst, callback=callback, check_interrupt=check_interrupt)
            return "direct"
        except SSHFerryError as exc:
            self.logger.warning("remote_direct_failed src=%s dst=%s reason=%s", normalized_src, normalized_dst, exc.message)
            self._transfer_file_relay(
                normalized_src,
                normalized_dst,
                callback=callback,
                check_interrupt=check_interrupt,
                total=total,
            )
            return "bridge"

    def transfer_dir(
        self,
        src_dir: str,
        dst_dir: str,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> str:
        """Transfer a directory recursively. Returns transfer mode used."""
        normalized_src = normalize_remote_path(src_dir)
        normalized_dst = normalize_remote_path(dst_dir)
        ensure_in_sandbox(normalized_src, self.src_site.remote_root)
        ensure_in_sandbox(normalized_dst, self.dst_site.remote_root)
        try:
            self._transfer_dir_direct(normalized_src, normalized_dst, callback=callback, check_interrupt=check_interrupt)
            return "direct"
        except SSHFerryError as exc:
            self.logger.warning("remote_direct_dir_failed src=%s dst=%s reason=%s", normalized_src, normalized_dst, exc.message)
            self._transfer_dir_relay(normalized_src, normalized_dst, callback=callback, check_interrupt=check_interrupt)
            return "bridge"

    def _transfer_file_direct(
        self,
        src_path: str,
        dst_path: str,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> None:
        """Attempt remote-to-remote direct copy via scp from source host."""
        if self.dst_site.auth_method != "key" or not self.dst_site.key_path:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, "Direct remote copy requires destination key auth")
        src_engine = SftpEngine(self.src_site, self.logger)
        try:
            src_engine.connect()
            src_stat = src_engine.stat(src_path)
            total = src_stat.size
            if callback:
                callback(0, total)
            if check_interrupt and check_interrupt():
                raise InterruptedError("Task interrupted")

            key_path = self.dst_site.key_path.replace("\\", "/")
            quoted_src = self._shell_quote(normalized_src)
            quoted_dst = self._shell_quote(normalized_dst)
            host = self.dst_site.host
            port = self.dst_site.port
            user = self.dst_site.username
            cmd = (
                f"command -v scp >/dev/null 2>&1 && "
                f"scp -q -P {port} -i {self._shell_quote(key_path)} "
                f"-o BatchMode=yes -o StrictHostKeyChecking=no "
                f"-- {quoted_src} {self._shell_quote(f'{user}@{host}:{dst_path}')}"
            )
            stdin, stdout, stderr = src_engine.ssh_client.exec_command(cmd)
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                err = stderr.read().decode("utf-8", errors="replace").strip() or "direct scp failed"
                raise SSHFerryError(ErrorCode.TRANSFER_FAILED, err)
            if callback:
                callback(total, total)
        except InterruptedError:
            raise
        finally:
            src_engine.disconnect()

    def _transfer_dir_direct(
        self,
        src_dir: str,
        dst_dir: str,
        callback: Optional[Callable[[int, int], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
    ) -> None:
        if self.dst_site.auth_method != "key" or not self.dst_site.key_path:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, "Direct remote copy requires destination key auth")
        src_engine = SftpEngine(self.src_site, self.logger)
        dst_engine = SftpEngine(self.dst_site, self.logger)
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
            key_path = self.dst_site.key_path.replace("\\", "/")
            host = self.dst_site.host
            port = self.dst_site.port
            user = self.dst_site.username
            cmd = (
                f"command -v scp >/dev/null 2>&1 && "
                f"scp -q -r -P {port} -i {self._shell_quote(key_path)} "
                f"-o BatchMode=yes -o StrictHostKeyChecking=no "
                f"-- {self._shell_quote(src_dir)} {self._shell_quote(f'{user}@{host}:{dst_dir}')}"
            )
            stdin, stdout, stderr = src_engine.ssh_client.exec_command(cmd)
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                err = stderr.read().decode("utf-8", errors="replace").strip() or "direct recursive scp failed"
                raise SSHFerryError(ErrorCode.TRANSFER_FAILED, err)
            if callback:
                callback(total, total)
        except InterruptedError:
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
    ) -> None:
        src_engine = SftpEngine(self.src_site, self.logger)
        dst_engine = SftpEngine(self.dst_site, self.logger)
        try:
            src_engine.connect()
            dst_engine.connect()
            total = self._remote_dir_size(src_engine, src_dir)
            if callback:
                callback(0, total)
            self._stream_dir_between_engines(src_engine, dst_engine, src_dir, dst_dir, total, callback, check_interrupt)
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
    ) -> int:
        try:
            dst_engine.mkdir(dst_dir)
        except SSHFerryError:
            pass
        bytes_done = 0

        def walk(current_src: str, current_dst: str) -> None:
            nonlocal bytes_done
            for entry in src_engine.list_dir(current_src):
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Task interrupted")
                target_path = f"{current_dst.rstrip('/')}/{entry.name}"
                if entry.is_dir:
                    try:
                        dst_engine.mkdir(target_path)
                    except SSHFerryError:
                        pass
                    walk(entry.path, target_path)
                    continue

                if entry.size >= self.parallel_threshold:
                    start_offset = bytes_done

                    def file_progress(done: int, _file_total: int) -> None:
                        if callback:
                            callback(min(total, start_offset + done), total)

                    self._transfer_file_parallel_bridge(
                        entry.path,
                        target_path,
                        entry.size,
                        callback=file_progress,
                        check_interrupt=check_interrupt,
                    )
                else:
                    self._stream_file_between_engines(
                        src_engine,
                        dst_engine,
                        entry.path,
                        target_path,
                        entry.size,
                        callback=None,
                        check_interrupt=check_interrupt,
                    )
                bytes_done += entry.size
                if callback:
                    callback(min(total, bytes_done), total)

        walk(src_dir, dst_dir)
        return bytes_done

    def _stream_file_between_engines(
        self,
        src_engine: SftpEngine,
        dst_engine: SftpEngine,
        src_path: str,
        dst_path: str,
        total: int,
        callback: Optional[Callable[[int, int], None]],
        check_interrupt: Optional[Callable[[], bool]],
    ) -> None:
        chunk_size = 4 * 1024 * 1024
        bytes_done = 0
        with src_engine.sftp_client.open(src_path, "rb") as src_file:
            with dst_engine.sftp_client.open(dst_path, "wb") as dst_file:
                if hasattr(dst_file, "set_pipelined"):
                    dst_file.set_pipelined(True)
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

    @staticmethod
    def _shell_quote(text: str) -> str:
        return "'" + text.replace("'", "'\"'\"'") + "'"
