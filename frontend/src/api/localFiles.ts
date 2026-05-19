import type { ApiListResponse, LocalDrive, LocalListResponse, LocalSearchResponse, LocalStatResponse } from './types';
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

export async function searchLocalFiles(path: string, query: string): Promise<LocalSearchResponse> {
  const { data } = await http.get<LocalSearchResponse>('/api/local-files/search', {
    params: {
      path,
      q: query,
    },
  });
  return data;
}

export async function statLocalPath(path: string): Promise<LocalStatResponse> {
  const { data } = await http.get<LocalStatResponse>('/api/local-files/stat', {
    params: { path },
  });
  return data;
}
