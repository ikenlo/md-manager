import { Inbox } from 'lucide-react';
import type { KeyboardEvent, ReactNode } from 'react';
import { cn } from './cn';

export interface TableColumn<T> {
  /** Field of the row to display (also the React key of the column). */
  key: string;
  /** Header text. */
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

/**
 * Data table in the MDS Connect style (`.card.table-wrap`): sticky header,
 * hover rows, empty state. Scrolls horizontally when it does not fit.
 *
 * @example
 * <Table
 *   columns={[{ key: 'name', label: 'Клієнт' }, { key: 'total', label: 'Сума', align: 'right', render: (r) => money(r.total) }]}
 *   data={clients}
 *   onRowClick={(c) => openClient(c.uuid)}
 * />
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
    <div className={cn('overflow-x-auto rounded-xl border border-line bg-surface shadow-sm', className)}>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                style={c.width !== undefined ? { width: c.width } : undefined}
                className={cn(
                  'sticky top-0 z-[1] whitespace-nowrap border-b border-line bg-surface-2 px-3.5 py-2.5 text-xs font-semibold text-ink-2',
                  ALIGN[c.align ?? 'left'],
                )}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-10">
                <div className="flex flex-col items-center gap-3 text-center text-ink-3">
                  <span className="grid h-[52px] w-[52px] place-items-center rounded-full bg-surface-2 ring-1 ring-inset ring-line">
                    <Inbox size={24} strokeWidth={1.6} aria-hidden="true" />
                  </span>
                  <span className="text-sm">{emptyText}</span>
                </div>
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
                  'transition-colors duration-1 hover:bg-surface-2',
                  onRowClick && 'cursor-pointer focus-visible:bg-surface-2 focus-visible:outline-none',
                )}
              >
                {columns.map((c) => (
                  <td
                    key={c.key}
                    className={cn(
                      'px-3.5 py-2.5 align-middle text-ink',
                      ALIGN[c.align ?? 'left'],
                      c.align === 'right' && 'whitespace-nowrap tabular-nums',
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
