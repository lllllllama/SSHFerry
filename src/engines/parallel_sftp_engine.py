"""Parallel SFTP engine for accelerated transfer using multiple connections."""
import logging
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from queue import Queue, Empty
from typing import Callable, List, Optional, Tuple

from src.engines.sftp_engine import SftpEngine
from src.shared.errors import ErrorCode, SSHFerryError
from src.shared.models import SiteConfig


class ParallelSftpEngine:
    """
    Manages parallel file transfers using multiple persistent SFTP connections.
    """

    def __init__(
        self,
        site_config: SiteConfig,
        logger: Optional[logging.Logger] = None,
        max_workers: int = 4,
        chunk_size: int = 1024 * 1024 * 2  # 2MB chunks
    ):
        self.site_config = site_config
        self.logger = logger or logging.getLogger(__name__)
        self.max_workers = max_workers
        self.chunk_size = chunk_size

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
        file_size = os.path.getsize(local_path)
        
        if file_size < self.chunk_size:
            # Fallback for small files
            engine = SftpEngine(self.site_config, self.logger)
            engine.connect()
            try:
                engine.upload_file(local_path, remote_path, callback, check_interrupt)
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
        error_event = threading.Event()
        
        # Pre-allocate remote file
        init_engine = SftpEngine(self.site_config, self.logger)
        init_engine.connect()
        try:
            # Ensure folder exists? Assumed for now or handled by caller/engine
            with init_engine.sftp_client.open(remote_path, 'wb') as f:
                f.set_pipelined(True)
                # Try to pre-allocate
                try:
                    f.truncate(file_size)
                except:
                    pass
        finally:
            init_engine.disconnect()

        # Worker function
        def worker_loop():
            eng = SftpEngine(self.site_config, self.logger)
            try:
                eng.connect()
                
                while not error_event.is_set():
                    try:
                        # Non-blocking get with timeout to check interrupts
                        offset, length = queue.get(timeout=0.5)
                    except Empty:
                        if queue.empty():
                            break
                        continue

                    # Check interrupt
                    if check_interrupt and check_interrupt():
                        error_event.set()
                        return

                    if error_event.is_set():
                        return

                    # Perform upload
                    try:
                        with open(local_path, 'rb') as f:
                            f.seek(offset)
                            data = f.read(length)
                        
                        with eng.sftp_client.open(remote_path, 'r+b') as rf:
                            rf.seek(offset)
                            rf.write(data)

                        with lock:
                            nonlocal bytes_transferred
                            bytes_transferred += length
                            if callback:
                                callback(bytes_transferred, file_size)
                                
                    except Exception as e:
                        self.logger.error(f"Upload worker failed: {e}")
                        error_event.set()
                        raise
                    finally:
                        queue.task_done()
                        
            except Exception as e:
                self.logger.error(f"Worker connection failed: {e}")
                error_event.set()
            finally:
                eng.disconnect()

        # Launch threads
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(worker_loop) for _ in range(self.max_workers)]
            wait(futures)
            
            # Check for errors
            if error_event.is_set():
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Transfer interrupted")
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
        # Get size
        init_engine = SftpEngine(self.site_config, self.logger)
        init_engine.connect()
        try:
            attr = init_engine.stat(remote_path)
            file_size = attr.size
        finally:
            init_engine.disconnect()

        if file_size < self.chunk_size:
            engine = SftpEngine(self.site_config, self.logger)
            engine.connect()
            try:
                engine.download_file(remote_path, local_path, callback, check_interrupt)
            finally:
                engine.disconnect()
            return

        # Pre-allocate local
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
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
        error_event = threading.Event()

        def worker_loop():
            eng = SftpEngine(self.site_config, self.logger)
            try:
                eng.connect()
                
                while not error_event.is_set():
                    try:
                        offset, length = queue.get(timeout=0.5)
                    except Empty:
                        if queue.empty():
                            break
                        continue

                    if check_interrupt and check_interrupt():
                        error_event.set()
                        return

                    if error_event.is_set():
                        return

                    try:
                        with eng.sftp_client.open(remote_path, 'rb') as rf:
                            rf.seek(offset)
                            data = rf.read(length)
                        
                        # Thread-safe write logic?
                        # Using rb+ on shared file path requires caution on Windows.
                        # Opening/closing handle per chunk is robust.
                        with open(local_path, 'r+b') as f:
                            f.seek(offset)
                            f.write(data)

                        with lock:
                            nonlocal bytes_transferred
                            bytes_transferred += length
                            if callback:
                                callback(bytes_transferred, file_size)

                    except Exception as e:
                        self.logger.error(f"Download worker failed: {e}")
                        error_event.set()
                        raise
                    finally:
                        queue.task_done()
            except Exception as e:
                self.logger.error(f"Worker connection failed: {e}")
                error_event.set()
            finally:
                eng.disconnect()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(worker_loop) for _ in range(self.max_workers)]
            wait(futures)
            
            if error_event.is_set():
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Transfer interrupted")
                raise SSHFerryError(ErrorCode.TRANSFER_FAILED, "Parallel download failed")
