export type ChannelType = 'instagram' | 'facebook' | 'telegram';
export type DialogueStatus = 'new' | 'in_progress' | 'ordered' | 'lost';
export type SenderType = 'client' | 'agent' | 'human' | 'system';

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
}

export interface Dialogue {
  uuid: string;
  status: DialogueStatus;
  channel: ChannelType;
  client: Client;
  tags: string[];
  last_message_at: string;
  preview: string;
  unread: number;
  ai_active: boolean;
}

export interface LoginResponse {
  token: string;
  expires_at: string;
  user: User;
}
