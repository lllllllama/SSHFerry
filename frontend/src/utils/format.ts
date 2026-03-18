import type { TaskItem } from '../api/types';

export const TASK_STATUS_PRIORITY: Record<string, number> = {
  running: 0,
  pending: 1,
  paused: 2,
  failed: 3,
  canceled: 4,
  skipped: 5,
  done: 6,
};

export function formatBytes(value: number): string {
  if (value <= 0) {
    return '0 B';
  }

  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = value;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  return `${size.toFixed(size >= 100 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

export function formatSpeed(value: number): string {
  if (!value) {
    return '--';
  }
  return `${formatBytes(value)}/s`;
}

export function formatTimestamp(value: number | null): string {
  if (!value) {
    return '--';
  }
  return new Date(value * 1000).toLocaleString('zh-CN', {
    hour12: false,
  });
}

export function shortId(value: string, length = 8): string {
  return value.slice(0, length);
}

export function describeTaskProgress(task: TaskItem): string {
  if (task.kind === 'folder_transfer' && task.subtask_count > 0) {
    const current = task.current_file ? ` · ${task.current_file}` : '';
    return `${task.subtask_done}/${task.subtask_count} 文件 · ${task.progress_percent.toFixed(1)}%${current}`;
  }
  if (!task.bytes_total) {
    return `${task.progress_percent.toFixed(1)}%`;
  }
  return `${task.progress_percent.toFixed(1)}% · ${formatBytes(task.bytes_done)}/${formatBytes(task.bytes_total)}`;
}

export function sortTasks(items: TaskItem[]): TaskItem[] {
  return [...items].sort((left, right) => {
    const priorityDelta = (TASK_STATUS_PRIORITY[left.status] ?? 99) - (TASK_STATUS_PRIORITY[right.status] ?? 99);
    if (priorityDelta !== 0) {
      return priorityDelta;
    }
    const leftTime = left.start_time ?? left.end_time ?? 0;
    const rightTime = right.start_time ?? right.end_time ?? 0;
    return rightTime - leftTime;
  });
}
