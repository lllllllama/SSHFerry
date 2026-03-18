import type { TaskSocketMessage } from './types';

const DEFAULT_WS_URL = 'ws://127.0.0.1:18080';
const TASK_SOCKET_PATH = '/api/ws/tasks';
const DRAG_MIME = 'application/x-sshferry-transfer';

export function getTaskSocketUrl(token: string): string {
  const base = import.meta.env.VITE_BACKEND_WS_URL ?? DEFAULT_WS_URL;
  const url = new URL(TASK_SOCKET_PATH, `${base.replace(/\/$/, '')}/`);
  url.searchParams.set('token', token);
  return url.toString();
}

export function parseTaskSocketMessage(raw: string): TaskSocketMessage | null {
  try {
    return JSON.parse(raw) as TaskSocketMessage;
  } catch {
    return null;
  }
}

export function getTransferDragMime(): string {
  return DRAG_MIME;
}
