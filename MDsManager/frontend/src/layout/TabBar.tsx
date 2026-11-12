import { Menu } from 'lucide-react';
import { NavLink, useLocation } from 'react-router-dom';
import { Badge, cn } from '../components/ui';
import { MOBILE_TABS, NAV } from '../lib/nav';
import { useInboxStore } from '../store/inbox';

/** Плаваючий нижній таббар на телефоні (MDS Connect .tabbar): лише іконки, підписи — для читалок. */
export default function TabBar() {
  const { pathname } = useLocation();
  const unread = useInboxStore((s) => s.dialogues.reduce((a, d) => a + d.unread_count, 0));
  const items = MOBILE_TABS.map((to) =>
    to === '/more' ? { to, label: 'Меню', icon: Menu } : NAV.find((n) => n.to === to)!,
  );
  // «Меню» підсвічене і для розділів, яких немає в таббарі
  const moreActive = !MOBILE_TABS.includes(pathname);

  return (
    <nav
      aria-label="Розділи"
      className={cn(
        'fixed bottom-[calc(10px+env(safe-area-inset-bottom))] left-[max(12px,env(safe-area-inset-left))] right-[max(12px,env(safe-area-inset-right))] z-20',
        'mx-auto hidden h-16 max-w-[480px] items-center gap-0.5 rounded-pill p-1.5 max-[900px]:flex',
        'border border-white/70 bg-white/[.72] shadow-[0_12px_32px_-8px_rgba(15,25,20,.28),0_2px_6px_rgba(15,25,20,.08),inset_0_1px_0_rgba(255,255,255,.9)] backdrop-blur-[22px] backdrop-saturate-[180%]',
        'dark:border-white/[.08] dark:bg-[rgba(17,36,29,.72)] dark:shadow-[0_12px_32px_-8px_rgba(0,0,0,.6),inset_0_1px_0_rgba(255,255,255,.06)]',
      )}
    >
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          aria-label={label}
          title={label}
          className={({ isActive }) =>
            cn(
              'relative flex h-[52px] min-w-0 flex-1 items-center justify-center rounded-pill transition duration-1 active:scale-[.94]',
              '[-webkit-tap-highlight-color:transparent] focus-visible:outline-none focus-visible:shadow-ring',
              isActive || (to === '/more' && moreActive)
                ? 'bg-[rgba(20,30,25,.08)] text-brand dark:bg-white/10 dark:text-gold'
                : 'text-ink-2',
            )
          }
        >
          {({ isActive }) => (
            <>
              <Icon size={25} strokeWidth={isActive ? 2.4 : 2} aria-hidden="true" />
              {to === '/' && unread > 0 && (
                <Badge count={unread} variant="danger" className="absolute left-[calc(50%+6px)] top-2" aria-hidden="true" />
              )}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
