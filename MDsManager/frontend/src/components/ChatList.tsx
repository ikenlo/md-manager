import { Search, SlidersHorizontal } from 'lucide-react';
import { useMemo } from 'react';
import { listTime } from '../lib/format';
import { useInbox, type StatusFilter } from '../store/inbox';
import Avatar from './Avatar';
import ChannelIcon from './ChannelIcon';
import StatusTag from './StatusTag';

const FILTERS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: 'Усі' },
  { key: 'new', label: 'Нові' },
  { key: 'in_progress', label: 'В роботі' },
  { key: 'ordered', label: 'Записані' },
  { key: 'lost', label: 'Втрачені' },
];

export default function ChatList() {
  const { dialogues, activeId, filter, search, select, setFilter, setSearch } = useInbox();

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return dialogues.filter(
      (d) =>
        (filter === 'all' || d.status === filter) &&
        (!q ||
          d.client.name.toLowerCase().includes(q) ||
          (d.client.instagram_handle ?? '').toLowerCase().includes(q)),
    );
  }, [dialogues, filter, search]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: dialogues.length };
    for (const d of dialogues) c[d.status] = (c[d.status] ?? 0) + 1;
    return c;
  }, [dialogues]);

  return (
    <section className="flex w-[380px] shrink-0 flex-col border-r border-line bg-surface">
      <header className="px-6 pb-4 pt-6">
        <div className="flex items-center justify-between">
          <h1 className="font-serif text-[32px] font-bold leading-none text-brand">Діалоги</h1>
          <button type="button" title="Фільтри" className="rounded-xl p-2 text-ink-3 hover:bg-surface-2 hover:text-ink">
            <SlidersHorizontal size={18} />
          </button>
        </div>
        <label className="mt-5 flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3 py-2.5 focus-within:border-gold">
          <Search size={16} className="text-ink-3" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Пошук за ім’ям або @нікнеймом"
            className="w-full bg-transparent text-sm outline-none placeholder:text-ink-3"
          />
        </label>
        <div className="mt-4 flex flex-wrap gap-2">
          {FILTERS.map(({ key, label }) => {
            const on = filter === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                  on ? 'bg-brand text-brand-ink' : 'bg-surface-2 text-ink-2 hover:bg-gold-tint'
                }`}
              >
                {label}
                <span className={`ml-1.5 ${on ? 'text-gold-soft' : 'text-ink-3'}`}>{counts[key] ?? 0}</span>
              </button>
            );
          })}
        </div>
      </header>

      <ul className="scroll-thin flex-1 overflow-y-auto px-3 pb-4">
        {visible.length === 0 && (
          <li className="px-4 py-10 text-center text-sm text-ink-3">Нічого не знайдено</li>
        )}
        {visible.map((d) => {
          const on = d.uuid === activeId;
          return (
            <li key={d.uuid}>
              <button
                type="button"
                onClick={() => select(d.uuid)}
                className={`flex w-full gap-3 rounded-2xl px-3 py-3 text-left transition ${
                  on ? 'bg-gold-tint/70 ring-1 ring-gold-soft' : 'hover:bg-surface-2'
                }`}
              >
                <div className="relative">
                  <Avatar name={d.client.name} />
                  <span className="absolute -bottom-0.5 -right-0.5 rounded-full bg-surface p-[3px] shadow-sm">
                    <ChannelIcon type={d.channel} size={12} />
                  </span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-[15px] font-bold text-ink">{d.client.name}</span>
                    <span className="ml-auto shrink-0 text-xs text-ink-3">{listTime(d.last_message_at)}</span>
                  </div>
                  <p className={`mt-0.5 truncate text-[13px] ${d.unread ? 'font-semibold text-ink' : 'text-ink-2'}`}>
                    {d.preview}
                  </p>
                  <div className="mt-1.5 flex items-center gap-2">
                    <StatusTag status={d.status} />
                    {!d.ai_active && (
                      <span className="rounded-full border border-line px-2 py-0.5 text-[11px] font-semibold text-ink-2">
                        Людина
                      </span>
                    )}
                    {d.unread > 0 && (
                      <span className="ml-auto min-w-[20px] rounded-full bg-gold px-1.5 text-center text-[11px] font-bold leading-5 text-surface">
                        {d.unread}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
