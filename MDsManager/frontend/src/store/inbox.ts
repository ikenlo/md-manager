import { create } from 'zustand';
import { fetchDialogues, fetchMessages, postMessage, previewOf, toDialogue, toMessage } from '../api/inbox';
import { getAIMode } from '../lib/ai_mode';
import type { DialogueUpdatedEvent, MessageStatusEvent, NewMessageEvent } from '../lib/ws';
import type { Dialogue, DialogueStatus, Message, MessageStatus } from '../types';
import { useAIStore } from './ai';

export type InboxFilter = 'all' | 'new' | 'in_progress' | 'ordered' | 'unread';
/** api — реальні дані бекенда; mock — демо (вхід без сервера в dev). */
export type InboxSource = 'api' | 'mock';

export const STATUS_LABEL: Record<DialogueStatus, string> = {
  new: 'Новий',
  in_progress: 'В роботі',
  ordered: 'Записано',
  lost: 'Втрачено',
};

const byLastDesc = (a: Dialogue, b: Dialogue) => b.last_message_at.localeCompare(a.last_message_at);

// Статус не відкочується назад (WS-подія могла випередити відповідь POST)
const RANK: Record<MessageStatus, number> = { queued: 0, sent: 1, delivered: 2, read: 3, failed: 4 };
const newerStatus = (a: MessageStatus | undefined, b: MessageStatus | undefined) =>
  !a ? b : !b ? a : RANK[b] >= RANK[a] ? b : a;

const isInbound = (m: Message) => m.direction === 'inbound' || (!m.direction && m.sender_type === 'client');

let localSeq = 0;
const localId = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `local-${Date.now()}-${++localSeq}`;

/** Додає або оновлює повідомлення в списку, зберігаючи «старший» статус. */
function upsert(list: Message[], m: Message): { list: Message[]; existed: boolean } {
  const i = list.findIndex((x) => x.uuid === m.uuid);
  if (i === -1) return { list: [...list, m], existed: false };
  const merged = { ...list[i]!, ...m, status: newerStatus(list[i]!.status, m.status) };
  const next = list.slice();
  next[i] = merged;
  return { list: next, existed: true };
}

// --- Автозапуск AI (режим «AI авто») ---

const AUTO_CLAIM_PREFIX = 'mds_ai_auto_';
const AUTO_CLAIM_TTL_MS = 10 * 60_000;
const claimedHere = new Set<string>();

/** Чи вже хтось (ця чи інша вкладка) запускав AI на це повідомлення. */
function alreadyClaimed(key: string): boolean {
  try {
    const prev = localStorage.getItem(key);
    return Boolean(prev) && Date.now() - Number(prev) < AUTO_CLAIM_TTL_MS;
  } catch {
    return false;
  }
}

function markClaimed(key: string): void {
  try {
    localStorage.setItem(key, String(Date.now()));
  } catch {
    /* недоступне сховище — захищає лише claimedHere */
  }
}

/**
 * Один запуск AI на одне вхідне повідомлення — навіть якщо подія прийде повторно
 * (оновлення вкладення) або відкрито кілька вкладок (кожна отримує ту саму WS-подію).
 * Між вкладками атомарність дає Web Locks API: блокування тримаємо до кінця відповіді AI,
 * а позначка в localStorage не дає повторити запуск після нього.
 */
async function runOnce(messageUuid: string, run: () => Promise<unknown>): Promise<void> {
  if (claimedHere.has(messageUuid)) return;
  claimedHere.add(messageUuid);
  const key = AUTO_CLAIM_PREFIX + messageUuid;
  const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined;
  if (!locks) {
    // без Web Locks (http, старий браузер) — найкраще, що можна: позначка в localStorage
    if (alreadyClaimed(key)) return;
    markClaimed(key);
    await run();
    return;
  }
  await locks.request(key, { ifAvailable: true }, async (lock) => {
    if (!lock || alreadyClaimed(key)) return; // інша вкладка вже працює або вже відпрацювала
    markClaimed(key);
    await run();
  });
}

