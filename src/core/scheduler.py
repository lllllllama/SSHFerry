"""Task scheduler for managing file transfer tasks."""
import logging
import os
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Queue
from threading import Lock, Thread
from typing import Dict, List, Optional

from src.engines.mscp_engine import DEFAULT_THRESHOLD_BYTES, MscpEngine
from src.engines.sftp_engine import SftpEngine
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
        mscp_preset: str = "low",
        mscp_threshold: int = DEFAULT_THRESHOLD_BYTES,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize task scheduler.
        
        Args:
            site_config: Site configuration for SFTP connection
            max_workers: Maximum number of concurrent tasks
            mscp_preset: MSCP acceleration preset (low/medium/high)
            mscp_threshold: File size threshold for auto MSCP (bytes)
            logger: Optional logger instance
        """
        self.site_config = site_config
        self.max_workers = max_workers
        self.mscp_preset = mscp_preset
        self.mscp_threshold = mscp_threshold
        self.logger = logger or logging.getLogger(__name__)

        # Task storage
        self.tasks: Dict[str, Task] = {}
        self.task_lock = Lock()

        # Task queue (priority queue)
        self.task_queue: Queue[str] = Queue()

        # Thread pool for executing tasks
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.futures: Dict[str, Future] = {}

        # Scheduler thread
        self.running = False
        self.scheduler_thread: Optional[Thread] = None

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
            self.task_queue.put(task.task_id)

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

        return False

    def _scheduler_loop(self):
        """Main scheduler loop that processes tasks from queue."""
        while self.running:
            try:
                # Get next task from queue (with timeout to allow checking self.running)
                if not self.task_queue.empty():
                    task_id = self.task_queue.get(timeout=0.5)

                    with self.task_lock:
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
                if task.engine == "mscp":
                    self._execute_mscp_upload(task)
                else:
                    self._execute_upload(task)
            elif task.kind == "download":
                if task.engine == "mscp":
                    self._execute_mscp_download(task)
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
                task.status = "done"
                task.bytes_done = task.bytes_total

            log_task_event(
                self.logger,
                task.task_id,
                task.engine,
                task.kind,
                "done",
                bytes_done=task.bytes_total,
                bytes_total=task.bytes_total
            )

        except SSHFerryError as e:
            with self.task_lock:
                task.status = "failed"
                task.error_code = e.code
                task.error_message = e.message

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
                task.error_code = ErrorCode.UNKNOWN_ERROR
                task.error_message = str(e)

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
                else:
                    # File exists but different size - rename with sequence
                    task.dst = self._get_unique_remote_path(engine, original_dst)
                    self.logger.info(f"Renamed: {original_dst} -> {task.dst}")
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
                return task.interrupted

            engine.upload_file(task.src, task.dst, callback=progress_callback, check_interrupt=check_interrupt)
        except InterruptedError:
            with self.task_lock:
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
                else:
                    # File exists but different size - rename with sequence
                    task.dst = self._get_unique_local_path(task.dst)
                    self.logger.info(f"Local renamed: {task.dst}")

            def progress_callback(bytes_transferred, bytes_total):
                with self.task_lock:
                    task.bytes_done = bytes_transferred
                    task.bytes_total = bytes_total
                    if task.start_time:
                        elapsed = time.time() - task.start_time
                        if elapsed > 0:
                            task.speed = bytes_transferred / elapsed

            def check_interrupt():
                return task.interrupted

            engine.download_file(task.src, task.dst, callback=progress_callback, check_interrupt=check_interrupt)
        except InterruptedError:
            with self.task_lock:
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

    def _execute_mscp_upload(self, task: Task):
        """Execute upload task using MSCP engine."""
        checkpoint_dir = os.path.join(
            os.path.expanduser("~"), ".sshferry", "checkpoints"
        )
        engine = MscpEngine(self.site_config, preset_name=self.mscp_preset, logger=self.logger)
        
        if not engine.is_available():
            self.logger.warning("MSCP not available, falling back to SFTP")
            self._execute_upload(task)
            return
        
        exit_code = engine.upload(task.src, task.dst, checkpoint_dir=checkpoint_dir)
        if exit_code != 0:
            raise SSHFerryError(
                ErrorCode.MSCP_EXIT_NONZERO,
                f"mscp exited with code {exit_code}"
            )

    def _execute_mscp_download(self, task: Task):
        """Execute download task using MSCP engine."""
        checkpoint_dir = os.path.join(
            os.path.expanduser("~"), ".sshferry", "checkpoints"
        )
        engine = MscpEngine(self.site_config, preset_name=self.mscp_preset, logger=self.logger)
        
        if not engine.is_available():
            self.logger.warning("MSCP not available, falling back to SFTP")
            self._execute_download(task)
            return
        
        exit_code = engine.download(task.src, task.dst, checkpoint_dir=checkpoint_dir)
        if exit_code != 0:
            raise SSHFerryError(
                ErrorCode.MSCP_EXIT_NONZERO,
                f"mscp exited with code {exit_code}"
            )

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
        finally:
            engine.disconnect()

    def _upload_dir_recursive(self, engine: SftpEngine, task: Task, local_dir: str, remote_dir: str):
        """Recursively upload a directory, updating task progress."""
        # Create remote directory
        try:
            engine.mkdir(remote_dir)
        except:
            pass  # Directory may already exist
        
        for name in os.listdir(local_dir):
            full_path = os.path.join(local_dir, name)
            remote_path = f"{remote_dir}/{name}"
            
            if os.path.isfile(full_path):
                file_size = os.path.getsize(full_path)
                
                with self.task_lock:
                    task.current_file = name
                
                # Upload with progress callback
                def progress_callback(bytes_transferred, bytes_total):
                    with self.task_lock:
                        # Calculate overall progress
                        base_bytes = task.bytes_done
                        task.speed = bytes_transferred / max(1, time.time() - task.start_time) if task.start_time else 0
                
                engine.upload_file(full_path, remote_path, callback=progress_callback)
                
                with self.task_lock:
                    task.subtask_done += 1
                    task.bytes_done += file_size
                    # Log file completion
                self.logger.info(f"[{task.subtask_done}/{task.subtask_count}] Uploaded: {name}")
                
            elif os.path.isdir(full_path):
                self._upload_dir_recursive(engine, task, full_path, remote_path)

    def _execute_folder_download(self, task: Task):
        """Execute folder download task - downloads all files as single aggregated task."""
        engine = SftpEngine(self.site_config, self.logger)
        engine.connect()
        
        try:
            self._download_dir_recursive(engine, task, task.src, task.dst)
        finally:
            engine.disconnect()

    def _download_dir_recursive(self, engine: SftpEngine, task: Task, remote_dir: str, local_dir: str):
        """Recursively download a directory, updating task progress."""
        # Create local directory
        os.makedirs(local_dir, exist_ok=True)
        
        # List remote directory
        entries = engine.list_dir(remote_dir)
        
        for entry in entries:
            local_path = os.path.join(local_dir, entry.name)
            
            if entry.is_dir:
                self._download_dir_recursive(engine, task, entry.path, local_path)
            else:
                with self.task_lock:
                    task.current_file = entry.name
                
                # Download with progress callback
                def progress_callback(bytes_transferred, bytes_total):
                    with self.task_lock:
                        task.speed = bytes_transferred / max(1, time.time() - task.start_time) if task.start_time else 0
                
                engine.download_file(entry.path, local_path, callback=progress_callback)
                
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
        threshold: int = DEFAULT_THRESHOLD_BYTES
    ) -> Task:
        """
        Create an upload task.
        
        Args:
            local_path: Local file path
            remote_path: Remote destination path
            file_size: File size in bytes
            engine: Engine to use (sftp or mscp), ignored if auto_engine=True
            auto_engine: If True, auto-select engine based on file size
            threshold: Size threshold for auto MSCP selection
            
        Returns:
            Task object
        """
        if auto_engine and file_size >= threshold:
            engine = "mscp"
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
        threshold: int = DEFAULT_THRESHOLD_BYTES
    ) -> Task:
        """
        Create a download task.
        
        Args:
            remote_path: Remote file path
            local_path: Local destination path
            file_size: File size in bytes
            engine: Engine to use (sftp or mscp), ignored if auto_engine=True
            auto_engine: If True, auto-select engine based on file size
            threshold: Size threshold for auto MSCP selection
            
        Returns:
            Task object
        """
        if auto_engine and file_size >= threshold:
            engine = "mscp"
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
