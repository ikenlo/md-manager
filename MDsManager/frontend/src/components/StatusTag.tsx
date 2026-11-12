import type { DialogueStatus } from '../types';

export const STATUS_LABEL: Record<DialogueStatus, string> = {
  new: 'Новий',
  in_progress: 'В роботі',
  ordered: 'Записано',
  lost: 'Втрачено',
};

const CLS: Record<DialogueStatus, string> = {
  new: 'bg-brand text-brand-ink',
  in_progress: 'bg-gold-tint text-gold',
  ordered: 'bg-[#e3ece7] text-brand-2',
  lost: 'bg-surface-2 text-ink-3',
};

export default function StatusTag({ status }: { status: DialogueStatus }) {
  return (
    <span className={`${CLS[status]} rounded-full px-2 py-0.5 text-[11px] font-semibold leading-4`}>
      {STATUS_LABEL[status]}
    </span>
  );
}
