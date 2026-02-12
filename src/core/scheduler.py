"""Task scheduler for managing file transfer tasks."""
import logging
import os
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Queue
from threading import Lock, Thread
from typing import Dict, List, Optional

from src.engines.parallel_sftp_engine import (
    DEFAULT_PARALLEL_THRESHOLD_BYTES,
    ParallelSftpEngine,
)
from src.engines.sftp_engine import SftpEngine
from src.services.metrics import MetricsCollector, TransferRecord
from src.shared.errors import ErrorCode, SSHFerryError
from src.shared.logging_ import log_task_event
from src.shared.models import SiteConfig, Task


class TaskScheduler:
    """
    Task scheduler with minimal state machine.
    
    Manages a queue of tasks and executes them using a thread pool.
    
    State transitions:
    - pending -> running -> done/failed/canceled
    - running -> paused -> running
    """

    def __init__(
        self,
        site_config: SiteConfig,
        max_workers: int = 3,
        parallel_preset: str = "high",
        parallel_upload_preset: str = "medium",
        parallel_download_preset: str = "high",
        parallel_threshold: int = DEFAULT_PARALLEL_THRESHOLD_BYTES,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize task scheduler.
        
        Args:
            site_config: Site configuration for SFTP connection
            max_workers: Maximum number of concurrent tasks
            parallel_preset: Legacy fallback parallel preset (low/medium/high)
            parallel_upload_preset: Parallel preset for upload tasks
            parallel_download_preset: Parallel preset for download tasks
            parallel_threshold: File size threshold for auto parallel mode (bytes)
            logger: Optional logger instance
        """
        self.site_config = site_config
        self.max_workers = max_workers
        self.parallel_preset = parallel_preset
        self.parallel_upload_preset = parallel_upload_preset or parallel_preset
        self.parallel_download_preset = parallel_download_preset or parallel_preset
        self.parallel_threshold = parallel_threshold
        self.logger = logger or logging.getLogger(__name__)

        # Task storage
        self.tasks: Dict[str, Task] = {}
        self.task_lock = Lock()

        # Task queue (priority queue)
        self.task_queue: Queue[str] = Queue()
        self.queued_task_ids: set[str] = set()

        # Thread pool for executing tasks
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.futures: Dict[str, Future] = {}

        # Scheduler thread
        self.running = False
        self.scheduler_thread: Optional[Thread] = None

        # Metrics collector for adaptive preset selection
        self.metrics = MetricsCollector()

    def start(self):
        """Start the scheduler."""
        if self.running:
            return

        self.running = True
        self.scheduler_thread = Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        self.logger.info("Task scheduler started")

    def stop(self):
        """Stop the scheduler and wait for completion."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        self.executor.shutdown(wait=True)
        self.logger.info("Task scheduler stopped")

    def add_task(self, task: Task) -> str:
        """
        Add a task to the queue.
        
        Args:
            task: Task to add
            
        Returns:
            Task ID
        """
        with self.task_lock:
            self.tasks[task.task_id] = task
            if task.task_id not in self.queued_task_ids:
                self.task_queue.put(task.task_id)
                self.queued_task_ids.add(task.task_id)

        self.logger.info(f"Added task {task.task_id}: {task.kind} {task.src} -> {task.dst}")
        return task.task_id

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        with self.task_lock:
            return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[Task]:
        """Get all tasks."""
        with self.task_lock:
            return list(self.tasks.values())

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task.
        
        Args:
            task_id: Task ID to cancel
            
        Returns:
            True if canceled, False otherwise
        """
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task:
                return False

            if task.status == "pending":
                task.status = "canceled"
                self.logger.info(f"Canceled pending task {task_id[:8]}")
                return True
            elif task.status == "running":
                # Set interrupted flag for graceful cancellation
                task.interrupted = True
                self.logger.info(f"Interrupting running task {task_id[:8]}")
                return True
            elif task.status == "paused":
                task.status = "canceled"
                self.logger.info(f"Canceled paused task {task_id[:8]}")
                return True

        return False

    def pause_task(self, task_id: str) -> bool:
        """
        Pause a running task.
        
        Args:
            task_id: Task ID to pause
            
        Returns:
            True if paused, False otherwise
        """
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task:
                return False

            if task.status == "running":
                task.paused = True
                self.logger.info(f"Pausing task {task_id[:8]}")
                return True

        return False

    def resume_task(self, task_id: str) -> bool:
        """
        Resume a paused task.
        
        Args:
            task_id: Task ID to resume
            
        Returns:
            True if resumed, False otherwise
        """
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task:
                return False

            if task.status == "paused":
                task.status = "pending"
                task.paused = False
                # Re-queue the task
                if task_id not in self.queued_task_ids:
                    self.task_queue.put(task_id)
                    self.queued_task_ids.add(task_id)
                self.logger.info(f"Resumed task {task_id[:8]}")
                return True

        return False

    def restart_task(self, task_id: str) -> bool:
        """
        Restart a failed, canceled, or done task.
        
        Args:
            task_id: Task ID to restart
            
        Returns:
            True if restarted, False otherwise
        """
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task:
                return False

            if task.status in ("failed", "canceled", "done", "skipped"):
                task.status = "pending"
                task.bytes_done = 0
                task.speed = 0.0
                task.error_code = None
                task.error_message = None
                task.start_time = None
                task.interrupted = False
                task.paused = False
                task.skipped = False
                
                # Re-queue the task
                if task_id not in self.queued_task_ids:
                    self.task_queue.put(task_id)
                    self.queued_task_ids.add(task_id)
                self.logger.info(f"Restarting task {task_id[:8]}")
                return True

        return False

    def _scheduler_loop(self):
        """Main scheduler loop that processes tasks from queue."""
        while self.running:
            try:
                # Get next task from queue (with timeout to allow checking self.running)
                if not self.task_queue.empty():
                    task_id = self.task_queue.get(timeout=0.5)

                    with self.task_lock:
                        self.queued_task_ids.discard(task_id)
                        task = self.tasks.get(task_id)

                    if task and task.status == "pending":
                        # Submit task to executor
                        future = self.executor.submit(self._execute_task, task)
                        self.futures[task_id] = future
                else:
                    time.sleep(0.1)

            except Exception as e:
                self.logger.error(f"Scheduler loop error: {e}")
                time.sleep(1)

    def _execute_task(self, task: Task):
        """
        Execute a single task.
        
        Args:
            task: Task to execute
        """
        with self.task_lock:
            task.status = "running"
            task.start_time = time.time()  # Track start time for speed calculation

        log_task_event(
            self.logger,
            task.task_id,
            task.engine,
            task.kind,
            "running",
            self.site_config.host,
            self.site_config.port,
            self.site_config.username,
            task.src,
            task.dst
        )

        try:
            # Execute based on task kind and engine
            if task.kind == "upload":
                if task.engine == "parallel":
                    self._execute_parallel_upload(task)
                else:
                    self._execute_upload(task)
            elif task.kind == "download":
                if task.engine == "parallel":
                    self._execute_parallel_download(task)
                else:
                    self._execute_download(task)
            elif task.kind == "folder_upload":
                self._execute_folder_upload(task)
            elif task.kind == "folder_download":
                self._execute_folder_download(task)
            elif task.kind == "delete":
                self._execute_delete(task)
            elif task.kind == "mkdir":
                self._execute_mkdir(task)
            elif task.kind == "rename":
                self._execute_rename(task)
            else:
                raise ValueError(f"Unknown task kind: {task.kind}")

            with self.task_lock:
                # Only mark as done if it hasn't been paused/canceled/skipped
                if task.status == "running":
                    task.status = "done"
                    task.end_time = time.time()
                    task.bytes_done = task.bytes_total

            # Record metrics for transfer tasks
            if task.kind in ("upload", "download", "folder_upload", "folder_download") and task.status == "done":
                duration = time.time() - (task.start_time or time.time())
                self.metrics.record(TransferRecord(
                    preset=self._metric_preset_for_task(task),
                    bytes_transferred=task.bytes_done,
                    duration_seconds=max(0.1, duration),
                    success=True,
                    timestamp=time.time()
                ))

            log_task_event(
                self.logger,
                task.task_id,
                task.engine,
                task.kind,
                task.status,
                bytes_done=task.bytes_done,
                bytes_total=task.bytes_total
            )

        except SSHFerryError as e:
            with self.task_lock:
                task.status = "failed"
                task.end_time = time.time()
                task.error_code = e.code
                task.error_message = e.message

            # Record failed transfer metrics
            if task.kind in ("upload", "download", "folder_upload", "folder_download"):
                duration = time.time() - (task.start_time or time.time())
                self.metrics.record(TransferRecord(
                    preset=self._metric_preset_for_task(task),
                    bytes_transferred=task.bytes_done,
                    duration_seconds=max(0.1, duration),
                    success=False,
                    timestamp=time.time()
                ))

            log_task_event(
                self.logger,
                task.task_id,
                task.engine,
                task.kind,
                "failed",
                error_code=e.code,
                message=e.message
            )
        except Exception as e:
            with self.task_lock:
                task.status = "failed"
                task.end_time = time.time()
                task.error_code = ErrorCode.UNKNOWN_ERROR
                task.error_message = str(e)

            # Record failed transfer metrics
            if task.kind in ("upload", "download", "folder_upload", "folder_download"):
                duration = time.time() - (task.start_time or time.time())
                self.metrics.record(TransferRecord(
                    preset=self._metric_preset_for_task(task),
                    bytes_transferred=task.bytes_done,
                    duration_seconds=max(0.1, duration),
                    success=False,
                    timestamp=time.time()
                ))

            log_task_event(
                self.logger,
                task.task_id,
                task.engine,
                task.kind,
                "failed",
                error_code=ErrorCode.UNKNOWN_ERROR,
                message=str(e)
            )

    def _execute_upload(self, task: Task):
        """Execute upload task with smart file detection."""
        engine = SftpEngine(self.site_config, self.logger)
        engine.connect()

        try:
            local_size = os.path.getsize(task.src)
            original_dst = task.dst
            
            # Check if file already exists at destination
            offset = 0
            try:
                remote_stat = engine.stat(task.dst)
                if remote_stat.size == local_size:
                    # File exists and is complete - skip
                    with self.task_lock:
                        task.skipped = True
                        task.status = "skipped"
                        task.bytes_done = local_size
                    self.logger.info(f"Skipped (exists): {os.path.basename(task.src)}")
                    return
                elif remote_stat.size < local_size:
                    # File exists and is smaller - resume
                    offset = remote_stat.size
                    self.logger.info(f"Resuming upload from {offset} bytes: {os.path.basename(task.src)}")
                else:
                     # File exists and is larger - overwrite (offset 0)
                     self.logger.info(f"Overwriting larger file: {os.path.basename(task.src)}")
            except:
                pass  # File doesn't exist, proceed normally

            def progress_callback(bytes_transferred, bytes_total):
                with self.task_lock:
                    task.bytes_done = bytes_transferred
                    task.bytes_total = bytes_total
                    if task.start_time:
                        elapsed = time.time() - task.start_time
                        if elapsed > 0:
                            task.speed = bytes_transferred / elapsed

            def check_interrupt():
                # Check for pause request
                if task.paused:
                    with self.task_lock:
                        task.status = "paused"
                    raise InterruptedError("Task paused")
                return task.interrupted

            engine.upload_file(task.src, task.dst, callback=progress_callback, check_interrupt=check_interrupt, offset=offset)
        except InterruptedError as e:
            with self.task_lock:
                if task.paused:
                    task.status = "paused"
                    self.logger.info(f"Paused: {os.path.basename(task.src)}")
                else:
                    task.status = "canceled"
                    self.logger.info(f"Canceled: {os.path.basename(task.src)}")
        finally:
            engine.disconnect()

    def _get_unique_remote_path(self, engine: SftpEngine, remote_path: str) -> str:
        """Generate unique remote path by adding sequence number."""
        base, ext = os.path.splitext(remote_path)
        counter = 1
        new_path = f"{base}_{counter}{ext}"
        
        while True:
            try:
                engine.stat(new_path)
                counter += 1
                new_path = f"{base}_{counter}{ext}"
            except:
                return new_path

    def _execute_download(self, task: Task):
        """Execute download task with smart file detection."""
        engine = SftpEngine(self.site_config, self.logger)
        engine.connect()

        try:
            # Get remote file size
            try:
                remote_stat = engine.stat(task.src)
                remote_size = remote_stat.size
            except:
                remote_size = task.bytes_total
            
            # Check if local file already exists
            offset = 0
            if os.path.exists(task.dst):
                local_size = os.path.getsize(task.dst)
                if local_size == remote_size:
                    # File exists and is complete - skip
                    with self.task_lock:
                        task.skipped = True
                        task.status = "skipped"
                        task.bytes_done = remote_size
                    self.logger.info(f"Skipped (exists): {os.path.basename(task.dst)}")
                    return
                elif local_size < remote_size:
                    # File exists and is smaller - resume
                    offset = local_size
                    self.logger.info(f"Resuming download from {offset} bytes: {os.path.basename(task.dst)}")
                else:
                    # Local is larger - overwrite
                    self.logger.info(f"Overwriting larger local file: {os.path.basename(task.dst)}")

            def progress_callback(bytes_transferred, bytes_total):
                with self.task_lock:
                    task.bytes_done = bytes_transferred
                    task.bytes_total = bytes_total
                    if task.start_time:
                        elapsed = time.time() - task.start_time
                        if elapsed > 0:
                            task.speed = bytes_transferred / elapsed

            def check_interrupt():
                # Check for pause request
                if task.paused:
                    with self.task_lock:
                        task.status = "paused"
                    raise InterruptedError("Task paused")
                return task.interrupted

            engine.download_file(task.src, task.dst, callback=progress_callback, check_interrupt=check_interrupt, offset=offset)
        except InterruptedError as e:
            with self.task_lock:
                if task.paused:
                    task.status = "paused"
                    self.logger.info(f"Paused: {os.path.basename(task.src)}")
                else:
                    task.status = "canceled"
                    self.logger.info(f"Canceled: {os.path.basename(task.src)}")
        finally:
            engine.disconnect()

    def _get_unique_local_path(self, local_path: str) -> str:
        """Generate unique local path by adding sequence number."""
        base, ext = os.path.splitext(local_path)
        counter = 1
        new_path = f"{base}_{counter}{ext}"
        
        while os.path.exists(new_path):
            counter += 1
            new_path = f"{base}_{counter}{ext}"
        
        return new_path

    def _execute_parallel_upload(self, task: Task):
        """Execute upload task using native parallel SFTP engine."""
        def progress_callback(bytes_transferred, bytes_total):
            with self.task_lock:
                task.bytes_done = bytes_transferred
                task.bytes_total = bytes_total
                if task.start_time:
                    elapsed = time.time() - task.start_time
                    if elapsed > 0:
                        task.speed = bytes_transferred / elapsed

        def check_interrupt():
            if task.paused:
                with self.task_lock:
                    task.status = "paused"
                raise InterruptedError("Task paused")
            return task.interrupted

        p_engine = ParallelSftpEngine(
            self.site_config,
            self.logger,
            preset_name=self.parallel_upload_preset,
        )
        p_engine.upload_file(
            task.src,
            task.dst,
            callback=progress_callback,
            check_interrupt=check_interrupt,
        )

    def _execute_parallel_download(self, task: Task):
        """Execute download task using native parallel SFTP engine."""
        def progress_callback(bytes_transferred, bytes_total):
            with self.task_lock:
                task.bytes_done = bytes_transferred
                task.bytes_total = bytes_total
                if task.start_time:
                    elapsed = time.time() - task.start_time
                    if elapsed > 0:
                        task.speed = bytes_transferred / elapsed

        def check_interrupt():
            if task.paused:
                with self.task_lock:
                    task.status = "paused"
                raise InterruptedError("Task paused")
            return task.interrupted

        p_engine = ParallelSftpEngine(
            self.site_config,
            self.logger,
            preset_name=self.parallel_download_preset,
        )
        p_engine.download_file(
            task.src,
            task.dst,
            callback=progress_callback,
            check_interrupt=check_interrupt,
        )

    def _metric_preset_for_task(self, task: Task) -> str:
        """Resolve metric preset label from task engine/kind."""
        if task.engine != "parallel":
            return task.engine
        if task.kind == "upload":
            return self.parallel_upload_preset
        if task.kind == "download":
            return self.parallel_download_preset
        return self.parallel_preset

    def _execute_delete(self, task: Task):
        """Execute delete task."""
        engine = SftpEngine(self.site_config, self.logger)
        engine.connect()

        try:
            # Try to remove as file first, then as directory
            try:
                engine.remove_file(task.src)
            except:
                engine.remove_dir(task.src)
        finally:
            engine.disconnect()

    def _execute_mkdir(self, task: Task):
        """Execute mkdir task."""
        engine = SftpEngine(self.site_config, self.logger)
        engine.connect()

        try:
            engine.mkdir(task.dst)
        finally:
            engine.disconnect()

    def _execute_rename(self, task: Task):
        """Execute rename task."""
        engine = SftpEngine(self.site_config, self.logger)
        engine.connect()

        try:
            engine.rename(task.src, task.dst)
        finally:
            engine.disconnect()

    def _execute_folder_upload(self, task: Task):
        """Execute folder upload task - uploads all files as single aggregated task."""
        engine = SftpEngine(self.site_config, self.logger)
        engine.connect()
        
        try:
            self._upload_dir_recursive(engine, task, task.src, task.dst)
        except InterruptedError:
            with self.task_lock:
                if task.paused:
                    task.status = "paused"
                    self.logger.info(f"Paused folder upload: {os.path.basename(task.src)}")
                else:
                    task.status = "canceled"
                    task.end_time = time.time()
                    self.logger.info(f"Canceled folder upload: {os.path.basename(task.src)}")
        finally:
            engine.disconnect()

    def _upload_dir_recursive(self, engine: SftpEngine, task: Task, local_dir: str, remote_dir: str):
        """Recursively upload a directory, updating task progress."""
        # Create remote directory
        try:
            engine.mkdir(remote_dir)
        except:
            pass  # Directory may already exist
        
        # Helper to check for interrupts
        def check_interrupt():
            if task.paused:
                with self.task_lock:
                    task.status = "paused"
                raise InterruptedError("Task paused")
            return task.interrupted

        for name in os.listdir(local_dir):
            if check_interrupt():
                raise InterruptedError("Task interrupted")
                
            full_path = os.path.join(local_dir, name)
            remote_path = f"{remote_dir}/{name}"
            
            if os.path.isfile(full_path):
                file_size = os.path.getsize(full_path)
                
                # Smart Resume Check
                offset = 0
                skip_file = False
                try:
                    stats = engine.stat(remote_path)
                    if stats.size == file_size:
                        skip_file = True
                    elif stats.size < file_size:
                        offset = stats.size
                except:
                    pass

                if skip_file:
                    with self.task_lock:
                        task.subtask_done += 1
                        task.bytes_done += file_size
                    self.logger.info(f"[{task.subtask_done}/{task.subtask_count}] Skipped (exists): {name}")
                    continue

                with self.task_lock:
                    task.current_file = name
                
                # Upload with progress callback
                def progress_callback(bytes_transferred, bytes_total):
                    with self.task_lock:
                        # Calculate overall progress
                        base_bytes = task.bytes_done
                        task.speed = bytes_transferred / max(1, time.time() - task.start_time) if task.start_time else 0
                
                if offset > 0:
                     self.logger.info(f"Resuming file {name} from {offset}")

                engine.upload_file(full_path, remote_path, callback=progress_callback, check_interrupt=check_interrupt, offset=offset)
                
                with self.task_lock:
                    task.subtask_done += 1
                    task.bytes_done += file_size
                    # Log file completion
                self.logger.info(f"[{task.subtask_done}/{task.subtask_count}] Uploaded: {name}")
                
            elif os.path.isdir(full_path):
                # Check interrupt before recursing
                if check_interrupt(): 
                    raise InterruptedError("Task interrupted")
                self._upload_dir_recursive(engine, task, full_path, remote_path)

    def _execute_folder_download(self, task: Task):
        """Execute folder download task - downloads all files as single aggregated task."""
        engine = SftpEngine(self.site_config, self.logger)
        engine.connect()
        
        try:
            self._download_dir_recursive(engine, task, task.src, task.dst)
        except InterruptedError:
            with self.task_lock:
                if task.paused:
                    task.status = "paused"
                    self.logger.info(f"Paused folder download: {os.path.basename(task.src)}")
                else:
                    task.status = "canceled"
                    task.end_time = time.time()
                    self.logger.info(f"Canceled folder download: {os.path.basename(task.src)}")
        finally:
            engine.disconnect()

    def _download_dir_recursive(self, engine: SftpEngine, task: Task, remote_dir: str, local_dir: str):
        """Recursively download a directory, updating task progress."""
        # Create local directory
        os.makedirs(local_dir, exist_ok=True)
        
        # List remote directory
        entries = engine.list_dir(remote_dir)
        
        # Helper to check for interrupts
        def check_interrupt():
            if task.paused:
                with self.task_lock:
                    task.status = "paused"
                raise InterruptedError("Task paused")
            return task.interrupted

        for entry in entries:
            if check_interrupt():
                raise InterruptedError("Task interrupted")

            local_path = os.path.join(local_dir, entry.name)
            
            if entry.is_dir:
                self._download_dir_recursive(engine, task, entry.path, local_path)
            else:
                # Smart Resume Check
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
                    self.logger.info(f"[{task.subtask_done}/{task.subtask_count}] Skipped (exists): {entry.name}")
                    continue

                with self.task_lock:
                    task.current_file = entry.name
                
                # Download with progress callback
                def progress_callback(bytes_transferred, bytes_total):
                    with self.task_lock:
                        task.speed = bytes_transferred / max(1, time.time() - task.start_time) if task.start_time else 0
                
                if offset > 0:
                    self.logger.info(f"Resuming file {entry.name} from {offset}")

                engine.download_file(entry.path, local_path, callback=progress_callback, check_interrupt=check_interrupt, offset=offset)
                
                with self.task_lock:
                    task.subtask_done += 1
                    task.bytes_done += entry.size
                    
                self.logger.info(f"[{task.subtask_done}/{task.subtask_count}] Downloaded: {entry.name}")

    @staticmethod
    def create_upload_task(
        local_path: str,
        remote_path: str,
        file_size: int,
        engine: str = "sftp",
        auto_engine: bool = True,
        threshold: int = DEFAULT_PARALLEL_THRESHOLD_BYTES
    ) -> Task:
        """
        Create an upload task.
        
        Args:
            local_path: Local file path
            remote_path: Remote destination path
            file_size: File size in bytes
            engine: Engine to use (sftp or parallel), ignored if auto_engine=True
            auto_engine: If True, auto-select engine based on file size
            threshold: Size threshold for auto parallel selection
            
        Returns:
            Task object
        """
        if auto_engine and file_size >= threshold:
            engine = "parallel"
        return Task(
            task_id=str(uuid.uuid4()),
            kind="upload",
            engine=engine,
            src=local_path,
            dst=remote_path,
            bytes_total=file_size,
            status="pending"
        )

    @staticmethod
    def create_download_task(
        remote_path: str,
        local_path: str,
        file_size: int,
        engine: str = "sftp",
        auto_engine: bool = True,
        threshold: int = DEFAULT_PARALLEL_THRESHOLD_BYTES
    ) -> Task:
        """
        Create a download task.
        
        Args:
            remote_path: Remote file path
            local_path: Local destination path
            file_size: File size in bytes
            engine: Engine to use (sftp or parallel), ignored if auto_engine=True
            auto_engine: If True, auto-select engine based on file size
            threshold: Size threshold for auto parallel selection
            
        Returns:
            Task object
        """
        if auto_engine and file_size >= threshold:
            engine = "parallel"
        return Task(
            task_id=str(uuid.uuid4()),
            kind="download",
            engine=engine,
            src=remote_path,
            dst=local_path,
            bytes_total=file_size,
            status="pending"
        )

    @staticmethod
    def create_mkdir_task(remote_path: str, engine: str = "sftp") -> Task:
        """Create a mkdir task."""
        return Task(
            task_id=str(uuid.uuid4()),
            kind="mkdir",
            engine=engine,
            src="",
            dst=remote_path,
            bytes_total=0,
            status="pending"
        )

    @staticmethod
    def create_delete_task(remote_path: str, engine: str = "sftp") -> Task:
        """Create a delete task."""
        return Task(
            task_id=str(uuid.uuid4()),
            kind="delete",
            engine=engine,
            src=remote_path,
            dst="",
            bytes_total=0,
            status="pending"
        )

    @staticmethod
    def create_folder_upload_task(
        local_dir: str,
        remote_dir: str,
        total_files: int,
        total_bytes: int,
        engine: str = "sftp"
    ) -> Task:
        """Create a folder upload task."""
        return Task(
            task_id=str(uuid.uuid4()),
            kind="folder_upload",
            engine=engine,
            src=local_dir,
            dst=remote_dir,
            bytes_total=total_bytes,
            subtask_count=total_files,
            status="pending"
        )

    @staticmethod
    def create_folder_download_task(
        remote_dir: str,
        local_dir: str,
        total_files: int,
        total_bytes: int,
        engine: str = "sftp"
    ) -> Task:
        """Create a folder download task."""
        return Task(
            task_id=str(uuid.uuid4()),
            kind="folder_download",
            engine=engine,
            src=remote_dir,
            dst=local_dir,
            bytes_total=total_bytes,
            subtask_count=total_files,
            status="pending"
        )
