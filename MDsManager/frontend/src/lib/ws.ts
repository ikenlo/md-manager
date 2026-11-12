/**
 * Realtime-канал інбоксу: WebSocket /api/ws?token=…
 *
 * - URL відносний до сторінки (у dev Vite проксіює /api разом з WebSocket).
 * - Обрив → повторне підключення з паузою 1, 2, 4, 8, 16, 30, 30… с; токен береться свіжий зі стору
 *   (тихе оновлення токена закриває старий сокет кодом 1008).
 * - `disconnect()` — ручне закриття, без повторів.
 */
import { meRequest } from '../api/client';
import type { ApiDialogue, ApiMessage } from '../api/inbox';
import { useAuthStore } from '../store/auth';
import type { MessageStatus } from '../types';

export interface NewMessageEvent {
  dialogue_uuid: string;
  message: ApiMessage;
  /** Є, коли діалог новий (симуляція вхідного / перший контакт). */
  dialogue?: ApiDialogue;
}

export interface MessageStatusEvent {
  dialogue_uuid: string;
  message_uuid: string;
  status: MessageStatus;
  external_id: string | null;
}

export interface DialogueUpdatedEvent {
  dialogue_uuid: string;
  unread_count?: number;
  status?: ApiDialogue['status'];
  last_message_at?: string | null;
  last_inbound_at?: string | null;
}

export interface WsHandlers {
  onNewMessage?: (e: NewMessageEvent) => void;
  onMessageStatus?: (e: MessageStatusEvent) => void;
  onDialogueUpdated?: (e: DialogueUpdatedEvent) => void;
  /** З'єднання відновлено після обриву — варто дозавантажити пропущене. */
  onReconnect?: () => void;
  /** З'єднання обірвалось (буде повторна спроба). */
  onDisconnect?: () => void;
}

const MAX_DELAY_MS = 30_000;

let socket: WebSocket | null = null;
let handlers: WsHandlers = {};
let manual = false;
let attempt = 0;
let dropped = false;
let timer: ReturnType<typeof setTimeout> | null = null;

function wsUrl(token: string): string {
  const q = `/api/ws?token=${encodeURIComponent(token)}`;
  const base = import.meta.env.VITE_API_URL as string | undefined;
  if (base) return base.replace(/^http/, 'ws').replace(/\/$/, '') + q;
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}${q}`;
}

function dispatch(raw: string): void {
  let data: { type?: string } & Record<string, unknown>;
  try {
    data = JSON.parse(raw);
  } catch {
    return;
  }
  switch (data.type) {
    case 'new_message':
      handlers.onNewMessage?.(data as unknown as NewMessageEvent);
      break;
    case 'message_status':
      handlers.onMessageStatus?.(data as unknown as MessageStatusEvent);
      break;
    case 'dialogue_updated':
      handlers.onDialogueUpdated?.(data as unknown as DialogueUpdatedEvent);
      break;
    default: // ping / pong / майбутні типи
  }
}

function scheduleReconnect(): void {
  if (manual || timer !== null) return;
  const delay = Math.min(1000 * 2 ** attempt, MAX_DELAY_MS);
  attempt += 1;
  timer = setTimeout(() => {
    timer = null;
    open();
  }, delay);
}

function open(): void {
  const token = useAuthStore.getState().token;
  if (manual || !token) return;
  const ws = new WebSocket(wsUrl(token));
  socket = ws;

  ws.onopen = () => {
    attempt = 0;
    if (dropped) {
      dropped = false;
      handlers.onReconnect?.();
    }
  };
  ws.onmessage = (ev) => dispatch(String(ev.data));
  ws.onerror = () => {
    /* деталі браузер не дає; повтор — в onclose */
  };
  ws.onclose = (ev) => {
    if (socket === ws) socket = null;
    if (manual) return;
    if (!dropped) {
      dropped = true;
      handlers.onDisconnect?.();
    }
    // 1008 — сесію завершено: перевіряємо через API (401 → вихід на /login)
    if (ev.code === 1008) meRequest().catch(() => undefined);
    scheduleReconnect();
  };
}

function onOnline(): void {
  // мережа повернулась — не чекаємо backoff
  if (manual || socket) return;
  if (timer !== null) clearTimeout(timer);
  timer = null;
  attempt = 0;
  open();
}

/** Opens the realtime connection (closes a previous one first). */
export function connect(token: string, h: WsHandlers): void {
  disconnect();
  if (!token) return;
  manual = false;
  handlers = h;
  attempt = 0;
  dropped = false;
  window.addEventListener('online', onOnline);
  open();
}

/** Closes the connection and stops reconnecting. */
export function disconnect(): void {
  manual = true;
  window.removeEventListener('online', onOnline);
  if (timer !== null) clearTimeout(timer);
  timer = null;
  const s = socket;
  socket = null;
  if (!s) return;
  s.onclose = null;
  s.onmessage = null;
  s.onerror = null;
  if (s.readyState === WebSocket.CONNECTING) {
    // закрити до рукостискання — браузер пише попередження; закриваємо одразу після нього
    s.onopen = () => s.close(1000, 'client disconnect');
  } else {
    s.onopen = null;
    s.close(1000, 'client disconnect');
  }
}

export function isConnected(): boolean {
  return socket?.readyState === WebSocket.OPEN;
}
