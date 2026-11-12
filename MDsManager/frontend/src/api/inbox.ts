import type { Attachment, ChannelType, Dialogue, DialogueStatus, Message, MessageStatus } from '../types';
import { api } from './client';

/** Повідомлення так, як його віддає бекенд (`MessageOut`). */
export interface ApiMessage {
  id: number;
  uuid: string;
  sender_type: Message['sender_type'];
  content: string;
  direction: 'inbound' | 'outbound';
  status: MessageStatus;
  attachments: Attachment[] | null;
  created_at: string;
}

/** Діалог так, як його віддає бекенд (`DialogueOut`). */
export interface ApiDialogue {
  uuid: string;
  status: DialogueStatus;
  last_message_at: string | null;
  client: { uuid: string; name: string; instagram_handle: string | null; phone: string | null };
  channel: { uuid: string; channel_type: ChannelType; account_name: string };
  tags: string[];
  last_message: ApiMessage | null;
  unread_count: number;
  last_inbound_at: string | null;
  webhook_status: 'active' | 'error' | 'expired' | 'inactive';
  ai_active: boolean;
}

export function toMessage(m: ApiMessage): Message {
  return {
    uuid: m.uuid,
    sender_type: m.sender_type,
    content: m.content,
    created_at: m.created_at,
    direction: m.direction,
    status: m.status,
    attachments: m.attachments ?? undefined,
  };
}

export function previewOf(m: { content: string; attachments?: Attachment[] | null } | null | undefined): string {
  if (!m) return '';
  if (m.content) return m.content;
  return m.attachments?.length ? '📎 Вкладення' : '';
}

export function toDialogue(d: ApiDialogue): Dialogue {
  return {
    uuid: d.uuid,
    status: d.status,
    channel: d.channel.channel_type,
    client: d.client,
    tags: d.tags,
    last_message_at: d.last_message_at ?? d.last_message?.created_at ?? new Date(0).toISOString(),
    preview: previewOf(d.last_message),
    unread_count: d.unread_count,
    ai_active: d.ai_active,
    // інтерфейс показує банер лише для «прострочено»; error/inactive — Фаза 2.5
    webhook_status: d.webhook_status === 'expired' ? 'expired' : 'active',
    last_inbound_at: d.last_inbound_at ?? undefined,
  };
}

export async function fetchDialogues(): Promise<Dialogue[]> {
  const { data } = await api.get<{ items: ApiDialogue[]; total: number }>('/api/dialogues', {
    params: { limit: 200 },
  });
  return data.items.map(toDialogue);
}

export async function fetchMessages(dialogueUuid: string): Promise<Message[]> {
  const { data } = await api.get<ApiMessage[]>(`/api/dialogues/${dialogueUuid}/messages`, {
    params: { limit: 500 },
  });
  return data.map(toMessage);
}

export async function postMessage(dialogueUuid: string, text: string): Promise<Message> {
  const { data } = await api.post<ApiMessage>(`/api/dialogues/${dialogueUuid}/messages`, { text });
  return toMessage(data);
}

// --- лише для розробки (бекенд з MOCK_META=true) ---

export const devApi = {
  simulateInbound: (body: { client_name: string; username: string; text: string; channel: 'instagram' | 'facebook' }) =>
    api.post<{ dialogue_uuid: string; message_uuid: string }>('/api/_test/simulate_inbound', body),
  simulateAttachment: (dialogue_uuid: string) =>
    api.post<{ message_uuid: string; attachment_url: string }>('/api/_test/simulate_attachment', { dialogue_uuid }),
  triggerFailure: (dialogue_uuid: string, text: string) =>
    api.post<{ message_uuid: string; queue_uuid: string }>('/api/_test/trigger_outbound_failure', {
      dialogue_uuid,
      text,
    }),
};
