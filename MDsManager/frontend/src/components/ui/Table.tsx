import { Inbox } from 'lucide-react';
import type { KeyboardEvent, ReactNode } from 'react';
import { cn } from './cn';
import { EmptyState } from './EmptyState';

export interface TableColumn<T> {
  /** Field of the row to display (also the React key of the column). */
  key: string;
  /** Header text (also the label of the value in the mobile card layout). */
  label: ReactNode;
  /** CSS width, e.g. `120` (px) or `'30%'`. */
  width?: number | string;
  /** Cell alignment. Use `right` for numbers/money. Defaults to `left`. */
  align?: 'left' | 'center' | 'right';
  /** Custom cell renderer; by default `String(row[key])` is shown. */
  render?: (row: T, index: number) => ReactNode;
}

export interface TableProps<T> {
  columns: Array<TableColumn<T>>;
  data: T[];
  /** Shown instead of rows when `data` is empty. Defaults to «Немає даних». */
  emptyText?: ReactNode;
  /** Makes rows clickable (and keyboard-focusable with Enter/Space). */
  onRowClick?: (row: T, index: number) => void;
  /** Stable row key. Defaults to `row.uuid ?? row.id ?? index`. */
  rowKey?: (row: T, index: number) => string | number;
  className?: string;
}

const ALIGN = { left: 'text-left', center: 'text-center', right: 'text-right' } as const;

function defaultKey(row: unknown, index: number): string | number {
  const r = row as { uuid?: unknown; id?: unknown };
  if (typeof r?.uuid === 'string') return r.uuid;
  if (typeof r?.id === 'string' || typeof r?.id === 'number') return r.id;
  return index;
}

function cellValue(v: unknown): ReactNode {
  if (v === null || v === undefined || v === '') return <span className="text-ink-3">—</span>;
  return String(v);
}

const textOf = (n: ReactNode) => (typeof n === 'string' || typeof n === 'number' ? String(n) : undefined);

/**
 * Data table in the MDS Connect style (`.card.table-wrap`): uppercase sticky header, hover rows,
 * empty state. ≤640px it turns into a list of cards with «label: value» lines (Connect `table.resp`).
 */
export function Table<T extends Record<string, unknown>>({
  columns,
  data,
  emptyText = 'Немає даних',
  onRowClick,
  rowKey = defaultKey,
  className,
}: TableProps<T>) {
  const onKey = (e: KeyboardEvent<HTMLTableRowElement>, row: T, i: number) => {
    if (onRowClick && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      onRowClick(row, i);
    }
  };

  return (
    <div className={cn('overflow-x-auto rounded-xl border border-line bg-surface py-1 shadow-sm', className)}>
      <table className="table-resp w-full border-collapse text-sm">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                style={c.width !== undefined ? { width: c.width } : undefined}
                className={cn(
                  'sticky top-0 z-[1] whitespace-nowrap border-b border-line bg-surface-2 px-3.5 py-2.5',
                  'text-2xs font-bold uppercase tracking-[.06em] text-ink-3',
                  ALIGN[c.align ?? 'left'],
                )}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td colSpan={columns.length}>
                <EmptyState icon={<Inbox size={24} strokeWidth={1.6} aria-hidden="true" />}>{emptyText}</EmptyState>
              </td>
            </tr>
          ) : (
            data.map((row, i) => (
              <tr
                key={rowKey(row, i)}
                onClick={onRowClick ? () => onRowClick(row, i) : undefined}
                onKeyDown={onRowClick ? (e) => onKey(e, row, i) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                className={cn(
                  'transition-colors duration-1 hover:bg-surface-2 [&:last-child>td]:border-b-0',
                  onRowClick && 'cursor-pointer focus-visible:bg-surface-2 focus-visible:outline-none',
                )}
              >
                {columns.map((c, ci) => (
                  <td
                    key={c.key}
                    data-label={textOf(c.label)}
                    className={cn(
                      'border-b border-line px-3.5 py-2.5 align-middle text-ink',
                      ALIGN[c.align ?? 'left'],
                      c.align === 'right' && 'whitespace-nowrap tabular-nums',
                      ci === 0 && 'resp-title',
                    )}
                  >
                    {c.render ? c.render(row, i) : cellValue(row[c.key])}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
