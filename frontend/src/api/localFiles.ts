import type { ApiListResponse, LocalDrive, LocalListResponse } from './types';
import { http } from './http';

export async function listLocalDrives(): Promise<ApiListResponse<LocalDrive>> {
  const { data } = await http.get<ApiListResponse<LocalDrive>>('/api/local-files/drives');
  return data;
}

export async function listLocalFiles(path: string): Promise<LocalListResponse> {
  const { data } = await http.get<LocalListResponse>('/api/local-files/list', {
    params: { path },
  });
  return data;
}
