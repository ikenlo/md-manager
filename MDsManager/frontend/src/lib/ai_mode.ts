/**
 * Режим AI для діалогу — поки лише в браузері (localStorage); на сервері — Phase 4.
 *
 * - auto: AI готує пропозицію сам на кожне нове вхідне (Part 3.3);
 * - manual: AI запускається кнопкою «Запустити AI»;
 * - human: AI для діалогу вимкнено.
 */
export type AIMode = 'auto' | 'manual' | 'human';

export const AI_MODES: readonly AIMode[] = ['auto', 'manual', 'human'];

const key = (dialogueUuid: string) => `mds_ai_mode_${dialogueUuid}`;

const isMode = (v: unknown): v is AIMode => v === 'auto' || v === 'manual' || v === 'human';

/** Збережений режим або `fallback` (типово «manual»), якщо нічого не збережено чи сховище недоступне. */
export function getAIMode(dialogueUuid: string, fallback: AIMode = 'manual'): AIMode {
  try {
    const stored = localStorage.getItem(key(dialogueUuid));
    return isMode(stored) ? stored : fallback;
  } catch {
    return fallback;
  }
}

export function setAIMode(dialogueUuid: string, mode: AIMode): void {
  try {
    localStorage.setItem(key(dialogueUuid), mode);
  } catch {
    /* приватний режим — режим діє до перезавантаження */
  }
}
