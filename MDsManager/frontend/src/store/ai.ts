import axios from 'axios';
import { create } from 'zustand';
import * as aiApi from '../api/ai';
import type { AISuggestion } from '../types';
import { toast } from './toast';

type Flags = Record<string, boolean>;

interface AIState {
  /** Pending suggestion per dialogue uuid (null — none). Missing key — not loaded yet. */
  pendingByDialogue: Record<string, AISuggestion | null>;
  /** Keyed by dialogue uuid. */
  responding: Flags;
  /** Keyed by suggestion uuid. */
  approving: Flags;
  /** Keyed by suggestion uuid. */
  rejecting: Flags;

  /** Loads the current pending suggestion. Silent: errors are only logged. */
  fetchPending: (dialogueUuid: string) => Promise<void>;
  /**
   * Asks AI for a reply. The reply is stored as pending and is NOT sent to the client.
   * Returns the new suggestion, or null on error (a toast is shown).
   */
  respond: (dialogueUuid: string) => Promise<AISuggestion | null>;
  /**
   * Approves a suggestion: the server creates the booking (if any) and queues the message.
   * Without `messageText` the server builds the text itself. Returns false on error (toast shown).
   */
  approve: (dialogueUuid: string, suggestionUuid: string, messageText?: string) => Promise<boolean>;
  /** Rejects a suggestion; nothing is sent to the client. Returns false on error (toast shown). */
  reject: (dialogueUuid: string, suggestionUuid: string, reason?: string) => Promise<boolean>;
  /** Forgets the pending suggestion locally (e.g. a human answered by hand). */
  clearPending: (dialogueUuid: string) => void;
}

const withFlag = (flags: Flags, key: string, on: boolean): Flags => {
  const next = { ...flags };
  if (on) next[key] = true;
  else delete next[key];
  return next;
};

/** HTTP status + server detail, or nulls for network/timeout errors. */
function describe(err: unknown): { status: number | null; detail: string | null; timeout: boolean } {
  if (!axios.isAxiosError(err)) return { status: null, detail: null, timeout: false };
  const raw = (err.response?.data as { detail?: unknown } | undefined)?.detail;
  return {
    status: err.response?.status ?? null,
    detail: typeof raw === 'string' ? raw : null,
    timeout: err.code === 'ECONNABORTED' || err.code === 'ETIMEDOUT',
  };
}

/** 401 (redirect to login) and 429 (toast) are already handled by the axios interceptor. */
const handledByInterceptor = (status: number | null) => status === 401 || status === 429;

/** Server details are English/technical — show the admin something actionable. */
function resolveErrorText(detail: string | null, status: number | null, action: 'approve' | 'reject'): string {
  if (status === 404) return 'Відповідь AI не знайдено — можливо, її вже видалено';
  if (detail?.includes("not 'pending'")) return 'Цю відповідь AI уже оброблено або вона застаріла';
  if (detail?.startsWith('Booking failed:')) {
    return `Не вдалося створити запис: ${detail.slice('Booking failed:'.length).trim()}`;
  }
  if (detail && status === 400) return detail;
  return action === 'approve' ? 'Не вдалося схвалити відповідь AI' : 'Не вдалося відхилити відповідь AI';
}

export const useAIStore = create<AIState>((set, get) => ({
  pendingByDialogue: {},
  responding: {},
  approving: {},
  rejecting: {},

  async fetchPending(dialogueUuid) {
    try {
      const suggestion = await aiApi.aiGetPending(dialogueUuid);
      set((s) => ({ pendingByDialogue: { ...s.pendingByDialogue, [dialogueUuid]: suggestion } }));
    } catch (err) {
      console.warn('AI: не вдалося завантажити pending-пропозицію', describe(err).status);
    }
  },

  async respond(dialogueUuid) {
    if (get().responding[dialogueUuid]) return null; // уже думає — не запускаємо вдруге
    set((s) => ({ responding: withFlag(s.responding, dialogueUuid, true) }));
    try {
      const r = await aiApi.aiRespond(dialogueUuid);
      const suggestion: AISuggestion = {
        uuid: r.suggestion_uuid,
        dialogue_uuid: dialogueUuid,
        content: r.content,
        intent: r.intent,
        proposed_booking: r.proposed_booking ?? null,
        status: 'pending',
        // відповідь /respond без часу створення — достатньо часу браузера
        created_at: new Date().toISOString(),
      };
      set((s) => ({ pendingByDialogue: { ...s.pendingByDialogue, [dialogueUuid]: suggestion } }));
      return suggestion;
    } catch (err) {
      const { status, timeout } = describe(err);
      if (timeout) {
        // сервер міг дописати відповідь уже після обриву — підтягуємо її
        toast.warning('AI думає надто довго. Перевіряю, чи відповідь уже готова…');
        void get().fetchPending(dialogueUuid);
      } else if (status === 503) {
        toast.error('AI вимкнено (Ollama не запущено). Перевірте, чи запущено Ollama на ПК.');
      } else if (status === 400) {
        toast.error('Немає повідомлень для AI');
      } else if (!handledByInterceptor(status)) {
        toast.error('AI не відповів. Спробуйте ще раз.');
      }
      return null;
    } finally {
      set((s) => ({ responding: withFlag(s.responding, dialogueUuid, false) }));
    }
  },

  async approve(dialogueUuid, suggestionUuid, messageText) {
    if (get().approving[suggestionUuid]) return false;
    set((s) => ({ approving: withFlag(s.approving, suggestionUuid, true) }));
    try {
      await aiApi.aiApprove(dialogueUuid, suggestionUuid, messageText);
      set((s) => ({
        pendingByDialogue: {
          ...s.pendingByDialogue,
          // прибираємо лише якщо це досі та сама пропозиція
          [dialogueUuid]:
            s.pendingByDialogue[dialogueUuid]?.uuid === suggestionUuid ? null : (s.pendingByDialogue[dialogueUuid] ?? null),
        },
      }));
      toast.success('AI-відповідь схвалено');
      return true;
    } catch (err) {
      const { status, detail } = describe(err);
      if (!handledByInterceptor(status)) toast.error(resolveErrorText(detail, status, 'approve'));
      void get().fetchPending(dialogueUuid); // стан на сервері міг змінитись (застаріла, оброблена)
      return false;
    } finally {
      set((s) => ({ approving: withFlag(s.approving, suggestionUuid, false) }));
    }
  },

  async reject(dialogueUuid, suggestionUuid, reason) {
    if (get().rejecting[suggestionUuid]) return false;
    set((s) => ({ rejecting: withFlag(s.rejecting, suggestionUuid, true) }));
    try {
      await aiApi.aiReject(dialogueUuid, suggestionUuid, reason);
      set((s) => ({
        pendingByDialogue: {
          ...s.pendingByDialogue,
          [dialogueUuid]:
            s.pendingByDialogue[dialogueUuid]?.uuid === suggestionUuid ? null : (s.pendingByDialogue[dialogueUuid] ?? null),
        },
      }));
      toast.info('AI-відповідь відхилено');
      return true;
    } catch (err) {
      const { status, detail } = describe(err);
      if (!handledByInterceptor(status)) toast.error(resolveErrorText(detail, status, 'reject'));
      void get().fetchPending(dialogueUuid);
      return false;
    } finally {
      set((s) => ({ rejecting: withFlag(s.rejecting, suggestionUuid, false) }));
    }
  },

  clearPending(dialogueUuid) {
    set((s) => ({ pendingByDialogue: { ...s.pendingByDialogue, [dialogueUuid]: null } }));
  },
}));
