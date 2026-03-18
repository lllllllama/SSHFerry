import type { ApiListResponse, TaskActionResponse, TaskEngine, TaskItem } from './types';
import { http } from './http';

export async function listTasks(): Promise<ApiListResponse<TaskItem>> {
  const { data } = await http.get<ApiListResponse<TaskItem>>('/api/tasks');
  return data;
}

export async function createUploadTask(payload: {
  session_id: string;
  local_path: string;
  remote_path: string;
  engine: TaskEngine;
}): Promise<TaskItem> {
  const { data } = await http.post<TaskItem>('/api/tasks/upload', payload);
  return data;
}

export async function createDownloadTask(payload: {
  session_id: string;
  remote_path: string;
  local_path: string;
  engine: TaskEngine;
}): Promise<TaskItem> {
  const { data } = await http.post<TaskItem>('/api/tasks/download', payload);
  return data;
}

export async function createRemoteCopyTask(payload: {
  src_session_id: string;
  dst_session_id: string;
  src_path: string;
  dst_path: string;
  engine: TaskEngine;
}): Promise<TaskItem> {
  const { data } = await http.post<TaskItem>('/api/tasks/remote-copy', payload);
  return data;
}

async function postTaskAction(taskId: string, action: 'pause' | 'resume' | 'cancel' | 'restart') {
  const { data } = await http.post<TaskActionResponse>(`/api/tasks/${taskId}/${action}`);
  return data;
}

export function pauseTask(taskId: string): Promise<TaskActionResponse> {
  return postTaskAction(taskId, 'pause');
}

export function resumeTask(taskId: string): Promise<TaskActionResponse> {
  return postTaskAction(taskId, 'resume');
}

export function cancelTask(taskId: string): Promise<TaskActionResponse> {
  return postTaskAction(taskId, 'cancel');
}

export function restartTask(taskId: string): Promise<TaskActionResponse> {
  return postTaskAction(taskId, 'restart');
}

export async function clearFinishedTasks(): Promise<void> {
  await http.delete('/api/tasks/finished');
}
