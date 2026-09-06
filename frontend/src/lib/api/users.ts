import { apiClient } from '../apiClient';

export interface UserAuditEntry {
  id: number;
  user_id: string;
  actor_user_id: string;
  action: string;
  description: string;
  created_at: string;
}

export interface OffsetPageMeta {
  page_index: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface OffsetApiResponse<T> {
  data: T;
  meta: OffsetPageMeta;
}

export async function getGlobalAuditLog(pageIndex: number = 1, pageSize: number = 20): Promise<OffsetApiResponse<UserAuditEntry[]>> {
  const res = await apiClient.get<OffsetApiResponse<UserAuditEntry[]>>('/users/audit', {
    params: {
      page_index: pageIndex,
      page_size: pageSize,
    },
  });
  return res.data;
}
