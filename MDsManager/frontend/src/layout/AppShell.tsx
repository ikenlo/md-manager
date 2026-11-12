import type { ReactNode } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useInboxStore } from '../store/inbox';
import MobileBar from './MobileBar';
import Sidebar from './Sidebar';
import TabBar from './TabBar';

/**
 * Каркас MDS Connect (.app): бокова панель + робоча область. ≤900px — верхня смуга й нижній таббар.
 * Відкритий чат на телефоні займає весь екран (без смуги й таббару): у чату своя шапка з «Назад».
 */
export default function AppShell() {
  const { pathname } = useLocation();
  const chatOpen = useInboxStore((s) => s.activeDialogueUuid !== null);
  const immersive = pathname === '/' && chatOpen;

  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className={immersive ? 'max-[900px]:hidden' : undefined}>
          <MobileBar />
        </div>
        <div className="min-h-0 flex-1">
          <Outlet />
        </div>
      </div>
      <div className={immersive ? 'max-[900px]:hidden' : undefined}>
        <TabBar />
      </div>
    </div>
  );
}

/** Прокручувана сторінка з полями як у Connect (.main): 22/28px, на телефоні 14/16 і місце під таббар. */
export function PageContainer({ children }: { children: ReactNode }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="anim-in max-w-[1360px] px-7 pb-[90px] pt-[22px] max-[900px]:px-4 max-[900px]:pb-[calc(104px+env(safe-area-inset-bottom))] max-[900px]:pt-3.5">
        {children}
      </div>
    </div>
  );
}
