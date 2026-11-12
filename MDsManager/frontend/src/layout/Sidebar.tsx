import { LogOut, Moon, Sun } from 'lucide-react';
import { Fragment } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { Avatar, Badge, IconButton, cn } from '../components/ui';
import { NAV, ROLE_LABEL } from '../lib/nav';
import { logout } from '../lib/session';
import { toggleTheme, useTheme } from '../lib/theme';
import { useAuthStore } from '../store/auth';
import { useInboxStore } from '../store/inbox';

/** Бокова панель MDS Connect (.sidebar): лого, групи розділів, внизу — користувач, тема, вихід. */
export default function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const unread = useInboxStore((s) => s.dialogues.reduce((a, d) => a + d.unread_count, 0));
  const dark = useTheme() === 'dark';

  let lastGroup = '';
  return (
    <aside className="sticky top-0 flex h-full w-60 shrink-0 flex-col overflow-y-auto bg-brand px-3 py-[18px] text-brand-ink max-[900px]:hidden">
      <div className="flex items-center gap-2.5 px-2 pb-[18px] pt-1">
        <div className="brand-mark grid h-[38px] w-[38px] shrink-0 place-items-center rounded-md text-[13px] font-bold tracking-[-.3px]">
          M&amp;D
        </div>
        <div className="min-w-0">
          <div className="font-serif text-xl font-semibold leading-none text-[#f3e6c4]">MDs Manager</div>
          <div className="mt-1 text-2xs uppercase tracking-[1.6px] text-brand-ink/55">Салон M&amp;D</div>
        </div>
      </div>

      <nav aria-label="Розділи">
        {NAV.map((item) => {
          const head = item.group !== lastGroup ? item.group : null;
          lastGroup = item.group;
          const Icon = item.icon;
          return (
            <Fragment key={item.to}>
              {head && (
                <div className="px-3 pb-1.5 pt-3.5 text-2xs uppercase tracking-[1.4px] text-brand-ink/40">{head}</div>
              )}
              <NavLink
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  cn(
                    'mb-px flex items-center gap-3 rounded-sm px-3 py-2 text-[13px] font-semibold transition duration-1',
                    'focus-visible:outline-none focus-visible:shadow-ring',
                    isActive
                      ? 'bg-[rgba(232,212,166,.14)] text-[#f3e6c4] shadow-[inset_2px_0_0_rgb(var(--gold-soft))]'
                      : 'text-brand-ink/80 hover:bg-white/[.06] hover:text-white',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon size={18} strokeWidth={1.8} aria-hidden="true" className={cn(isActive && 'animate-pop')} />
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    {item.to === '/' && <Badge count={unread} variant="danger" aria-label={`${unread} непрочитаних`} />}
                  </>
                )}
              </NavLink>
            </Fragment>
          );
        })}
      </nav>

      <div className="mt-auto flex items-center gap-2.5 border-t border-white/[.08] px-2 pb-1 pt-3">
        <Link to="/settings" className="flex min-w-0 flex-1 items-center gap-2.5 rounded-sm focus-visible:outline-none focus-visible:shadow-ring">
          <Avatar name={user?.display_name || 'Адміністратор'} />
          <div className="min-w-0">
            <b className="block truncate text-[13px] text-white">{user?.display_name || 'Адміністратор'}</b>
            <span className="block truncate text-xs text-brand-ink/55">{ROLE_LABEL[user?.role ?? ''] ?? user?.role ?? ''}</span>
          </div>
        </Link>
        <IconButton title={dark ? 'Світла тема' : 'Темна тема'} aria-label="Змінити тему" onClick={toggleTheme} className="w-8">
          {dark ? <Sun size={18} /> : <Moon size={18} />}
        </IconButton>
        <IconButton title="Вийти" aria-label="Вийти" onClick={logout} className="w-8">
          <LogOut size={18} />
        </IconButton>
      </div>
    </aside>
  );
}
