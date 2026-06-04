import type { ApiListResponse, SiteBulkDeleteResponse, SiteResponse, SiteUpsertRequest } from './types';
import { http } from './http';

export async function listSites(): Promise<ApiListResponse<SiteResponse>> {
  const { data } = await http.get<ApiListResponse<SiteResponse>>('/api/sites');
  return data;
}

export async function createSite(payload: SiteUpsertRequest): Promise<SiteResponse> {
  const { data } = await http.post<SiteResponse>('/api/sites', payload);
  return data;
}

export async function updateSite(siteName: string, payload: SiteUpsertRequest): Promise<SiteResponse> {
  const { data } = await http.put<SiteResponse>(`/api/sites/${encodeURIComponent(siteName)}`, payload);
  return data;
}

export async function deleteSite(siteName: string): Promise<void> {
  await http.delete(`/api/sites/${encodeURIComponent(siteName)}`);
}

export async function deleteSites(siteNames: string[]): Promise<SiteBulkDeleteResponse> {
  const { data } = await http.post<SiteBulkDeleteResponse>('/api/sites/bulk-delete', { names: siteNames });
  return data;
}
