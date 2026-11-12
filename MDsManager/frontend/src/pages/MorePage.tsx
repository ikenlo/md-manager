import { ChevronRight, LogOut, Moon, Sun } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Card, Topbar } from '../components/ui';
import { PageContainer } from '../layout/AppShell';
import { MOBILE_TABS, NAV } from '../lib/nav';
import { logout } from '../lib/session';
import { toggleTheme, useTheme } from '../lib/theme';

const rowCls =
  'flex w-full items-center gap-3 rounded-sm p-3 text-left text-sm font-semibold text-ink transition duration-1 hover:bg-surface-2 focus-visible:outline-none focus-visible:shadow-ring';

/** «Меню» на телефоні (Connect viewMore): розділи поза таббаром, тема, вихід. */
export default function MorePage() {
  const dark = useTheme() === 'dark';
  return (
    <PageContainer>
      <Topbar title="Меню" />
      <Card className="p-1.5">
        {NAV.filter((n) => !MOBILE_TABS.includes(n.to)).map(({ to, label, icon: Icon }) => (
          <Link key={to} to={to} className={rowCls}>
            <Icon size={18} className="text-ink-2" aria-hidden="true" />
            <span className="flex-1">{label}</span>
            <ChevronRight size={16} className="text-ink-3" aria-hidden="true" />
          </Link>
        ))}
        <button type="button" onClick={toggleTheme} className={rowCls}>
          {dark ? <Sun size={18} className="text-ink-2" aria-hidden="true" /> : <Moon size={18} className="text-ink-2" aria-hidden="true" />}
          <span className="flex-1">{dark ? 'Світла тема' : 'Темна тема'}</span>
        </button>
        <button type="button" onClick={logout} className={rowCls.replace('text-ink ', 'text-danger ')}>
          <LogOut size={18} aria-hidden="true" />
          <span className="flex-1">Вийти</span>
        </button>
      </Card>
      <p className="mt-3.5 text-center text-[13px] text-ink-3">MDs Manager · салон M&amp;D</p>
    </PageContainer>
  );
}
