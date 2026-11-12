/**
 * Realtime inbox channel.
 *
 * Phase 2 will implement real WebSocket connection to /api/ws. Phase 1.5 stubs only:
 * `connect` just remembers the token and handlers, `disconnect` forgets them.
 */
import type { Dialogue, Message, MessageStatus } from '../types';

export interface WsHandlers {
  /** A new message in a dialogue (inbound from a client or outbound from AI/another operator). */
  onNewMessage: (dialogueUuid: string, message: Message) => void;
  /** Dialogue fields changed (status, unread, AI on/off, preview…). */
  onDialogueUpdated: (dialogue: Dialogue) => void;
  /** Delivery status of an outbound message changed (queued → sent → delivered → read / failed). */
  onMessageStatus: (dialogueUuid: string, messageUuid: string, status: MessageStatus) => void;
}

let state: { token: string; handlers: WsHandlers } | null = null;

/** Opens the realtime connection. Stub: stores token and handlers only. */
export function connect(token: string, handlers: WsHandlers): void {
  state = { token, handlers };
}

/** Closes the realtime connection. Stub. */
export function disconnect(): void {
  state = null;
}

/** For diagnostics/tests: whether `connect` was called and not yet disconnected. */
export function isConnected(): boolean {
  return state !== null;
}
