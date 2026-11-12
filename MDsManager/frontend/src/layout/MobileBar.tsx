import { ChevronLeft, Moon, Sun } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { IconButton } from '../components/ui';
import { MOBILE_TABS, titleFor } from '../lib/nav';
import { toggleTheme, useTheme } from '../lib/theme';

/** Липка верхня смуга на телефоні (MDS Connect .mbar): лого або «Назад», назва розділу. */
export default function MobileBar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const dark = useTheme() === 'dark';
  const isTab = MOBILE_TABS.includes(pathname);

  return (
    <header className="sticky top-0 z-[25] hidden shrink-0 items-center gap-2.5 border-b border-line bg-bg px-4 pb-2.5 pt-[calc(10px+env(safe-area-inset-top))] max-[900px]:flex">
      {isTab ? (
        <div className="brand-mark grid h-[30px] w-[30px] shrink-0 place-items-center rounded-sm text-2xs font-bold" aria-hidden="true">
          M&amp;D
        </div>
      ) : (
        <button
          type="button"
          onClick={() => navigate('/more')}
          className="-ml-1 inline-flex items-center gap-0.5 rounded-sm py-1 pr-2.5 text-[15px] font-semibold text-brand-2 focus-visible:outline-none focus-visible:shadow-ring dark:text-gold"
        >
          <ChevronLeft size={22} aria-hidden="true" />
          Назад
        </button>
      )}
      <b className="min-w-0 flex-1 truncate text-base text-ink">{titleFor(pathname)}</b>
      <IconButton aria-label="Змінити тему" title={dark ? 'Світла тема' : 'Темна тема'} onClick={toggleTheme} className="text-ink-3">
        {dark ? <Sun size={18} /> : <Moon size={18} />}
      </IconButton>
    </header>
  );
}
