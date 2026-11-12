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
  WifiOff,
  X,
} from 'lucide-react';
import { Fragment, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { dayLabel, msgTime } from '../lib/format';
import { STATUS_LABEL, useInboxStore } from '../store/inbox';
import type { Attachment, Dialogue, Message, MessageStatus } from '../types';
import ChannelIcon, { channelLabel } from './ChannelIcon';
import { CHANNEL_RING } from './ChatList';
import { Avatar, Button, Chip, Divider, Input, cn, toast } from './ui';

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
              'flex max-w-xs items-center gap-2 rounded-md px-3 py-2 text-xs',
              outbound ? 'bg-white/10 text-brand-ink' : 'bg-surface-2 text-ink',
            )}
          >
            <FileText size={16} className="shrink-0" aria-hidden="true" />
            <span className="min-w-0 truncate font-semibold">{a.name}</span>
            <span className={cn('shrink-0', outbound ? 'text-brand-ink/70' : 'text-ink-3')}>{formatSize(a.size)}</span>
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
        <span className="inline-flex items-center gap-1.5 rounded-full bg-gold-tint px-4 py-1 text-xs font-semibold text-gold">
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
            'rounded-2xl px-4 py-2.5 text-sm leading-relaxed [overflow-wrap:anywhere]',
            inbound
              ? 'rounded-bl-none border border-line bg-surface text-ink shadow-sm'
              : 'rounded-br-none bg-brand text-brand-ink shadow-sm',
          )}
        >
          {m.content && <p className="whitespace-pre-wrap">{m.content}</p>}
          {m.attachments?.length ? <Attachments items={m.attachments} outbound={!inbound} /> : null}
        </div>
        <div className="mt-1 flex items-center gap-1 text-2xs text-ink-3">
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