/** Нове вхідне в діалозі з режимом «AI авто» і без відкритої пропозиції → AI готує відповідь. */
function maybeAutoRespond(dialogueUuid: string, messageUuid: string): void {
  if (getAIMode(dialogueUuid) !== 'auto') return;
  const ai = useAIStore.getState();
  if (ai.pendingByDialogue[dialogueUuid] || ai.responding[dialogueUuid]) return;
  // помилки (503, мережа) показує сам respond тостом
  runOnce(messageUuid, () => useAIStore.getState().respond(dialogueUuid)).catch((err) =>
    console.warn('Auto-trigger AI failed:', err),
  );
}

export interface WsNewMessageResult {
  /** Вхідне в неактивний діалог — варто показати тост. */
  notify: boolean;
  clientName?: string;
  /** Діалогу немає в списку й подія без його даних — треба перезавантажити список. */
  needsResync: boolean;
}

interface InboxState {
  source: InboxSource;
  dialogues: Dialogue[];
  activeDialogueUuid: string | null;
  messagesByDialogue: Record<string, Message[]>;
  isLoading: boolean;
  loadError: string | null;
  filter: InboxFilter;
  search: string;

  /** Завантажує діалоги з API (або залишає mock). Повторний виклик — ресинхронізація. */
  loadDialogues: () => Promise<void>;
  loadMessages: (uuid: string) => Promise<void>;
  /** Відкриває діалог (null — назад до списку на телефоні); непрочитані скидаються лише локально. */
  selectDialogue: (uuid: string | null) => void;
  /** API: POST → `queued`, далі статус приходить через WS. Mock: локально. false — не вдалося. */
  sendMessage: (uuid: string, text: string) => Promise<boolean>;

  handleWsNewMessage: (e: NewMessageEvent) => WsNewMessageResult;
  handleWsMessageStatus: (e: MessageStatusEvent) => void;
  handleWsDialogueUpdated: (e: DialogueUpdatedEvent) => void;
  addDialogueFromPayload: (d: Dialogue, messages?: Message[]) => void;

  /** Демо-режим / майбутня синхронізація. */
  setDialogues: (dialogues: Dialogue[], messages?: Record<string, Message[]>, source?: InboxSource) => void;
  toggleAi: (uuid: string) => void;
  setFilter: (f: InboxFilter) => void;
  setSearch: (s: string) => void;
}

