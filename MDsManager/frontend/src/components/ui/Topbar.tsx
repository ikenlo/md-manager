import type { ReactNode } from 'react';
import { cn } from './cn';

/**
 * Page title row (MDS Connect `.topbar`): h1 + subtitle on the left, actions on the right.
 * Below 900px the h1 is hidden — the mobile bar already shows the page title.
 */
export function Topbar({ title, sub, actions, className }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <div className={cn('mb-[18px] flex flex-wrap items-center justify-between gap-3 max-[900px]:mb-3', className)}>
      <div className="min-w-0">
        <h1 className="m-0 text-2xl font-bold text-ink max-[900px]:hidden">{title}</h1>
        {sub && <div className="mt-0.5 text-[13px] text-ink-3 max-[900px]:mt-0">{sub}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
