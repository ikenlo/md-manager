import { create } from 'zustand';
import { mockDialogues, mockMessages } from '../data/mock';
import type { Dialogue, DialogueStatus, Message } from '../types';

export type StatusFilter = 'all' | DialogueStatus;

interface InboxState {
  dialogues: Dialogue[];
  messages: Record<string, Message[]>;
  activeId: string | null;
  filter: StatusFilter;
  search: string;
  select: (id: string) => void;
  setFilter: (f: StatusFilter) => void;
  setSearch: (s: string) => void;
  send: (text: string) => void;
  toggleAi: (id: string) => void;
}

export const useInbox = create<InboxState>((set, get) => ({
  dialogues: mockDialogues,
  messages: mockMessages,
  activeId: mockDialogues[0]?.uuid ?? null,
  filter: 'all',
  search: '',

  select: (id) =>
    set((s) => ({
      activeId: id,
      dialogues: s.dialogues.map((d) => (d.uuid === id ? { ...d, unread_count: 0 } : d)),
    })),
  setFilter: (filter) => set({ filter }),
  setSearch: (search) => set({ search }),

  send(text) {
    const id = get().activeId;
    const content = text.trim();
    if (!id || !content) return;
    const now = new Date().toISOString();
    const msg: Message = {
      uuid: crypto.randomUUID(),
      sender_type: 'human',
      content,
      created_at: now,
      direction: 'outbound',
      status: 'sent',
    };
    set((s) => ({
      messages: { ...s.messages, [id]: [...(s.messages[id] ?? []), msg] },
      dialogues: s.dialogues
        .map((d) =>
          d.uuid === id
            ? { ...d, preview: content, last_message_at: now, status: d.status === 'new' ? 'in_progress' : d.status }
            : d,
        )
        .sort((a, b) => b.last_message_at.localeCompare(a.last_message_at)),
    }));
  },

  toggleAi: (id) =>
    set((s) => ({
      dialogues: s.dialogues.map((d) => (d.uuid === id ? { ...d, ai_active: !d.ai_active } : d)),
    })),
}));
