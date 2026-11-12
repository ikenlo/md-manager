import { Bot, CalendarCheck, Check, RefreshCw, X } from 'lucide-react';
import { useEffect, useId, useState } from 'react';
import type { AIIntent, AIProposedBooking, AISuggestion } from '../types';
import { Button, Chip, Field, cn, type ChipVariant } from './ui';

const MAX_LENGTH = 5000;

const INTENT: Record<AIIntent, { label: string; variant: ChipVariant }> = {
  booking: { label: 'Запис', variant: 'ordered' },
  question: { label: 'Питання', variant: 'info' },
  // окремого «warn» у Chip немає — теплий золотий читається як «потрібна увага»
  escalate: { label: 'Ескалація', variant: 'in_progress' },
  unknown: { label: '?', variant: 'new' },
};

/** «2026-12-01» → «01.12.2026»; інше лишається як є. */
function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso;
}

/** Той самий текст, що сервер складає при схваленні запису без message_text. */
export function bookingConfirmationText(b: AIProposedBooking): string {
  return `Вас записано на ${b.service_name || 'послугу'} ${formatDate(b.date)} о ${b.time}. Чекаємо вас! 😊`;
}

/** Текст, який піде клієнту після схвалення: для запису — підтвердження, інакше — відповідь AI. */
export function initialReplyText(s: AISuggestion): string {
  return s.proposed_booking ? bookingConfirmationText(s.proposed_booking) : s.content;
}

export interface AISuggestionPanelProps {
  suggestion: AISuggestion;
  /** Called with the (possibly edited) text that will be sent to the client. */
  onApprove: (messageText: string) => void | Promise<void>;
  onReject: () => void | Promise<void>;
  /** Asks AI for a new draft (replaces this suggestion). */
  onRegenerate?: () => void | Promise<void>;
  isApproving?: boolean;
  isRejecting?: boolean;
  isRegenerating?: boolean;
  /** Hides the panel without approving or rejecting. */
  onClose?: () => void;
  className?: string;
}

/**
 * Card with a pending AI reply: intent, proposed booking, editable text for the client,
 * and approve / reject / regenerate actions. Nothing reaches the client until «Схвалити».
 *
 * For bookings the textarea starts with the confirmation the client will receive
 * («Вас записано на …»), not with the AI's neutral holding reply.
 */
export function AISuggestionPanel({
  suggestion,
  onApprove,
  onReject,
  onRegenerate,
  isApproving = false,
  isRejecting = false,
  isRegenerating = false,
  onClose,
  className,
}: AISuggestionPanelProps) {
  const [text, setText] = useState(() => initialReplyText(suggestion));
  const textareaId = useId();
  const counterId = useId();

  // нова пропозиція (перегенерація) — новий текст
  useEffect(() => {
    setText(initialReplyText(suggestion));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- лише при зміні пропозиції
  }, [suggestion.uuid]);

  const busy = isApproving || isRejecting || isRegenerating;
  const tooLong = text.length > MAX_LENGTH;
  const canApprove = !busy && text.trim().length > 0 && !tooLong;
  const intent = INTENT[suggestion.intent] ?? INTENT.unknown;
  const booking = suggestion.proposed_booking;

  return (
    <section
      aria-label="Пропозиція AI"
      aria-busy={busy || undefined}
      className={cn('rounded-xl border border-line bg-surface p-4 shadow-sm', className)}
    >
      <header className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-gold-tint text-gold">
            <Bot size={18} aria-hidden="true" />
          </span>
          <h3 className="truncate font-serif text-lg font-bold text-brand">Пропозиція AI</h3>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Chip variant={intent.variant} size="sm" dot>
            {intent.label}
          </Chip>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Сховати пропозицію"
              className="grid h-8 w-8 place-items-center rounded-sm text-ink-3 transition hover:bg-surface-2 hover:text-ink focus-visible:outline-none focus-visible:shadow-ring"
            >
              <X size={16} />
            </button>
          )}
        </div>
      </header>

      {booking && (
        <div className="mt-3 rounded-md border border-gold-soft/50 bg-gold-tint/30 p-3">
          <div className="flex items-center gap-2 font-semibold text-ink">
            <CalendarCheck size={16} className="shrink-0 text-gold" aria-hidden="true" />
            {booking.service_name}
          </div>
          <div className="mt-0.5 pl-6 text-sm text-ink-2 tabular-nums">
            {formatDate(booking.date)} о {booking.time}
          </div>
          <p className="mt-2 text-xs text-ink-3">
            Після схвалення запис буде створено і клієнт отримає підтвердження.
          </p>
        </div>
      )}

      <Field label="Текст, який отримає клієнт:" htmlFor={textareaId} className="mt-3">
        <textarea
          id={textareaId}
          aria-label="Текст для клієнта"
          aria-describedby={counterId}
          aria-invalid={tooLong || undefined}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={busy}
          rows={3}
          className={cn(
            'min-h-[80px] w-full resize-y rounded-lg border bg-surface-2 p-3 text-base text-ink outline-none md:text-sm',
            'transition duration-1 ease-ease placeholder:text-ink-3 disabled:cursor-not-allowed disabled:opacity-60',
            tooLong
              ? 'border-danger focus:ring-2 focus:ring-danger/20'
              : 'border-line focus:border-brand focus:ring-2 focus:ring-brand/20',
          )}
        />
      </Field>
      <div
        id={counterId}
        aria-live="polite"
        className={cn('mt-1 text-right text-2xs tabular-nums', tooLong ? 'font-semibold text-danger' : 'text-ink-3')}
      >
        {text.length} / {MAX_LENGTH}
      </div>

      <div className="mt-3 flex flex-wrap justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          iconLeft={<X size={14} />}
          loading={isRejecting}
          disabled={busy}
          onClick={() => void onReject()}
        >
          Відхилити
        </Button>
        {onRegenerate && (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            iconLeft={<RefreshCw size={14} />}
            loading={isRegenerating}
            disabled={busy}
            onClick={() => void onRegenerate()}
          >
            Перегенерувати
          </Button>
        )}
        <Button
          type="button"
          size="sm"
          iconLeft={<Check size={14} />}
          loading={isApproving}
          disabled={!canApprove}
          onClick={() => void onApprove(text)}
        >
          Схвалити
        </Button>
      </div>
    </section>
  );
}

export default AISuggestionPanel;
