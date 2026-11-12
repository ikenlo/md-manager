import { create } from 'zustand';
import type { Dialogue, DialogueStatus, Message, MessageStatus } from '../types';

export type InboxFilter = 'all' | 'new' | 'in_progress' | 'ordered' | 'unread';

export const STATUS_LABEL: Record<DialogueStatus, string> = {
  new: 'Новий',
  in_progress: 'В роботі',
  ordered: 'Записано',
  lost: 'Втрачено',
};

const byLastDesc = (a: Dialogue, b: Dialogue) => b.last_message_at.localeCompare(a.last_message_at);

let localSeq = 0;
const localId = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `local-${Date.now()}-${++localSeq}`;

interface InboxState {
  dialogues: Dialogue[];
  activeDialogueUuid: string | null;
  messagesByDialogue: Record<string, Message[]>;
  isLoading: boolean;
  filter: InboxFilter;
  search: string;

  /** Opens a dialogue (null — back to the list on mobile) and marks it read locally. */
  selectDialogue: (uuid: string | null) => void;
  /**
   * Adds an operator message locally. Phase 1.5: nothing is sent yet, so it stays `queued`
   * until Phase 2's outbound queue reports a status via `setMessageStatus`.
   */
  sendMessage: (uuid: string, text: string) => void;
  /** Incoming message (future WebSocket). Bumps unread unless the dialogue is open. */
  appendIncomingMessage: (dialogueUuid: string, message: Message) => void;
  setMessageStatus: (dialogueUuid: string, messageUuid: string, status: MessageStatus) => void;
  /** Replaces the dialogue list (future sync); optionally messages too. */
  setDialogues: (dialogues: Dialogue[], messages?: Record<string, Message[]>) => void;
  upsertDialogue: (dialogue: Dialogue) => void;
  toggleAi: (uuid: string) => void;
  setFilter: (f: InboxFilter) => void;
  setSearch: (s: string) => void;
}

export const useInboxStore = create<InboxState>((set, get) => ({
  dialogues: [],
  activeDialogueUuid: null,
  messagesByDialogue: {},
  isLoading: false,
  filter: 'all',
  search: '',

  selectDialogue: (uuid) =>
    set((s) => ({
      activeDialogueUuid: uuid,
      dialogues: uuid ? s.dialogues.map((d) => (d.uuid === uuid ? { ...d, unread_count: 0 } : d)) : s.dialogues,
    })),

  sendMessage(uuid, text) {
    const content = text.trim();
    if (!content || !get().dialogues.some((d) => d.uuid === uuid)) return;
    const now = new Date().toISOString();
    const msg: Message = {
      uuid: localId(),
      sender_type: 'human',
      direction: 'outbound',
      status: 'queued',
      content,
      created_at: now,
    };
    set((s) => ({
      messagesByDialogue: { ...s.messagesByDialogue, [uuid]: [...(s.messagesByDialogue[uuid] ?? []), msg] },
      dialogues: s.dialogues
        .map((d) =>
          d.uuid === uuid
            ? { ...d, preview: content, last_message_at: now, status: d.status === 'new' ? ('in_progress' as const) : d.status }
            : d,
        )
        .sort(byLastDesc),
    }));
  },

  appendIncomingMessage(dialogueUuid, message) {
    set((s) => {
      const list = s.messagesByDialogue[dialogueUuid] ?? [];
      if (list.some((m) => m.uuid === message.uuid)) return s;
      const open = s.activeDialogueUuid === dialogueUuid;
      const inbound = message.direction === 'inbound' || message.sender_type === 'client';
      return {
        messagesByDialogue: { ...s.messagesByDialogue, [dialogueUuid]: [...list, message] },
        dialogues: s.dialogues
          .map((d) =>
            d.uuid === dialogueUuid
              ? {
                  ...d,
                  preview: message.content,
                  last_message_at: message.created_at,
                  last_inbound_at: inbound ? message.created_at : d.last_inbound_at,
                  unread_count: inbound && !open ? d.unread_count + 1 : d.unread_count,
                }
              : d,
          )
          .sort(byLastDesc),
      };
    });
  },

  setMessageStatus: (dialogueUuid, messageUuid, status) =>
    set((s) => ({
      messagesByDialogue: {
        ...s.messagesByDialogue,
        [dialogueUuid]: (s.messagesByDialogue[dialogueUuid] ?? []).map((m) =>
          m.uuid === messageUuid ? { ...m, status } : m,
        ),
      },
    })),

  setDialogues: (dialogues, messages) =>
    set((s) => ({
      dialogues: [...dialogues].sort(byLastDesc),
      messagesByDialogue: messages ?? s.messagesByDialogue,
      isLoading: false,
    })),

  upsertDialogue: (dialogue) =>
    set((s) => {
      const exists = s.dialogues.some((d) => d.uuid === dialogue.uuid);
      const next = exists ? s.dialogues.map((d) => (d.uuid === dialogue.uuid ? dialogue : d)) : [...s.dialogues, dialogue];
      return { dialogues: next.sort(byLastDesc) };
    }),

  toggleAi: (uuid) =>
    set((s) => ({ dialogues: s.dialogues.map((d) => (d.uuid === uuid ? { ...d, ai_active: !d.ai_active } : d)) })),
  setFilter: (filter) => set({ filter }),
  setSearch: (search) => set({ search }),
}));
