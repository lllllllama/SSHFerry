import type { LogListResponse } from './types';
import { http } from './http';

export async function listLogs(limit = 400): Promise<LogListResponse> {
  const { data } = await http.get<LogListResponse>('/api/logs', {
    params: { limit },
  });
  return data;
}

export async function clearLogs(): Promise<void> {
  await http.delete('/api/logs');
}