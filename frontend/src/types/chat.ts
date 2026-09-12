export type MessageType = 'user' | 'assistant' | 'thinking' | 'system';

export interface Citation {
  id: string;
  title: string;
  sectionPath?: string;
  excerpt?: string;
  url?: string;
}

export type MessageSenderType = 'client' | 'bot' | 'operator' | 'system' | 'admin';

export interface Message {
  id: string;
  ticket_id?: string;
  content: string;
  type: MessageType;
  sender_type?: MessageSenderType;
  sender_name?: string;
  sender_role?: string;
  timestamp: string;
  actions: ('copy' | 'edit' | 'regenerate' | 'thumbs_up' | 'thumbs_down')[];
  citations?: Citation[];
  needsFeedbackButtons?: boolean;
  statusText?: string;
  isStreaming?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  category?: string;
  createdAt: string;
  updatedAt: string;
  status: 'active' | 'resolved' | 'escalated_to_operator' | 'moderation_closed';
  messages: Message[];
}

export interface SupportLine {
  id: string;
  name: string;
  count: number;
  description: string;
}


export interface QuickPrompt {
  id: number;
  label: string;
  prompt: string;
  category: string;
}