export const useInboxStore = create<InboxState>((set, get) => ({
  source: 'api',
  dialogues: [],
  activeDialogueUuid: null,
  messagesByDialogue: {},
  isLoading: false,
  loadError: null,
  filter: 'all',
  search: '',

  async loadDialogues() {
    if (get().source === 'mock') return;
    set({ isLoading: true, loadError: null });
    try {
      const fresh = await fetchDialogues();
      const active = get().activeDialogueUuid;
      set({
        // відкритий діалог лишається прочитаним локально
        dialogues: fresh.map((d) => (d.uuid === active ? { ...d, unread_count: 0 } : d)).sort(byLastDesc),
        isLoading: false,
      });
      if (active) void get().loadMessages(active);
    } catch {
      set({ isLoading: false, loadError: 'Не вдалося завантажити діалоги' });
    }
  },

  async loadMessages(uuid) {
    if (get().source === 'mock') return;
    try {
      const list = await fetchMessages(uuid);
      set((s) => {
        // події WS, що прийшли під час запиту, не губимо
        let merged = list;
        for (const m of s.messagesByDialogue[uuid] ?? []) merged = upsert(merged, m).list;
        return { messagesByDialogue: { ...s.messagesByDialogue, [uuid]: merged } };
      });
    } catch {
      /* 401 обробляє інтерсептор; інше — покаже порожній чат */
    }
  },

  selectDialogue(uuid) {
    set((s) => ({
      activeDialogueUuid: uuid,
      dialogues: uuid ? s.dialogues.map((d) => (d.uuid === uuid ? { ...d, unread_count: 0 } : d)) : s.dialogues,
    }));
    if (uuid && get().messagesByDialogue[uuid] === undefined) void get().loadMessages(uuid);
  },

  async sendMessage(uuid, text) {
    const content = text.trim();
    if (!content || !get().dialogues.some((d) => d.uuid === uuid)) return false;

    let msg: Message;
    if (get().source === 'mock') {
      msg = {
        uuid: localId(),
        sender_type: 'human',
        direction: 'outbound',
        status: 'queued',
        content,
        created_at: new Date().toISOString(),
      };
    } else {
      try {
        msg = await postMessage(uuid, content);
      } catch {
        return false;
      }
    }
    set((s) => ({
      messagesByDialogue: {
        ...s.messagesByDialogue,
        [uuid]: upsert(s.messagesByDialogue[uuid] ?? [], msg).list,
      },
      dialogues: s.dialogues
        .map((d) =>
          d.uuid === uuid
            ? {
                ...d,
                preview: content,
                last_message_at: msg.created_at,
                status: d.status === 'new' ? ('in_progress' as const) : d.status,
              }
            : d,
        )
        .sort(byLastDesc),
    }));
    return true;
  },

  handleWsNewMessage(e) {
    const msg = toMessage(e.message);
    const s = get();
    const d = s.dialogues.find((x) => x.uuid === e.dialogue_uuid);
    if (!d) {
      if (!e.dialogue) return { notify: false, needsResync: true };
      const fresh = toDialogue(e.dialogue);
      get().addDialogueFromPayload(fresh, [msg]);
      if (isInbound(msg)) maybeAutoRespond(fresh.uuid, msg.uuid);
      return { notify: isInbound(msg), clientName: fresh.client.name, needsResync: false };
    }

    const active = s.activeDialogueUuid === d.uuid;
    const cached = s.messagesByDialogue[d.uuid];
    // список ще не завантажено — не створюємо неповний; підтягнеться при відкритті
    const { list, existed } = cached ? upsert(cached, msg) : { list: undefined, existed: false };
    const bump = isInbound(msg) && !existed && !active;
    const newer = msg.created_at >= d.last_message_at;

    set({
      messagesByDialogue: list ? { ...s.messagesByDialogue, [d.uuid]: list } : s.messagesByDialogue,
      dialogues: s.dialogues
        .map((x) =>
          x.uuid === d.uuid
            ? {
                ...x,
                preview: newer ? previewOf(msg) || x.preview : x.preview,
                last_message_at: newer ? msg.created_at : x.last_message_at,
                last_inbound_at: isInbound(msg) && newer ? msg.created_at : x.last_inbound_at,
                unread_count: bump ? x.unread_count + 1 : x.unread_count,
              }
            : x,
        )
        .sort(byLastDesc),
    });
    if (isInbound(msg) && !existed) maybeAutoRespond(d.uuid, msg.uuid);
    return { notify: bump, clientName: d.client.name, needsResync: false };
  },

  handleWsMessageStatus(e) {
    set((s) => {
      const list = s.messagesByDialogue[e.dialogue_uuid];
      if (!list) return s;
      return {
        messagesByDialogue: {
          ...s.messagesByDialogue,
          [e.dialogue_uuid]: list.map((m) =>
            m.uuid === e.message_uuid ? { ...m, status: newerStatus(m.status, e.status) } : m,
          ),
        },
      };
    });
  },

  handleWsDialogueUpdated(e) {
    set((s) => ({
      dialogues: s.dialogues
        .map((d) => {
          if (d.uuid !== e.dialogue_uuid) return d;
          const active = s.activeDialogueUuid === d.uuid;
          return {
            ...d,
            status: e.status ?? d.status,
            last_message_at: e.last_message_at ?? d.last_message_at,
            last_inbound_at: e.last_inbound_at ?? d.last_inbound_at,
            // у відкритому діалозі лічильник лишається 0
            unread_count: active ? 0 : (e.unread_count ?? d.unread_count),
          };
        })
        .sort(byLastDesc),
    }));
  },

  addDialogueFromPayload(d, messages) {
    set((s) => {
      if (s.dialogues.some((x) => x.uuid === d.uuid)) return s;
      return {
        dialogues: [...s.dialogues, d].sort(byLastDesc),
        messagesByDialogue: messages ? { ...s.messagesByDialogue, [d.uuid]: messages } : s.messagesByDialogue,
      };
    });
  },

  setDialogues: (dialogues, messages, source) =>
    set((s) => ({
      dialogues: [...dialogues].sort(byLastDesc),
      messagesByDialogue: messages ?? s.messagesByDialogue,
      source: source ?? s.source,
      isLoading: false,
    })),

  toggleAi: (uuid) =>
    set((s) => ({ dialogues: s.dialogues.map((d) => (d.uuid === uuid ? { ...d, ai_active: !d.ai_active } : d)) })),
  setFilter: (filter) => set({ filter }),
  setSearch: (search) => set({ search }),
}));
