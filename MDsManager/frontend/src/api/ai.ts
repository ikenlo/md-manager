import type { AIApproveResult, AIRejectResult, AIRespondResult, AISuggestion } from '../types';
import { api } from './client';

/**
 * AI на сервері: до 3 звернень до моделі по OLLAMA_TIMEOUT_SECONDS (120 с) кожне.
 * Спільний таймаут клієнта (15 с) обірвав би запит, хоча сервер усе одно збереже пропозицію.
 */
const AI_RESPOND_TIMEOUT_MS = 6 * 60 * 1000;

/** Як GET /ai/pending віддає пропозицію (без dialogue_uuid і полів рішення). */
interface ApiPendingSuggestion {
  uuid: string;
  content: string;
  intent: AISuggestion['intent'];
  proposed_booking: AISuggestion['proposed_booking'] | null;
  status: AISuggestion['status'];
  created_at: string;
}

const base = (dialogueUuid: string) => `/api/dialogues/${dialogueUuid}/ai`;

/** Запускає AI на діалозі: відповідь зберігається як pending і клієнту ще не надсилається. */
export async function aiRespond(dialogueUuid: string): Promise<AIRespondResult> {
  const { data } = await api.post<AIRespondResult>(`${base(dialogueUuid)}/respond`, null, {
    timeout: AI_RESPOND_TIMEOUT_MS,
  });
  return data;
}

/** Поточна pending-пропозиція діалогу або null. */
export async function aiGetPending(dialogueUuid: string): Promise<AISuggestion | null> {
  const { data } = await api.get<{ suggestion: ApiPendingSuggestion | null }>(
    `${base(dialogueUuid)}/pending`,
  );
  const raw = data.suggestion;
  if (!raw) return null;
  // бекенд не повертає dialogue_uuid — він відомий з адреси запиту
  return {
    uuid: raw.uuid,
    dialogue_uuid: dialogueUuid,
    content: raw.content,
    intent: raw.intent,
    proposed_booking: raw.proposed_booking ?? null,
    status: raw.status,
    created_at: raw.created_at,
  };
}

/**
 * Погоджує пропозицію. Без messageText сервер сам складе текст:
 * для запису — «Вас записано на …», інакше — текст AI.
 */
export async function aiApprove(
  dialogueUuid: string,
  suggestionUuid: string,
  messageText?: string,
): Promise<AIApproveResult> {
  const body: { message_text?: string } = {};
  if (messageText && messageText.trim()) body.message_text = messageText.trim();
  const { data } = await api.post<AIApproveResult>(
    `${base(dialogueUuid)}/${suggestionUuid}/approve`,
    body,
  );
  return data;
}

/** Відхиляє пропозицію; клієнту нічого не надсилається. */
export async function aiReject(
  dialogueUuid: string,
  suggestionUuid: string,
  reason?: string,
): Promise<AIRejectResult> {
  const body: { reason?: string } = {};
  if (reason && reason.trim()) body.reason = reason.trim();
  const { data } = await api.post<AIRejectResult>(
    `${base(dialogueUuid)}/${suggestionUuid}/reject`,
    body,
  );
  return data;
}
