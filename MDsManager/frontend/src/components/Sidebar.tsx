import {
  BarChart3,
  Bot,
  CalendarDays,
  LogOut,
  Megaphone,
  MessageCircle,
  Settings,
  Users,
} from 'lucide-react';
import { logout } from '../lib/session';
import { useAuthStore } from '../store/auth';

const NAV = [
  { key: 'chats', label: 'Чати', Icon: MessageCircle, badge: 4 },
  { key: 'calendar', label: 'Записи', Icon: CalendarDays },
  { key: 'clients', label: 'Клієнти', Icon: Users },
  { key: 'agents', label: 'AI-агенти', Icon: Bot },
  { key: 'marketing', label: 'Реклама', Icon: Megaphone },
  { key: 'analytics', label: 'Аналітика', Icon: BarChart3 },
];

export default function Sidebar({ active = 'chats' }: { active?: string }) {
  const user = useAuthStore((s) => s.user);
  return (
    <aside className="flex w-24 shrink-0 flex-col items-center bg-brand py-6 text-brand-ink">
      <div className="mb-8 font-serif text-[28px] font-bold leading-none tracking-wide text-gold">
        M&amp;D
      </div>
      <nav className="flex flex-1 flex-col items-center gap-2">
        {NAV.map(({ key, label, Icon, badge }) => {
          const on = key === active;
          return (
            <button
              key={key}
              type="button"
              title={label}
              className={`relative flex w-[72px] flex-col items-center gap-1 rounded-2xl py-2.5 text-[11px] font-semibold transition ${
                on ? 'bg-brand-2 text-gold-soft' : 'text-brand-ink/60 hover:bg-brand-2/60 hover:text-brand-ink'
              }`}
            >
              {on && <span className="absolute left-[-12px] top-3 h-6 w-1 rounded-r bg-gold" />}
              <Icon size={22} strokeWidth={1.8} />
              {label}
              {badge ? (
                <span className="absolute right-3 top-1.5 min-w-[18px] rounded-full bg-gold px-1 text-[10px] leading-[18px] text-brand">
                  {badge}
                </span>
              ) : null}
            </button>
          );
        })}
      </nav>
      <div className="flex flex-col items-center gap-2">
        <button type="button" title="Налаштування" className="rounded-xl p-2.5 text-brand-ink/60 hover:bg-brand-2 hover:text-brand-ink">
          <Settings size={22} strokeWidth={1.8} />
        </button>
        <div
          className="flex h-10 w-10 items-center justify-center rounded-full border border-gold/60 text-base font-bold text-gold-soft"
          title={user?.display_name}
        >
          {user?.display_name?.[0] ?? 'Д'}
        </div>
        <button
          type="button"
          title="Вийти"
          aria-label="Вийти"
          onClick={logout}
          className="rounded-xl p-2 text-brand-ink/50 transition hover:bg-brand-2 hover:text-brand-ink focus-visible:outline-none focus-visible:shadow-ring"
        >
          <LogOut size={18} />
        </button>
      </div>
    </aside>
  );
}
