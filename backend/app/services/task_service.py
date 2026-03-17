"""Task orchestration service for backend APIs."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Any
import uuid

from fastapi import HTTPException, status

from backend.app.schemas.tasks import (
    TaskActionResponse,
    TaskCreateDownloadRequest,
    TaskCreateRemoteCopyRequest,
    TaskCreateUploadRequest,
    TaskResponse,
)
from backend.app.services.app_state import AppState
from src.shared.models import SiteConfig, Task


DEFAULT_PARALLEL_THRESHOLD_BYTES = 50 * 1024 * 1024


class TaskService:
    """Facade around TaskScheduler for REST APIs."""

    def __init__(self, app_state: AppState):
        self.app_state = app_state

    def list_tasks(self) -> list[TaskResponse]:
        scheduler = self._require_scheduler()
        tasks = scheduler.get_all_tasks()
        return [self._to_response(task) for task in tasks]

    def create_upload(self, payload: TaskCreateUploadRequest) -> TaskResponse:
        scheduler = self._require_scheduler()
        site = self._require_session(payload.session_id)
        local_path = self._resolve_local_path(payload.local_path, require_exists=True)
        remote_path = self._require_non_blank_remote_path(payload.remote_path)

        if local_path.is_dir():
            total_files, total_bytes = self._scan_local_dir(local_path)
            task = Task(
                task_id=str(uuid.uuid4()),
                kind='folder_transfer',
                engine='sftp',
                src=str(local_path),
                dst=remote_path,
                bytes_total=total_bytes,
                subtask_count=max(1, total_files),
                src_endpoint_type='local',
                dst_endpoint_type='remote',
                dst_session_id=payload.session_id,
                dst_site_snapshot=site,
                dst_display_name=site.name,
                status='pending',
            )
        else:
            file_size = int(local_path.stat().st_size)
            task = Task(
                task_id=str(uuid.uuid4()),
                kind='file_transfer',
                engine=self._resolve_file_engine(site, file_size, payload.engine, scheduler),
                src=str(local_path),
                dst=remote_path,
                bytes_total=file_size,
                src_endpoint_type='local',
                dst_endpoint_type='remote',
                dst_session_id=payload.session_id,
                dst_site_snapshot=site,
                dst_display_name=site.name,
                status='pending',
            )

        scheduler.add_task(task)
        return self._to_response(task)

    def create_download(self, payload: TaskCreateDownloadRequest) -> TaskResponse:
        scheduler = self._require_scheduler()
        site = self._require_session(payload.session_id)
        remote_path = self._require_non_blank_remote_path(payload.remote_path)
        local_path = self._resolve_local_path(payload.local_path, require_exists=False)
        engine = self._build_remote_engine(site)
        try:
            engine.connect()
            remote_entry = engine.stat(remote_path)
            if remote_entry.is_dir:
                total_files, total_bytes = self._scan_remote_dir(engine, remote_path)
                task = Task(
                    task_id=str(uuid.uuid4()),
                    kind='folder_transfer',
                    engine='sftp',
                    src=remote_path,
                    dst=str(local_path),
                    bytes_total=total_bytes,
                    subtask_count=max(1, total_files),
                    src_endpoint_type='remote',
                    dst_endpoint_type='local',
                    src_session_id=payload.session_id,
                    src_site_snapshot=site,
                    src_display_name=site.name,
                    status='pending',
                )
            else:
                task = Task(
                    task_id=str(uuid.uuid4()),
                    kind='file_transfer',
                    engine=self._resolve_file_engine(site, int(remote_entry.size), payload.engine, scheduler),
                    src=remote_path,
                    dst=str(local_path),
                    bytes_total=int(remote_entry.size),
                    src_endpoint_type='remote',
                    dst_endpoint_type='local',
                    src_session_id=payload.session_id,
                    src_site_snapshot=site,
                    src_display_name=site.name,
                    status='pending',
                )
        finally:
            self._disconnect_quietly(engine)

        scheduler.add_task(task)
        return self._to_response(task)

    def create_remote_copy(self, payload: TaskCreateRemoteCopyRequest) -> TaskResponse:
        scheduler = self._require_scheduler()
        src_site = self._require_session(payload.src_session_id)
        dst_site = self._require_session(payload.dst_session_id)
        src_path = self._require_non_blank_remote_path(payload.src_path)
        dst_path = self._require_non_blank_remote_path(payload.dst_path)
        engine = self._build_remote_engine(src_site)
        try:
            engine.connect()
            remote_entry = engine.stat(src_path)
            if remote_entry.is_dir:
                total_files, total_bytes = self._scan_remote_dir(engine, src_path)
                task = Task(
                    task_id=str(uuid.uuid4()),
                    kind='folder_transfer',
                    engine='sftp',
                    src=src_path,
                    dst=dst_path,
                    bytes_total=total_bytes,
                    subtask_count=max(1, total_files),
                    src_endpoint_type='remote',
                    dst_endpoint_type='remote',
                    src_session_id=payload.src_session_id,
                    dst_session_id=payload.dst_session_id,
                    src_site_snapshot=src_site,
                    dst_site_snapshot=dst_site,
                    src_display_name=src_site.name,
                    dst_display_name=dst_site.name,
                    status='pending',
                )
            else:
                task = Task(
                    task_id=str(uuid.uuid4()),
                    kind='file_transfer',
                    engine=self._resolve_remote_copy_engine(payload.engine),
                    src=src_path,
                    dst=dst_path,
                    bytes_total=int(remote_entry.size),
                    src_endpoint_type='remote',
                    dst_endpoint_type='remote',
                    src_session_id=payload.src_session_id,
                    dst_session_id=payload.dst_session_id,
                    src_site_snapshot=src_site,
                    dst_site_snapshot=dst_site,
                    src_display_name=src_site.name,
                    dst_display_name=dst_site.name,
                    status='pending',
                )
        finally:
            self._disconnect_quietly(engine)

        scheduler.add_task(task)
        return self._to_response(task)

    def pause_task(self, task_id: str) -> TaskActionResponse:
        scheduler = self._require_scheduler()
        return self._run_control_action(scheduler, task_id, action='pause', runner=scheduler.pause_task)

    def resume_task(self, task_id: str) -> TaskActionResponse:
        scheduler = self._require_scheduler()
        return self._run_control_action(scheduler, task_id, action='resume', runner=scheduler.resume_task)

    def cancel_task(self, task_id: str) -> TaskActionResponse:
        scheduler = self._require_scheduler()
        return self._run_control_action(scheduler, task_id, action='cancel', runner=scheduler.cancel_task)

    def restart_task(self, task_id: str) -> TaskActionResponse:
        scheduler = self._require_scheduler()
        return self._run_control_action(scheduler, task_id, action='restart', runner=scheduler.restart_task)

    def clear_finished_tasks(self) -> int:
        scheduler = self._require_scheduler()
        removed = 0
        with self._task_lock(scheduler):
            task_ids = [task_id for task_id, task in scheduler.tasks.items() if task.is_finished]
            for task_id in task_ids:
                del scheduler.tasks[task_id]
                scheduler.queued_task_ids.discard(task_id)
                scheduler.active_task_ids.discard(task_id)
                scheduler.futures.pop(task_id, None)
                removed += 1
            scheduler.task_queue = [task_id for task_id in scheduler.task_queue if task_id in scheduler.tasks]
        return removed

    def _run_control_action(self, scheduler: Any, task_id: str, *, action: str, runner) -> TaskActionResponse:
        task = scheduler.get_task(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task '{task_id}' not found",
            )
        changed = runner(task_id)
        if not changed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot {action} task '{task_id}' while status is '{task.status}'",
            )
        refreshed = scheduler.get_task(task_id) or task
        return TaskActionResponse(task_id=task_id, action=action, status=refreshed.status)

    def _require_scheduler(self):
        try:
            return self.app_state.require_scheduler()
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    def _require_session(self, session_id: str) -> SiteConfig:
        with self._session_guard():
            site = self.app_state.remote_sessions.get(session_id)
            if site is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session '{session_id}' not found",
                )
            return replace(site)

    def _session_guard(self):
        lock = getattr(self.app_state, 'session_lock', None)
        return lock if lock is not None else nullcontext()

    @staticmethod
    def _resolve_local_path(raw_path: str, *, require_exists: bool) -> Path:
        normalized = raw_path.strip()
        if not normalized:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Local path must not be blank',
            )
        path = Path(normalized).expanduser().resolve(strict=False)
        if require_exists and not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'Path not found: {raw_path}',
            )
        return path

    @staticmethod
    def _require_non_blank_remote_path(path: str) -> str:
        normalized = path.strip()
        if not normalized:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Remote path must not be blank',
            )
        return normalized

    @staticmethod
    def _resolve_file_engine(site: SiteConfig, file_size: int, requested_engine: str, scheduler: Any) -> str:
        if requested_engine == 'parallel':
            return 'parallel'
        if requested_engine == 'scp':
            return 'scp'
        if requested_engine == 'sftp':
            return 'parallel' if file_size >= TaskService._parallel_threshold(scheduler) else 'sftp'

        base_protocol = site.default_transfer_protocol if site.default_transfer_protocol in ('sftp', 'scp') else 'sftp'
        if base_protocol != 'scp' and file_size >= TaskService._parallel_threshold(scheduler):
            return 'parallel'
        return base_protocol

    @staticmethod
    def _resolve_remote_copy_engine(requested_engine: str) -> str:
        if requested_engine in ('sftp', 'scp', 'parallel'):
            return requested_engine
        return 'sftp'

    @staticmethod
    def _parallel_threshold(scheduler: Any) -> int:
        threshold = getattr(scheduler, 'parallel_threshold', DEFAULT_PARALLEL_THRESHOLD_BYTES)
        return int(threshold) if isinstance(threshold, int) else DEFAULT_PARALLEL_THRESHOLD_BYTES

    @staticmethod
    def _scan_local_dir(path: Path) -> tuple[int, int]:
        total_files = 0
        total_bytes = 0
        for child in path.iterdir():
            if child.is_file():
                total_files += 1
                total_bytes += int(child.stat().st_size)
            elif child.is_dir():
                sub_files, sub_bytes = TaskService._scan_local_dir(child)
                total_files += sub_files
                total_bytes += sub_bytes
        return total_files, total_bytes

    @staticmethod
    def _scan_remote_dir(engine, path: str) -> tuple[int, int]:
        total_files = 0
        total_bytes = 0
        for entry in engine.list_dir(path):
            if entry.is_dir:
                sub_files, sub_bytes = TaskService._scan_remote_dir(engine, entry.path)
                total_files += sub_files
                total_bytes += sub_bytes
            else:
                total_files += 1
                total_bytes += int(entry.size)
        return total_files, total_bytes

    @staticmethod
    def _to_response(task: Task) -> TaskResponse:
        error_code = task.error_code.name if task.error_code is not None else None
        return TaskResponse(
            task_id=task.task_id,
            kind=task.kind,
            engine=task.engine,
            status=task.status,
            src=task.src,
            dst=task.dst,
            src_endpoint_type=task.src_endpoint_type,
            dst_endpoint_type=task.dst_endpoint_type,
            src_session_id=task.src_session_id,
            dst_session_id=task.dst_session_id,
            src_display_name=task.src_display_name,
            dst_display_name=task.dst_display_name,
            src_label=task.src_endpoint.label,
            dst_label=task.dst_endpoint.label,
            bytes_total=task.bytes_total,
            bytes_done=task.bytes_done,
            progress_percent=task.progress_percent,
            speed=task.speed,
            retries=task.retries,
            error_code=error_code,
            error_message=task.error_message,
            start_time=task.start_time,
            end_time=task.end_time,
            interrupted=task.interrupted,
            paused=task.paused,
            skipped=task.skipped,
            subtask_count=task.subtask_count,
            subtask_done=task.subtask_done,
            current_file=task.current_file,
            is_finished=task.is_finished,
        )

    @staticmethod
    def _disconnect_quietly(engine) -> None:
        try:
            engine.disconnect()
        except Exception:
            pass

    @staticmethod
    def _task_lock(scheduler):
        lock = getattr(scheduler, 'task_lock', None)
        return lock if lock is not None else nullcontext()

    @staticmethod
    def _build_remote_engine(site: SiteConfig):
        try:
            from src.engines.sftp_engine import SftpEngine
        except ModuleNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f'Remote task dependency unavailable: {exc}',
            ) from exc
        return SftpEngine(site)
