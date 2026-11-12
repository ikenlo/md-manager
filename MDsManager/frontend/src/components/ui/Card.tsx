import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from './cn';

/** Surface block (MDS Connect `.card`): white, 1px line, radius 16, soft shadow. */
export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('rounded-xl border border-line bg-surface p-4 shadow-sm', className)} {...rest} />;
}

/** Card title row (MDS Connect `.card-head`): title left, actions right. */
export function CardHead({ title, actions, className }: { title: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <div className={cn('mb-2.5 flex flex-wrap items-center justify-between gap-x-2.5 gap-y-1', className)}>
      <h3 className="m-0 text-[15px] font-bold text-ink">{title}</h3>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
