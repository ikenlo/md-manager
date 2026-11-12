import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  CalendarPlus,
  Check,
  CheckCheck,
  Clock,
  FileText,
  Flag,
  Hand,
  MessageCircle,
  Phone,
  Send,
  Sparkles,
  User,
  UserRound,
  WifiOff,
  X,
} from 'lucide-react';
import { Fragment, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { aiReject } from '../api/ai';
import { AI_MODES, getAIMode, setAIMode, type AIMode } from '../lib/ai_mode';
import { dayLabel, msgTime } from '../lib/format';
import { useAIStore } from '../store/ai';
import { STATUS_LABEL, useInboxStore } from '../store/inbox';
import type { Attachment, Dialogue, Message, MessageStatus } from '../types';
import { AISuggestionPanel } from './AISuggestionPanel';
import ChannelIcon, { channelLabel } from './ChannelIcon';
import { Avatar, Badge, Button, Chip, Divider, EmptyState, IconButton, Input, Skeleton, cn, toast } from './ui';

const WINDOW_MS = 24 * 60 * 60 * 1000;

const QUICK_REPLIES = [
  'Вітаю! Чим можу допомогти?',
  'Надішлю вільні віконця за хвилину 🙌',
  'Уточніть, будь ласка, зручний день і час',
  'Дякуємо! Чекаємо вас у салоні M&D',
];

const STATUS_META: Record<MessageStatus, { label: string; render: () => JSX.Element }> = {
  queued: { label: 'У черзі', render: () => <Clock size={13} /> },
  sent: { label: 'Надіслано', render: () => <Check size={13} /> },
  delivered: { label: 'Доставлено', render: () => <CheckCheck size={13} /> },
  read: { label: 'Прочитано', render: () => <CheckCheck size={13} className="text-info" /> },
  failed: { label: 'Не доставлено', render: () => <X size={13} className="text-danger" /> },
};

const isInbound = (m: Message) => m.direction === 'inbound' || (!m.direction && m.sender_type === 'client');

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1).replace('.', ',')} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} МБ`;
}

function StatusIcon({ status }: { status?: MessageStatus }) {
  if (!status) return null;
  const meta = STATUS_META[status];
  return (
    <span className="inline-flex" title={meta.label} role="img" aria-label={meta.label}>
      {meta.render()}
    </span>
  );
}

function Attachments({ items, outbound }: { items: Attachment[]; outbound: boolean }) {
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {items.map((a, i) =>
        a.type.startsWith('image/') ? (
          <a
            key={`${a.url}-${i}`}
            href={a.url}
            target="_blank"
            rel="noreferrer"
            className="block overflow-hidden rounded-lg ring-1 ring-black/5 focus-visible:outline-none focus-visible:shadow-ring"
          >
            <img
              src={a.url}
              alt={a.name}
              loading="lazy"
              className="h-28 w-28 max-w-xs bg-surface-3 object-cover sm:h-32 sm:w-32"
            />
          </a>
        ) : (
          <a
            key={`${a.url}-${i}`}
            href={a.url}
            target="_blank"
            rel="noreferrer"
            className={cn(
              'flex max-w-xs items-center gap-2 rounded-sm px-3 py-2 text-xs',
              outbound ? 'bg-white/10 text-white' : 'bg-surface-2 text-ink',
            )}
          >
            <FileText size={16} className="shrink-0" aria-hidden="true" />
            <span className="min-w-0 truncate font-semibold">{a.name}</span>
            <span className={cn('shrink-0', outbound ? 'text-white/70' : 'text-ink-3')}>{formatSize(a.size)}</span>
          </a>
        ),
      )}
    </div>
  );
}

function Bubble({ m, clientName }: { m: Message; clientName: string }) {
  if (m.sender_type === 'system') {
    return (
      <div className="flex justify-center">
        <span className="inline-flex items-center gap-1.5 rounded-pill border border-gold/30 bg-gold-tint px-3.5 py-1 text-xs font-bold text-gold">
          <Sparkles size={12} aria-hidden="true" />
          {m.content}
        </span>
      </div>
    );
  }

  const inbound = isInbound(m);
  const human = m.sender_type === 'human';
  return (
    <div className={cn('flex items-end gap-2', inbound ? 'justify-start' : 'justify-end')}>
      {inbound && <Avatar name={clientName} size="sm" className="mb-5 hidden sm:inline-flex" />}
      <div className={cn('flex max-w-[82%] flex-col sm:max-w-[68%]', inbound ? 'items-start' : 'items-end')}>
        <div
          className={cn(
            'rounded-[14px] px-3.5 py-2.5 text-sm leading-relaxed [overflow-wrap:anywhere]',
            inbound
              ? 'rounded-bl-[4px] border border-line bg-surface text-ink shadow-sm'
              : 'rounded-br-[4px] bg-gradient-to-b from-brand-2 to-brand text-white shadow-sm',
          )}
        >
          {m.content && <p className="whitespace-pre-wrap">{m.content}</p>}
          {m.attachments?.length ? <Attachments items={m.attachments} outbound={!inbound} /> : null}
        </div>
        <div className="mt-1 flex items-center gap-1 px-1 text-2xs text-ink-3">
          {!inbound && (
            <>
              {human ? <Hand size={11} aria-hidden="true" /> : <Bot size={11} aria-hidden="true" />}
              <span>{human ? 'Адміністратор' : 'AI'} ·</span>
            </>
          )}
          <time dateTime={m.created_at}>{msgTime(m.created_at)}</time>
          {inbound ? (
            (m.status === 'delivered' || m.status === 'read') && (
              <span title={m.status === 'read' ? 'Прочитано' : 'Отримано'} className="inline-flex">
                <Check size={11} aria-hidden="true" />
              </span>
            )
          ) : (
            <StatusIcon status={m.status} />
          )}
        </div>
      </div>
    </div>
  );
}

function lastInboundAt(d: Dialogue, list: Message[]): string | null {
  if (d.last_inbound_at) return d.last_inbound_at;
  for (let i = list.length - 1; i >= 0; i--) if (isInbound(list[i]!)) return list[i]!.created_at;
  return null;
}

const soon = (what: string) => () => toast.info(`${what} — буде у Фазі 2`);

const MODE_META: Record<AIMode, { label: string; title: string; Icon: typeof Bot }> = {
  auto: { label: 'AI авто', title: 'AI генерує пропозиції автоматично', Icon: Sparkles },
  manual: { label: 'Вручну', title: 'AI запускається кнопкою', Icon: Bot },
  human: { label: 'Людина', title: 'AI вимкнено для цього діалогу', Icon: UserRound },
};

function AIModeToggle({
  mode,
  onChange,
  className,
}: {
  mode: AIMode;
  onChange: (m: AIMode) => void;
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label="Режим AI" className={cn('inline-flex rounded-md bg-surface-3 p-[3px]', className)}>
      {AI_MODES.map((m) => {
        const { label, title, Icon } = MODE_META[m];
        const on = m === mode;
        return (
          <button
            key={m}
            type="button"
            role="radio"
            aria-checked={on}
            title={title}
            onClick={() => onChange(m)}
            className={cn(
              'inline-flex min-h-7 items-center gap-1 whitespace-nowrap rounded-[7px] px-2.5 text-xs font-semibold transition duration-1',
              'focus-visible:outline-none focus-visible:shadow-ring',
              on
                ? 'bg-surface text-ink shadow-[0_1px_2px_rgba(20,30,25,.1),0_0_0_1px_rgb(var(--line))]'
                : 'text-ink-2 hover:text-ink',
            )}
          >
            <Icon size={12} aria-hidden="true" />
            {label}
          </button>
        );
      })}
    </div>
  );
}

export default function ActiveChat({ className }: { className?: string }) {
  const activeUuid = useInboxStore((s) => s.activeDialogueUuid);
  const d = useInboxStore((s) => s.dialogues.find((x) => x.uuid === s.activeDialogueUuid));
  const list = useInboxStore((s) => (s.activeDialogueUuid ? s.messagesByDialogue[s.activeDialogueUuid] : undefined));
  const { sendMessage, selectDialogue } = useInboxStore.getState();
  const source = useInboxStore((s) => s.source);
  const pending = useAIStore((s) => (activeUuid ? s.pendingByDialogue[activeUuid] : undefined));
  const responding = useAIStore((s) => (activeUuid ? Boolean(s.responding[activeUuid]) : false));
  const isApproving = useAIStore((s) => (pending ? Boolean(s.approving[pending.uuid]) : false));
  const isRejecting = useAIStore((s) => (pending ? Boolean(s.rejecting[pending.uuid]) : false));
  const [mode, setMode] = useState<AIMode>('manual');
  const messages = useMemo(() => list ?? [], [list]);
  const loading = list === undefined;

  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
    // responding — щоб бульбашка «AI аналізує» була в полі зору
  }, [activeUuid, messages.length, responding]);

  useEffect(() => setText(''), [activeUuid]);

  // Режим AI — свій для кожного діалогу; без збереженого — з ai_active від сервера
  useEffect(() => {
    if (!activeUuid) return;
    const fromServer = useInboxStore.getState().dialogues.find((x) => x.uuid === activeUuid)?.ai_active;
    const m = getAIMode(activeUuid, fromServer === false ? 'human' : 'manual');
    setMode(m);
    // збережений режим важливіший за ai_active з сервера — чип «Людина» у списку має збігатися
    if (fromServer !== undefined && fromServer !== (m !== 'human')) {
      useInboxStore.setState((st) => ({
        dialogues: st.dialogues.map((x) => (x.uuid === activeUuid ? { ...x, ai_active: m !== 'human' } : x)),
      }));
    }
  }, [activeUuid]);

  // Пропозиція AI, що чекає рішення (демо-режим без сервера — пропускаємо)
  useEffect(() => {
    if (!activeUuid || source !== 'api') return;
    void useAIStore.getState().fetchPending(activeUuid);
  }, [activeUuid, source]);

  if (!d) {
    return (
      <main className={cn('flex min-w-0 flex-1 flex-col items-center justify-center bg-bg', className)}>
        <EmptyState icon={<MessageCircle size={24} strokeWidth={1.6} aria-hidden="true" />}>
          <b className="block text-[15px] text-ink">Оберіть діалог</b>
          <span className="mt-1 block">Повідомлення з Instagram, Facebook і Telegram — в одному місці.</span>
        </EmptyState>
      </main>
    );
  }

  const changeMode = (m: AIMode) => {
    setMode(m);
    setAIMode(d.uuid, m);
    // список діалогів показує чип «Людина» за ai_active — тримаємо їх узгодженими
    useInboxStore.setState((st) => ({
      dialogues: st.dialogues.map((x) => (x.uuid === d.uuid ? { ...x, ai_active: m !== 'human' } : x)),
    }));
  };
  const hasPending = Boolean(pending);
  const canRunAI = mode !== 'human' && !hasPending && !responding;

  const inboundAt = lastInboundAt(d, messages);
  const windowClosed = inboundAt !== null && Date.now() - Date.parse(inboundAt) > WINDOW_MS;
  const expired = d.webhook_status === 'expired';

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const value = text;
    if (!value.trim() || sending) return;
    setText('');
    setSending(true);
    const ok = await sendMessage(d.uuid, value);
    setSending(false);
    if (!ok) {
      setText(value); // повертаємо текст, щоб не загубився
      toast.error('Не вдалося надіслати. Спробуйте ще раз');
    } else if (pending) {
      // відповіли вручну — пропозиція AI застаріла: прибираємо тут і відхиляємо на сервері,
      // інакше після перезавантаження вона повернулась би «привидом»
      useAIStore.getState().clearPending(d.uuid);
      aiReject(d.uuid, pending.uuid, 'manual reply').catch(() => undefined);
    }
    inputRef.current?.focus();
  };

  return (
    <main className={cn('flex min-h-0 min-w-0 flex-1 flex-col bg-bg', className)} aria-label={`Чат: ${d.client.name}`}>
      <header className="flex min-h-[68px] shrink-0 items-center gap-3 border-b border-line bg-surface px-3 py-2.5 pt-[calc(10px+env(safe-area-inset-top))] min-[900px]:pt-2.5 sm:px-6">
        <IconButton onClick={() => selectDialogue(null)} aria-label="Назад до списку" className="-ml-1 text-ink min-[900px]:hidden">
          <ArrowLeft size={20} />
        </IconButton>
        <span className="relative shrink-0">
          <Avatar name={d.client.name} size="md" className="sm:h-[42px] sm:w-[42px]" />
          <span
            className="absolute -bottom-1 -right-1 grid h-[18px] w-[18px] place-items-center rounded-full bg-surface ring-2 ring-surface"
            aria-hidden="true"
          >
            <ChannelIcon type={d.channel} size={12} />
          </span>
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-base font-bold leading-tight text-ink sm:text-lg">{d.client.name}</h2>
            <Chip variant={d.status} size="sm" className="hidden sm:inline-flex">
              {STATUS_LABEL[d.status]}
            </Chip>
          </div>
          <div className="mt-0.5 flex min-w-0 items-center gap-3 text-xs text-ink-3">
            <span className="flex shrink-0 items-center gap-1">
              <Phone size={12} className="text-ink-3" aria-hidden="true" />
              {d.client.phone ?? <span className="text-ink-3">без номера</span>}
            </span>
            <span className="flex min-w-0 items-center gap-1">
              <ChannelIcon type={d.channel} size={12} />
              <span className="truncate">
                {d.client.instagram_handle ? `@${d.client.instagram_handle}` : channelLabel(d.channel)}
              </span>
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-0.5 text-ink-2">
          <div className="mr-1.5 hidden items-center gap-1.5 sm:flex">
            <AIModeToggle mode={mode} onChange={changeMode} />
            <Badge count={hasPending ? 1 : 0} variant="danger" aria-label="Є пропозиція AI" title="Є пропозиція AI" />
          </div>
          <IconButton aria-label="Записати" title="Записати" onClick={soon('Запис')}>
            <CalendarPlus size={18} />
          </IconButton>
          <IconButton aria-label="Картка клієнта" title="Картка клієнта" className="hidden  sm:inline-flex" onClick={soon('Картка клієнта')}>
            <User size={18} />
          </IconButton>
          <IconButton aria-label="Позначити" title="Позначити" className="hidden  sm:inline-flex" onClick={soon('Позначки')}>
            <Flag size={18} />
          </IconButton>
        </div>
      </header>

      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-3 py-5 sm:px-8 sm:py-6" aria-live="polite">
        <div className="mx-auto flex max-w-3xl flex-col gap-4" aria-busy={loading || undefined}>
          {loading && (
            <>
              <Skeleton variant="rect" height={44} width="55%" />
              <Skeleton variant="rect" height={44} width="45%" className="self-end" />
              <Skeleton variant="rect" height={44} width="60%" />
            </>
          )}
          {messages.map((m, i) => {
            const day = dayLabel(m.created_at);
            const showDay = i === 0 || dayLabel(messages[i - 1]!.created_at) !== day;
            return (
              <Fragment key={m.uuid}>
                {showDay && <Divider label={day} className="my-1" />}
                <Bubble m={m} clientName={d.client.name} />
              </Fragment>
            );
          })}
          {responding && (
            <div role="status" aria-label="AI аналізує розмову" className="flex items-end justify-end gap-2">
              <div className="rounded-[14px] rounded-br-[4px] bg-gradient-to-b from-brand-2 to-brand px-3.5 py-2.5 text-white shadow-sm">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm">AI аналізує</span>
                  <span className="flex gap-1" aria-hidden="true">
                    {[0, 150, 300].map((delay) => (
                      <span
                        key={delay}
                        className="h-1.5 w-1.5 animate-bounce rounded-full bg-white/60 motion-reduce:animate-none"
                        style={{ animationDelay: `${delay}ms` }}
                      />
                    ))}
                  </span>
                </div>
              </div>
              <span className="mb-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full border border-gold/30 bg-brand-2 shadow-sm">
                <Bot size={16} className="text-gold" aria-hidden="true" />
              </span>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      {(expired || windowClosed) && (
        <div className="shrink-0 space-y-px">
          {expired && (
            <div role="alert" className="flex items-center gap-2 border-t border-danger/25 bg-danger-bg px-4 py-2.5 text-sm font-semibold text-danger sm:px-6">
              <WifiOff size={16} className="shrink-0" aria-hidden="true" />
              <span className="min-w-0 flex-1">{channelLabel(d.channel)}-токен прострочений. Повідомлення не доходять.</span>
              <button
                type="button"
                onClick={soon('Перепідключення каналу')}
                className="shrink-0 rounded-sm px-2 py-1 font-bold underline decoration-danger/40 underline-offset-2 hover:bg-danger/10 focus-visible:outline-none focus-visible:shadow-ring"
              >
                Перепідключити
              </button>
            </div>
          )}
          {windowClosed && (
            <div role="status" className="flex items-center gap-2 border-t border-warn/25 bg-warn-bg px-4 py-2.5 text-sm font-semibold text-warn sm:px-6">
              <AlertTriangle size={16} className="shrink-0" aria-hidden="true" />
              Вікно 24 год минуло. Відповідь може не дійти.
            </div>
          )}
        </div>
      )}

      {pending && (
        <div className="scroll-thin max-h-[55vh] shrink-0 overflow-y-auto border-t border-line bg-bg px-3 py-3 sm:px-6">
          <AISuggestionPanel
            suggestion={pending}
            isApproving={isApproving}
            isRejecting={isRejecting}
            isRegenerating={responding}
            onApprove={async (messageText) => {
              // успіх: стор прибирає pending, повідомлення приходить через WebSocket (new_message)
              await useAIStore.getState().approve(d.uuid, pending.uuid, messageText);
            }}
            onReject={async () => {
              await useAIStore.getState().reject(d.uuid, pending.uuid);
            }}
            onRegenerate={async () => {
              await useAIStore.getState().respond(d.uuid);
            }}
            onClose={() => useAIStore.getState().clearPending(d.uuid)}
          />
        </div>
      )}

      <footer className="shrink-0 border-t border-line bg-surface px-3 pb-[calc(12px+env(safe-area-inset-bottom))] pt-3 sm:p-5">
        <div className="mb-2 flex min-h-8 flex-wrap items-center gap-2 text-xs text-ink-3">
          {/* на телефоні в шапці немає місця — перемикач тут */}
          <AIModeToggle mode={mode} onChange={changeMode} className="sm:hidden" />
          {/* очікування AI показує бульбашка «AI аналізує» в чаті (або кнопка панелі) */}
          {hasPending || responding ? null : mode !== 'human' ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              iconLeft={<Sparkles size={14} />}
              disabled={!canRunAI || source !== 'api'}
              title={source !== 'api' ? 'Потрібен запущений сервер' : 'AI підготує відповідь — клієнт її не отримає без вашого схвалення'}
              onClick={() => void useAIStore.getState().respond(d.uuid)}
              className="-ml-2 text-gold"
            >
              Запустити AI
            </Button>
          ) : null}
        </div>
        <form onSubmit={submit} className="flex items-start gap-2">
          <Input
            ref={inputRef}
            className="flex-1"
            aria-label="Повідомлення"
            autoComplete="off"
            placeholder={mode === 'auto' ? 'Написати від імені салону (AI призупиниться)…' : 'Написати повідомлення…'}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <Button type="submit" disabled={!text.trim()} loading={sending} iconLeft={<Send size={16} />} aria-label="Надіслати">
            <span className="hidden sm:inline">Надіслати</span>
          </Button>
        </form>
        {/* поки є пропозиція AI — швидкі відповіді лише заважають */}
        {!hasPending && (
          <div className="scroll-thin mt-2.5 flex gap-1.5 overflow-x-auto whitespace-nowrap pb-0.5 sm:flex-wrap">
            {QUICK_REPLIES.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => {
                  setText(q);
                  inputRef.current?.focus();
                }}
                className="inline-flex min-h-7 shrink-0 items-center rounded-pill border border-line bg-surface-2 px-2.5 text-xs font-semibold text-ink-2 transition duration-1 hover:border-line-strong hover:text-ink focus-visible:outline-none focus-visible:shadow-ring"
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </footer>
    </main>
  );
}
