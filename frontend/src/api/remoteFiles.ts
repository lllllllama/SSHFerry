import type { RemoteListResponse } from './types';
import { http } from './http';

export async function listRemoteFiles(sessionId: string, path?: string): Promise<RemoteListResponse> {
  const { data } = await http.get<RemoteListResponse>('/api/remote-files/list', {
    params: {
      session_id: sessionId,
      path,
    },
  });
  return data;
}

export async function createRemoteDirectory(sessionId: string, path: string): Promise<void> {
  await http.post('/api/remote-files/mkdir', {
    session_id: sessionId,
    path,
  });
}

export async function renameRemotePath(sessionId: string, oldPath: string, newPath: string): Promise<void> {
  await http.post('/api/remote-files/rename', {
    session_id: sessionId,
    old_path: oldPath,
    new_path: newPath,
  });
}

export async function deleteRemotePath(sessionId: string, path: string, recursive = true): Promise<void> {
  await http.post('/api/remote-files/delete', {
    session_id: sessionId,
    path,
    recursive,
  });
}
