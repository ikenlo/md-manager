import { Bot, MessageCircle, Search } from 'lucide-react';
import { useMemo } from 'react';
import { listTime } from '../lib/format';
import { useAIStore } from '../store/ai';
import { STATUS_LABEL, useInboxStore, type InboxFilter } from '../store/inbox';
import type { Dialogue } from '../types';
import ChannelIcon, { channelLabel } from './ChannelIcon';
import { Avatar, Badge, Chip, EmptyState, Input, Skeleton, cn } from './ui';

const FILTERS: Array<{ key: InboxFilter; label: string }> = [
  { key: 'all', label: 'Всі' },
  { key: 'new', label: 'Нові' },
  { key: 'in_progress', label: 'В роботі' },
  { key: 'ordered', label: 'Записані' },
  { key: 'unread', label: 'Непрочитані' },
];

const matches = (d: Dialogue, f: InboxFilter) =>
  f === 'all' ? true : f === 'unread' ? d.unread_count > 0 : d.status === f;

export default function ChatList({ className }: { className?: string }) {
  const dialogues = useInboxStore((s) => s.dialogues);
  const activeUuid = useInboxStore((s) => s.activeDialogueUuid);
  const filter = useInboxStore((s) => s.filter);
  const search = useInboxStore((s) => s.search);
  const isLoading = useInboxStore((s) => s.isLoading);
  const pendingAI = useAIStore((s) => s.pendingByDialogue);
  const loadError = useInboxStore((s) => s.loadError);
  const { selectDialogue, setFilter, setSearch } = useInboxStore.getState();

  const counts = useMemo(() => {
    const c = {} as Record<InboxFilter, number>;
    for (const f of FILTERS) c[f.key] = dialogues.filter((d) => matches(d, f.key)).length;
    return c;
  }, [dialogues]);

  const unreadTotal = useMemo(() => dialogues.reduce((a, d) => a + d.unread_count, 0), [dialogues]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return dialogues
      .filter(
        (d) =>
          matches(d, filter) &&
          (!q ||
            d.client.name.toLowerCase().includes(q) ||
            (d.client.instagram_handle ?? '').toLowerCase().includes(q) ||
            (d.client.phone ?? '').includes(q)),
      )
      .sort((a, b) => b.last_message_at.localeCompare(a.last_message_at));
  }, [dialogues, filter, search]);

  return (
    <section
      aria-label="Діалоги"
      className={cn(
        'flex min-h-0 w-full flex-col bg-surface min-[900px]:w-[380px] min-[900px]:shrink-0 min-[900px]:border-r min-[900px]:border-line',
        className,
      )}
    >
      <header className="px-4 pb-3 pt-3.5 min-[900px]:px-5 min-[900px]:pt-[22px]">
        {/* ≤900px заголовок — у верхній смузі (MobileBar), як у Connect */}
        <div className="mb-3.5 hidden items-center gap-2.5 min-[900px]:flex">
          <h1 className="text-2xl font-bold leading-tight tracking-[-0.01em] text-ink">Діалоги</h1>
          {unreadTotal > 0 && (
            <Badge count={unreadTotal} aria-label={`${unreadTotal} непрочитаних повідомлень`} title="Непрочитані" />
          )}
        </div>

        <Input
          type="search"
          aria-label="Пошук клієнта"
          placeholder="Пошук: ім'я, @instagram, телефон"
          iconLeft={<Search size={16} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        {/* Фільтри — «чіпи» Connect: горизонтальна прокрутка на телефоні */}
        <div
          role="tablist"
          aria-label="Фільтр діалогів"
          className="scroll-thin -mx-4 mt-3 flex gap-1.5 overflow-x-auto px-4 pb-0.5 min-[900px]:-mx-5 min-[900px]:px-5"
        >
          {FILTERS.map(({ key, label }) => {
            const on = filter === key;
            return (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={on}
                onClick={() => setFilter(key)}
                className={cn(
                  'inline-flex min-h-8 shrink-0 items-center gap-1.5 rounded-pill border px-3 text-[13px] font-semibold transition duration-1',
                  'focus-visible:outline-none focus-visible:shadow-ring',
                  on
                    ? 'border-brand bg-brand text-white dark:border-gold dark:bg-gold dark:text-[#17120a]'
                    : 'border-line-strong bg-surface text-ink-2 hover:bg-surface-2',
                )}
              >
                {label}
                <span className={cn('tabular-nums text-xs', on ? 'opacity-75' : 'text-ink-3')}>{counts[key]}</span>
              </button>
            );
          })}
        </div>
      </header>

      <ul
        className="min-h-0 flex-1 overflow-y-auto border-t border-line max-[900px]:pb-[calc(96px+env(safe-area-inset-bottom))]"
        aria-label="Список діалогів"
      >
        {isLoading && dialogues.length === 0 ? (
          [0, 1, 2, 3].map((i) => (
            <li key={i} className="flex gap-3 border-b border-line px-4 py-3.5" aria-hidden="true">
              <Skeleton variant="circle" width={40} />
              <div className="flex flex-1 flex-col gap-2 pt-1">
                <Skeleton width="50%" />
                <Skeleton width="80%" height={12} />
              </div>
            </li>
          ))
        ) : visible.length === 0 ? (
          <li>
            <EmptyState icon={<MessageCircle size={24} strokeWidth={1.6} aria-hidden="true" />}>
              {loadError ?? (dialogues.length ? 'Немає діалогів за цим фільтром' : 'Поки немає діалогів')}
            </EmptyState>
          </li>
        ) : (
          visible.map((d) => {
            const on = d.uuid === activeUuid;
            return (
              <li key={d.uuid} className="border-b border-line last:border-b-0">
                <button
                  type="button"
                  onClick={() => selectDialogue(d.uuid)}
                  aria-current={on ? 'true' : undefined}
                  className={cn(
                    'relative flex w-full gap-3 px-4 py-3 text-left transition-colors duration-1 min-[900px]:px-5',
                    'focus-visible:bg-surface-2 focus-visible:outline-none',
                    on
                      ? 'bg-gold-tint/60 shadow-[inset_3px_0_0_rgb(var(--gold))]'
                      : 'hover:bg-surface-2',
                  )}
                >
                  <span className="relative mt-0.5 shrink-0 self-start">
                    <Avatar name={d.client.name} size="md" />
                    <span
                      className="absolute -bottom-1 -right-1.5 grid h-4 w-4 place-items-center rounded-full bg-surface ring-2 ring-surface"
                      aria-hidden="true"
                    >
                      <ChannelIcon type={d.channel} size={10} />
                    </span>
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className={cn('truncate text-[15px] text-ink', d.unread_count ? 'font-bold' : 'font-semibold')}>
                        {d.client.name}
                      </span>
                      <span className="sr-only">{channelLabel(d.channel)}</span>
                      <time
                        dateTime={d.last_message_at}
                        className={cn('ml-auto shrink-0 text-xs tabular-nums', d.unread_count ? 'font-bold text-gold' : 'text-ink-3')}
                      >
                        {listTime(d.last_message_at)}
                      </time>
                    </div>
                    <p className={cn('mt-0.5 truncate text-[13px]', d.unread_count ? 'font-semibold text-ink' : 'text-ink-2')}>
                      {d.preview}
                    </p>
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <Chip variant={d.status} size="sm">
                        {STATUS_LABEL[d.status]}
                      </Chip>
                      {pendingAI[d.uuid] && (
                        <span
                          title="Є пропозиція AI — чекає схвалення"
                          aria-label="Є пропозиція AI"
                          className="inline-flex min-h-[22px] items-center gap-1 rounded-pill border border-gold/35 bg-gold-tint px-2"
                        >
                          <Bot size={12} className="text-gold" aria-hidden="true" />
                          <span className="text-[11px] font-bold leading-none text-gold">AI</span>
                        </span>
                      )}
                      {!d.ai_active && (
                        <Chip variant="muted" size="sm">
                          Людина
                        </Chip>
                      )}
                      <Badge count={d.unread_count} className="ml-auto" aria-label={`${d.unread_count} непрочитаних`} />
                    </div>
                  </div>
                </button>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}
