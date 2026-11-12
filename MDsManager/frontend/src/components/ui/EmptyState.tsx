import type { ReactNode } from 'react';
import { cn } from './cn';

/** Empty / no-results block (MDS Connect `.empty`): icon in a soft circle + text. */
export function EmptyState({ icon, children, className }: { icon: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex flex-col items-center gap-3 px-3 py-8 text-center text-sm text-ink-3 [text-wrap:balance]', className)}>
      <span className="grid h-[52px] w-[52px] place-items-center rounded-full bg-surface-2 text-ink-3 shadow-[inset_0_0_0_1px_rgb(var(--line))]">
        {icon}
      </span>
      <div>{children}</div>
    </div>
  );
}
