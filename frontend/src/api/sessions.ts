import type {
  ApiListResponse,
  ConnectionCheckRequest,
  ConnectionCheckResponse,
  SessionCloseRequest,
  SessionOpenRequest,
  SessionResponse,
} from './types';
import { http } from './http';

export async function checkConnection(payload: ConnectionCheckRequest): Promise<ConnectionCheckResponse> {
  const { data } = await http.post<ConnectionCheckResponse>('/api/connections/check', payload);
  return data;
}

export async function listSessions(): Promise<ApiListResponse<SessionResponse>> {
  const { data } = await http.get<ApiListResponse<SessionResponse>>('/api/sessions');
  return data;
}

export async function openSession(payload: SessionOpenRequest): Promise<SessionResponse> {
  const { data } = await http.post<SessionResponse>('/api/sessions/open', payload);
  return data;
}

export async function closeSession(payload: SessionCloseRequest): Promise<void> {
  await http.post('/api/sessions/close', payload);
}
