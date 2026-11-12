export type ChannelType = 'instagram' | 'facebook' | 'telegram';
export type DialogueStatus = 'new' | 'in_progress' | 'ordered' | 'lost';
export type SenderType = 'client' | 'agent' | 'human' | 'system';
export type MessageStatus = 'queued' | 'sent' | 'delivered' | 'read' | 'failed';
export type MessageDirection = 'inbound' | 'outbound';

export interface Attachment {
  url: string;
  type: string; // MIME, напр. 'image/png'
  name: string;
  size: number; // байти
}

export interface User {
  uuid: string;
  email: string;
  display_name: string;
  role: string;
}

export interface Client {
  uuid: string;
  name: string;
  instagram_handle: string | null;
  phone: string | null;
}

export interface Message {
  uuid: string;
  sender_type: SenderType;
  content: string;
  created_at: string;
  status?: MessageStatus;
  direction?: MessageDirection;
  attachments?: Attachment[];
}

export interface Dialogue {
  uuid: string;
  status: DialogueStatus;
  channel: ChannelType;
  client: Client;
  tags: string[];
  last_message_at: string;
  preview: string;
  unread_count: number;
  ai_active: boolean;
  /** Стан підключення каналу (токен Meta тощо); `expired` → відповіді не доходять. */
  webhook_status?: 'active' | 'expired';
  /** Останнє вхідне від клієнта — для 24-годинного вікна Meta. Якщо нема — береться з повідомлень. */
  last_inbound_at?: string;
}

export interface LoginResponse {
  token: string;
  expires_at: string;
  user: User;
}

// --- AI (Phase 3): відповіді /api/dialogues/{uuid}/ai/* — поля snake_case, як у JSON бекенда ---

export type AIIntent = 'booking' | 'question' | 'escalate' | 'unknown';

export type AISuggestionStatus = 'pending' | 'approved' | 'rejected' | 'expired';

export interface AIProposedBooking {
  tool: string;
  service_name: string;
  date: string;
  time: string;
  arguments: Record<string, unknown>;
  result?: Record<string, unknown>;
}

export interface AISuggestion {
  uuid: string;
  dialogue_uuid: string;
  content: string;
  intent: AIIntent;
  proposed_booking: AIProposedBooking | null;
  status: AISuggestionStatus;
  created_at: string;
  resolved_at?: string;
  resolved_by_user_id?: number;
}

export interface AIRespondResult {
  suggestion_uuid: string;
  content: string;
  intent: AIIntent;
  needs_approval: boolean;
  proposed_booking: AIProposedBooking | null;
}

export interface AIApproveResult {
  message_uuid: string;
  suggestion_uuid: string;
  status: string;
}

export interface AIRejectResult {
  suggestion_uuid: string;
  status: string;
}
