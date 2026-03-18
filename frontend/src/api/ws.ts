import type { LogSocketMessage, TaskSocketMessage } from './types';

const DEFAULT_WS_URL = 'ws://127.0.0.1:18080';
const TASK_SOCKET_PATH = '/api/ws/tasks';
const LOG_SOCKET_PATH = '/api/ws/logs';
const DRAG_MIME = 'application/x-sshferry-transfer';

function buildSocketUrl(path: string, token: string): string {
  const base = import.meta.env.VITE_BACKEND_WS_URL ?? DEFAULT_WS_URL;
  const url = new URL(path, `${base.replace(/\/$/, '')}/`);
  url.searchParams.set('token', token);
  return url.toString();
}

function parseSocketMessage<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function getTaskSocketUrl(token: string): string {
  return buildSocketUrl(TASK_SOCKET_PATH, token);
}

export function getLogSocketUrl(token: string): string {
  return buildSocketUrl(LOG_SOCKET_PATH, token);
}

export function parseTaskSocketMessage(raw: string): TaskSocketMessage | null {
  return parseSocketMessage<TaskSocketMessage>(raw);
}

export function parseLogSocketMessage(raw: string): LogSocketMessage | null {
  return parseSocketMessage<LogSocketMessage>(raw);
}

export function getTransferDragMime(): string {
  return DRAG_MIME;
}