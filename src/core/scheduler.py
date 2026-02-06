"""Task scheduler for managing file transfer tasks."""
import logging
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Queue
from threading import Lock, Thread

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
        logger: logging.Logger | None = None
    ):
        """
        Initialize task scheduler.
        
        Args:
            site_config: Site configuration for SFTP connection
            max_workers: Maximum number of concurrent tasks
            logger: Optional logger instance
        """
        self.site_config = site_config
        self.max_workers = max_workers
        self.logger = logger or logging.getLogger(__name__)

        # Task storage
        self.tasks: dict[str, Task] = {}
        self.task_lock = Lock()

        # Task queue (priority queue)
        self.task_queue: Queue[str] = Queue()

        # Thread pool for executing tasks
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.futures: dict[str, Future] = {}

        # Scheduler thread
        self.running = False
        self.scheduler_thread: Thread | None = None

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

    def get_task(self, task_id: str) -> Task | None:
        """Get task by ID."""
        with self.task_lock:
            return self.tasks.get(task_id)

    def get_all_tasks(self) -> list[Task]:
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
                self.logger.info(f"Canceled pending task {task_id}")
                return True
            elif task.status == "running":
                # Try to cancel the future
                future = self.futures.get(task_id)
                if future and future.cancel():
                    task.status = "canceled"
                    self.logger.info(f"Canceled running task {task_id}")
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
            # Execute based on task kind
            if task.kind == "upload":
                self._execute_upload(task)
            elif task.kind == "download":
                self._execute_download(task)
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
        """Execute upload task."""
        engine = SftpEngine(self.site_config, self.logger)
        engine.connect()

        def progress_callback(bytes_transferred, bytes_total):
            with self.task_lock:
                task.bytes_done = bytes_transferred
                task.bytes_total = bytes_total

        try:
            engine.upload_file(task.src, task.dst, callback=progress_callback)
        finally:
            engine.disconnect()

    def _execute_download(self, task: Task):
        """Execute download task."""
        engine = SftpEngine(self.site_config, self.logger)
        engine.connect()

        def progress_callback(bytes_transferred, bytes_total):
            with self.task_lock:
                task.bytes_done = bytes_transferred
                task.bytes_total = bytes_total

        try:
            engine.download_file(task.src, task.dst, callback=progress_callback)
        finally:
            engine.disconnect()

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

    @staticmethod
    def create_upload_task(
        local_path: str,
        remote_path: str,
        file_size: int,
        engine: str = "sftp"
    ) -> Task:
        """
        Create an upload task.
        
        Args:
            local_path: Local file path
            remote_path: Remote destination path
            file_size: File size in bytes
            engine: Engine to use (sftp or mscp)
            
        Returns:
            Task object
        """
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
        engine: str = "sftp"
    ) -> Task:
        """
        Create a download task.
        
        Args:
            remote_path: Remote file path
            local_path: Local destination path
            file_size: File size in bytes
            engine: Engine to use (sftp or mscp)
            
        Returns:
            Task object
        """
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
