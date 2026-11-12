import {
  Bot,
  CalendarPlus,
  Hand,
  MessageCircle,
  MoreVertical,
  Paperclip,
  Phone,
  Sparkles,
} from 'lucide-react';
import { Fragment, useEffect, useRef, useState, type FormEvent } from 'react';
import { dayLabel, msgTime } from '../lib/format';
import { useInbox } from '../store/inbox';
import type { Message } from '../types';
import Avatar from './Avatar';
import ChannelIcon, { channelLabel } from './ChannelIcon';
import StatusTag from './StatusTag';

function Bubble({ m }: { m: Message }) {
  if (m.sender_type === 'system') {
    return (
      <div className="my-1 flex justify-center">
        <span className="flex items-center gap-1.5 rounded-full bg-gold-tint px-3.5 py-1.5 text-xs font-semibold text-gold">
          <Sparkles size={13} />
          {m.content}
        </span>
      </div>
    );
  }
  const mine = m.sender_type !== 'client';
  const human = m.sender_type === 'human';
  return (
    <div className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
      <div className="max-w-[62%]">
        <div
          className={`rounded-2xl px-4 py-3 text-[14px] leading-relaxed shadow-card ${
            mine
              ? human
                ? 'rounded-br-none bg-brand-2 text-brand-ink'
                : 'rounded-br-none bg-brand text-brand-ink'
              : 'rounded-bl-none bg-surface text-ink'
          }`}
        >
          {m.content}
        </div>
        <div className={`mt-1 flex items-center gap-1 text-[11px] text-ink-3 ${mine ? 'justify-end' : ''}`}>
          {mine && (human ? <Hand size={11} /> : <Bot size={11} />)}
          {mine && <span>{human ? 'Адміністратор' : 'AI'} ·</span>}
          {msgTime(m.created_at)}
        </div>
      </div>
    </div>
  );
}

export default function ChatView() {
  const { dialogues, messages, activeId, send, toggleAi } = useInbox();
  const d = dialogues.find((x) => x.uuid === activeId);
  const list = (activeId && messages[activeId]) || [];
  const [text, setText] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [activeId, list.length]);

  if (!d) {
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-3 bg-bg text-ink-3">
        <MessageCircle size={40} strokeWidth={1.4} />
        Оберіть діалог зліва
      </main>
    );
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    send(text);
    setText('');
  };

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-bg">
      <header className="flex items-center gap-4 border-b border-line bg-surface px-7 py-4">
        <Avatar name={d.client.name} size="lg" />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="truncate font-serif text-2xl font-bold leading-tight text-brand">{d.client.name}</h2>
            <StatusTag status={d.status} />
          </div>
          <div className="mt-0.5 flex items-center gap-3 text-[13px] text-ink-2">
            {d.client.phone && (
              <span className="flex items-center gap-1">
                <Phone size={13} className="text-ink-3" />
                {d.client.phone}
              </span>
            )}
            <span className="flex items-center gap-1">
              <ChannelIcon type={d.channel} size={13} />
              {d.client.instagram_handle ? `@${d.client.instagram_handle}` : channelLabel(d.channel)}
            </span>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => toggleAi(d.uuid)}
            className={`flex items-center gap-1.5 rounded-xl border px-3.5 py-2 text-[13px] font-semibold transition ${
              d.ai_active
                ? 'border-gold-soft bg-gold-tint text-gold'
                : 'border-line bg-surface text-ink-2 hover:bg-surface-2'
            }`}
          >
            {d.ai_active ? <Bot size={16} /> : <Hand size={16} />}
            {d.ai_active ? 'AI веде' : 'Веде людина'}
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 rounded-xl bg-brand px-3.5 py-2 text-[13px] font-semibold text-brand-ink hover:bg-brand-2"
          >
            <CalendarPlus size={16} />
            Записати
          </button>
          <button type="button" title="Ще" className="rounded-xl p-2 text-ink-3 hover:bg-surface-2 hover:text-ink">
            <MoreVertical size={18} />
          </button>
        </div>
      </header>

      <div className="scroll-thin flex-1 space-y-4 overflow-y-auto px-8 py-6">
        {list.map((m, i) => {
          const day = dayLabel(m.created_at);
          const showDay = i === 0 || dayLabel(list[i - 1]!.created_at) !== day;
          return (
            <Fragment key={m.uuid}>
              {showDay && (
                <div className="flex justify-center">
                  <span className="rounded-full bg-surface px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-3">
                    {day}
                  </span>
                </div>
              )}
              <Bubble m={m} />
            </Fragment>
          );
        })}
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="border-t border-line bg-surface px-7 py-4">
        <div className="flex items-center gap-3 rounded-2xl border border-line bg-surface-2 px-3 py-2 focus-within:border-gold">
          <button type="button" title="Прикріпити" className="rounded-lg p-1.5 text-ink-3 hover:text-ink">
            <Paperclip size={18} />
          </button>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={d.ai_active ? 'Написати від імені салону (AI призупиниться)…' : 'Написати повідомлення…'}
            className="flex-1 bg-transparent py-1.5 text-sm outline-none placeholder:text-ink-3"
          />
          <button
            type="submit"
            disabled={!text.trim()}
            className="rounded-xl bg-brand px-5 py-2.5 text-sm font-semibold text-brand-ink transition hover:bg-brand-2 disabled:opacity-40"
          >
            Надіслати
          </button>
        </div>
      </form>
    </main>
  );
}
