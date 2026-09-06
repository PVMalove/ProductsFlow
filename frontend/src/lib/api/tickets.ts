export interface TicketMessageView {
  id: string;
  author_id: string | null;
  body: string;
  created_at: string;
  is_system: boolean;
  is_deleted: boolean;
}

export interface TicketView {
  id: string;
  author_id: string | null;
  subject: string;
  status: string;
  created_at: string;
}

export interface TicketDetailView {
  id: string;
  author_id: string | null;
  subject: string;
  status: string;
  created_at: string;
  messages: TicketMessageView[];
}

import { apiClient } from '../apiClient';
import { ApiResponse } from './products';

export async function createTicket(subject: string, first_message: string): Promise<TicketDetailView> {
  const res = await apiClient.post<ApiResponse<TicketDetailView>>('/v1/tickets', {
    subject,
    first_message,
  });
  return res.data.data;
}
