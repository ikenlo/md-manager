import { Bot, LogOut, MessageCircle, Search } from 'lucide-react';
import { useMemo } from 'react';
import { listTime } from '../lib/format';
import { logout } from '../lib/session';
import { useAIStore } from '../store/ai';
import { STATUS_LABEL, useInboxStore, type InboxFilter } from '../store/inbox';
import type { ChannelType, Dialogue } from '../types';
import ChannelIcon, { channelLabel } from './ChannelIcon';
import { Avatar, Badge, Button, Chip, Input, Skeleton, cn } from './ui';

const FILTERS: Array<{ key: InboxFilter; label: string }> = [
  { key: 'all', label: 'Всі' },
  { key: 'new', label: 'Нові' },
  { key: 'in_progress', label: 'В роботі' },
  { key: 'ordered', label: 'Записані' },
  { key: 'unread', label: 'Непрочитані' },
];

/** Кольорова обводка аватара за каналом. */
export const CHANNEL_RING: Record<ChannelType, string> = {
  instagram: 'ring-[#c13584]',
  facebook: 'ring-[#1877f2]',
  telegram: 'ring-[#2aa3df]',
};

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
      className={cn('flex min-h-0 w-full flex-col border-r border-line bg-surface min-[900px]:w-[380px] min-[900px]:shrink-0', className)}
    >
      <header className="px-4 pb-3 pt-5 sm:px-5">
        <div className="flex items-center gap-2.5">
          {/* На телефоні бокової панелі немає — лого і вихід тут */}
          <div
            aria-hidden="true"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-sm bg-gradient-to-br from-[#d8b46a] to-[#a9823b] text-[10px] font-bold tracking-tight text-[#1a1408] min-[900px]:hidden"
          >
            M&amp;D
          </div>
          <h1 className="font-serif text-2xl font-bold leading-none text-brand">Діалоги</h1>
          {unreadTotal > 0 && (
            <Badge count={unreadTotal} aria-label={`${unreadTotal} непрочитаних повідомлень`} title="Непрочитані" />
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={logout}
            aria-label="Вийти"
            title="Вийти"
            className="ml-auto px-2 text-ink-3 min-[900px]:hidden"
          >
            <LogOut size={16} />
          </Button>
        </div>

        <Input
          className="mt-4"
          type="search"
          aria-label="Пошук клієнта"
          placeholder="Пошук клієнта..."
          iconLeft={<Search size={16} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          inputClassName="bg-surface-2 border-line"
        />

        <div role="tablist" aria-label="Фільтр діалогів" className="mt-3 flex flex-wrap gap-1">
          {FILTERS.map(({ key, label }) => {
            const on = filter === key;
            return (
              <Button
                key={key}
                role="tab"
                aria-selected={on}
                variant={on ? 'primary' : 'ghost'}
                size="sm"
                onClick={() => setFilter(key)}
                className={cn('shrink-0 gap-1 rounded-pill', on ? 'text-white shadow-none' : 'text-ink-2')}
              >
                {label}
                <span className={cn('tabular-nums', on ? 'text-gold-soft' : 'text-ink-3')}>{counts[key]}</span>
              </Button>
            );
          })}
        </div>
      </header>

      <ul className="min-h-0 flex-1 overflow-y-auto border-t border-line" aria-label="Список діалогів">
        {isLoading && dialogues.length === 0 ? (
          [0, 1, 2].map((i) => (
            <li key={i} className="flex gap-3 border-b border-line px-4 py-3" aria-hidden="true">
              <Skeleton variant="circle" width={40} className="bg-surface-3" />
              <div className="flex flex-1 flex-col gap-2 pt-1">
                <Skeleton width="50%" className="bg-surface-3" />
                <Skeleton width="80%" height={12} className="bg-surface-3" />
              </div>
            </li>
          ))
        ) : visible.length === 0 ? (
          <li className="flex flex-col items-center gap-3 px-6 py-14 text-center text-sm text-ink-3">
            <span className="grid h-[52px] w-[52px] place-items-center rounded-full bg-surface-2 ring-1 ring-inset ring-line">
              <MessageCircle size={24} strokeWidth={1.6} aria-hidden="true" />
            </span>
            {loadError ?? (dialogues.length ? 'Немає діалогів за цим фільтром' : 'Немає діалогів')}
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
                    'flex w-full gap-3 border-l-4 py-3 pl-3 pr-4 text-left transition-colors duration-1 sm:pl-4',
                    'focus-visible:bg-surface-2 focus-visible:outline-none',
                    on ? 'border-gold bg-brand/5' : 'border-transparent hover:bg-surface-2',
                  )}
                >
                  <Avatar
                    name={d.client.name}
                    size="md"
                    className={cn('mt-0.5 rounded-full ring-2 ring-offset-2 ring-offset-surface', CHANNEL_RING[d.channel])}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className={cn('truncate text-[15px] text-ink', d.unread_count ? 'font-bold' : 'font-semibold')}>
                        {d.client.name}
                      </span>
                      <ChannelIcon type={d.channel} size={13} />
                      <span className="sr-only">{channelLabel(d.channel)}</span>
                      <time dateTime={d.last_message_at} className="ml-auto shrink-0 text-xs text-ink-3">
                        {listTime(d.last_message_at)}
                      </time>
                    </div>
                    <p className={cn('mt-0.5 truncate text-sm', d.unread_count ? 'font-medium text-ink' : 'text-ink-2')}>
                      {d.preview}
                    </p>
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <Chip variant={d.status} size="sm" dot>
                        {STATUS_LABEL[d.status]}
                      </Chip>
                      {pendingAI[d.uuid] && (
                        <span
                          title="Є пропозиція AI — чекає схвалення"
                          aria-label="Є пропозиція AI"
                          className="inline-flex items-center gap-1 rounded-md border border-gold-soft/50 bg-gold-tint px-1.5 py-0.5"
                        >
                          <Bot size={12} className="text-gold" aria-hidden="true" />
                          <span className="text-[10px] font-semibold leading-none text-gold">AI</span>
                        </span>
                      )}
                      {!d.ai_active && (
                        <Chip variant="new" size="sm">
                          Людина
                        </Chip>
                      )}
                      <Badge
                        count={d.unread_count}
                        className="ml-auto"
                        aria-label={`${d.unread_count} непрочитаних`}
                      />
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
