import { Bot, CalendarCheck, Check, RefreshCw, X } from 'lucide-react';
import { useEffect, useId, useState } from 'react';
import type { AIIntent, AISuggestion } from '../types';
import { Button, Chip, Field, IconButton, cn, controlClass, type ChipVariant } from './ui';

const MAX_LENGTH = 5000;

const INTENT: Record<AIIntent, { label: string; variant: ChipVariant }> = {
  booking: { label: 'Запис', variant: 'ok' },
  question: { label: 'Питання', variant: 'info' },
  escalate: { label: 'Ескалація', variant: 'warn' },
  unknown: { label: '?', variant: 'muted' },
};

/** «2026-12-01» → «01.12.2026» для картки запису; інше лишається як є. */
function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso;
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
 * The textarea starts with `suggestion.suggested_message` — built by the server, so it is exactly
 * what the client receives on approve without edits (for bookings: the ready confirmation,
 * not the AI's neutral holding reply).
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
  const [text, setText] = useState(suggestion.suggested_message);
  const textareaId = useId();
  const counterId = useId();

  // нова пропозиція (перегенерація) — новий текст
  useEffect(() => {
    setText(suggestion.suggested_message);
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
      className={cn('rounded-lg border border-line bg-surface p-4 shadow-sm sm:p-[18px]', className)}
    >
      <header className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="brand-mark grid h-8 w-8 shrink-0 place-items-center rounded-sm text-[#1a1408]">
            <Bot size={18} aria-hidden="true" />
          </span>
          <h3 className="truncate text-[15px] font-bold text-ink">Пропозиція AI</h3>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Chip variant={intent.variant} size="sm">
            {intent.label}
          </Chip>
          {onClose && (
            <IconButton onClick={onClose} aria-label="Сховати пропозицію" className="text-ink-3 hover:text-ink">
              <X size={16} />
            </IconButton>
          )}
        </div>
      </header>

      {booking && (
        <div className="mt-3 rounded-md border border-gold/30 bg-gold-tint p-3">
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
          className={cn(controlClass(tooLong), 'min-h-[84px] resize-y py-2.5 leading-relaxed')}
        />
      </Field>
      <div
        id={counterId}
        aria-live="polite"
        className={cn('mt-1 text-right text-2xs tabular-nums', tooLong ? 'font-semibold text-danger' : 'text-ink-3')}
      >
        {text.length} / {MAX_LENGTH}
      </div>

      <div className="mt-3 flex flex-wrap justify-end gap-2 max-[480px]:[&>button]:flex-1">
        <Button
          type="button"
          variant="danger"
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