export default function ActiveChat({ className }: { className?: string }) {
  const activeUuid = useInboxStore((s) => s.activeDialogueUuid);
  const d = useInboxStore((s) => s.dialogues.find((x) => x.uuid === s.activeDialogueUuid));
  const list = useInboxStore((s) => (s.activeDialogueUuid ? s.messagesByDialogue[s.activeDialogueUuid] : undefined));
  const { sendMessage, selectDialogue, toggleAi } = useInboxStore.getState();
  const messages = useMemo(() => list ?? [], [list]);

  const [text, setText] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [activeUuid, messages.length]);

  useEffect(() => setText(''), [activeUuid]);

  if (!d) {
    return (
      <main className={cn('flex min-w-0 flex-1 flex-col items-center justify-center gap-3 bg-bg text-sm text-ink-3', className)}>
        <span className="grid h-[52px] w-[52px] place-items-center rounded-full bg-surface ring-1 ring-inset ring-line">
          <MessageCircle size={24} strokeWidth={1.6} aria-hidden="true" />
        </span>
        Оберіть діалог зліва
      </main>
    );
  }

  const inboundAt = lastInboundAt(d, messages);
  const windowClosed = inboundAt !== null && Date.now() - Date.parse(inboundAt) > WINDOW_MS;
  const expired = d.webhook_status === 'expired';

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    sendMessage(d.uuid, text);
    setText('');
    inputRef.current?.focus();
  };

  return (
    <main className={cn('flex min-h-0 min-w-0 flex-1 flex-col bg-bg', className)} aria-label={`Чат: ${d.client.name}`}>
      <header className="flex h-20 shrink-0 items-center gap-3 border-b border-line bg-surface/80 px-3 backdrop-blur-md sm:px-6">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => selectDialogue(null)}
          aria-label="Назад до списку"
          className="-ml-1 px-2 text-brand-2 min-[900px]:hidden"
        >
          <ArrowLeft size={20} />
        </Button>
        <Avatar
          name={d.client.name}
          size="lg"
          className={cn('rounded-full ring-2 ring-offset-2 ring-offset-surface', CHANNEL_RING[d.channel])}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate font-serif text-xl font-bold leading-tight text-brand sm:text-2xl">{d.client.name}</h2>
            <Chip variant={d.status} size="sm" dot className="hidden sm:inline-flex">
              {STATUS_LABEL[d.status]}
            </Chip>
          </div>
          <div className="mt-0.5 flex min-w-0 items-center gap-3 text-xs text-ink-2">
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
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => toggleAi(d.uuid)}
            aria-pressed={d.ai_active}
            title={d.ai_active ? 'AI відповідає клієнту. Натисніть, щоб вести самому' : 'Веде людина. Натисніть, щоб передати AI'}
            iconLeft={d.ai_active ? <Bot size={14} /> : <Hand size={14} />}
            className={cn('mr-1', d.ai_active && 'border-gold-soft bg-gold-tint text-gold hover:bg-gold-tint')}
          >
            <span className="hidden lg:inline">{d.ai_active ? 'AI веде' : 'Веде людина'}</span>
          </Button>
          <Button variant="ghost" size="sm" aria-label="Записати" title="Записати" className="px-2" onClick={soon('Запис')}>
            <CalendarPlus size={18} />
          </Button>
          <Button variant="ghost" size="sm" aria-label="Картка клієнта" title="Картка клієнта" className="hidden px-2 sm:inline-flex" onClick={soon('Картка клієнта')}>
            <User size={18} />
          </Button>
          <Button variant="ghost" size="sm" aria-label="Позначити" title="Позначити" className="hidden px-2 sm:inline-flex" onClick={soon('Позначки')}>
            <Flag size={18} />
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-5 sm:p-8" aria-live="polite">
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
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
          <div ref={endRef} />
        </div>
      </div>

      {(expired || windowClosed) && (
        <div className="shrink-0 space-y-px">
          {expired && (
            <div role="alert" className="flex items-center gap-2 bg-danger px-4 py-2.5 text-sm font-semibold text-white sm:px-6">
              <WifiOff size={16} className="shrink-0" aria-hidden="true" />
              <span className="min-w-0 flex-1">{channelLabel(d.channel)}-токен прострочений. Повідомлення не доходять.</span>
              <button
                type="button"
                onClick={soon('Перепідключення каналу')}
                className="shrink-0 rounded-sm px-2 py-1 underline decoration-white/50 underline-offset-2 hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
              >
                Перепідключити
              </button>
            </div>
          )}
          {windowClosed && (
            <div role="status" className="flex items-center gap-2 bg-warn-bg px-4 py-2.5 text-sm font-semibold text-warn sm:px-6">
              <AlertTriangle size={16} className="shrink-0" aria-hidden="true" />
              Вікно 24 год минуло. Відповідь може не дійти.
            </div>
          )}
        </div>
      )}

      <footer className="shrink-0 border-t border-line bg-surface px-3 pb-[calc(12px+env(safe-area-inset-bottom))] pt-3 sm:p-5">
        <form onSubmit={submit} className="flex items-start gap-2">
          <Input
            ref={inputRef}
            className="flex-1"
            aria-label="Повідомлення"
            autoComplete="off"
            placeholder={d.ai_active ? 'Написати від імені салону (AI призупиниться)…' : 'Написати повідомлення…'}
            value={text}
            onChange={(e) => setText(e.target.value)}
            inputClassName="border-transparent bg-surface-2 hover:border-transparent"
          />
          <Button type="submit" disabled={!text.trim()} iconLeft={<Send size={16} />} aria-label="Надіслати">
            <span className="hidden sm:inline">Надіслати</span>
          </Button>
        </form>
        <div className="mt-2 flex gap-x-4 gap-y-1 overflow-x-auto whitespace-nowrap text-xs text-ink-3 sm:flex-wrap">
          {QUICK_REPLIES.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => {
                setText(q);
                inputRef.current?.focus();
              }}
              className="shrink-0 underline decoration-transparent underline-offset-4 transition hover:text-ink-2 hover:decoration-gold-soft focus-visible:outline-none focus-visible:decoration-gold"
            >
              {q}
            </button>
          ))}
        </div>
      </footer>
    </main>
  );
}
