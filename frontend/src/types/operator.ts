import { Message } from './chat';

export type ShiftStatus = 'active' | 'break' | 'offline';
export type TicketPriority = 'P0' | 'P1' | 'P2';

export interface OperatorProfile {
  user_id: string;
  full_name: string;
  line_id: number;
  line_code: string;
  shift_status: ShiftStatus;
  max_slots: number;
  active_slots_count: number;
}

export interface OperatorSidebarTicket {
  ticket_id: string;
  chat_id: string;
  priority: TicketPriority;
  status: 'assigned' | 'in_progress' | 'queued' | 'resolved';
  line_code?: string;
  client_name?: string | null;
  company_name?: string | null;
  last_message_preview?: string | null;
  unread_messages_count: number;
  created_at: string;
  assigned_at?: string | null;
}

export interface ClientInfo {
  company_name?: string | null;
  inn?: string | null;
  kpp?: string | null;
  phone?: string | null;
  full_name?: string | null;
  email: string;
}

export interface SimilarTicketItem {
  ticket_id: string;
  support_line: string;
  user_query: string;
  solution_text: string;
  similarity_score: number;
}

export interface CopilotSummary {
  summary: string;
  suggested_line_code?: string | null;
  suggested_response?: string | null;
  recommended_chunk_ids?: string[];
  similar_resolved_tickets?: SimilarTicketItem[];
}

export interface OperatorTicketWorkspace {
  ticket_id: string;
  chat_id: string;
  priority: TicketPriority;
  status: string;
  line_code: string;
  transfer_comment?: string | null;
  client: ClientInfo;
  copilot_summary?: CopilotSummary | null;
  messages: Message[];
}
