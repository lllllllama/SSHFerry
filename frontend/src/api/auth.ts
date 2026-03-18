import type { AuthSessionResponse, HealthResponse } from './types';
import { http } from './http';

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await http.get<HealthResponse>('/api/health');
  return data;
}

export async function getAuthSession(): Promise<AuthSessionResponse> {
  const { data } = await http.get<AuthSessionResponse>('/api/auth/session');
  return data;
}
