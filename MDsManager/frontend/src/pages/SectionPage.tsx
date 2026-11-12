import { Check, type LucideIcon } from 'lucide-react';
import { Card, CardHead, Chip, EmptyState, Topbar } from '../components/ui';
import { PageContainer } from '../layout/AppShell';

export interface SectionPageProps {
  title: string;
  sub: string;
  icon: LucideIcon;
  /** Коли з'явиться, напр. «Фаза 4». */
  phase: string;
  /** Що буде в розділі. */
  planned: string[];
}

/** Розділ, який ще в розробці: заголовок як у Connect, порожній стан і план. */
export default function SectionPage({ title, sub, icon: Icon, phase, planned }: SectionPageProps) {
  return (
    <PageContainer>
      <Topbar title={title} sub={sub} actions={<Chip variant="warn">{phase}</Chip>} />
      <div className="grid grid-cols-1 gap-3 min-[1100px]:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card>
          <EmptyState icon={<Icon size={24} strokeWidth={1.6} aria-hidden="true" />}>
            <b className="block text-[15px] text-ink">Розділ у розробці</b>
            <span className="mt-1 block">Тут з'явиться «{title}». Поки що все важливе — у «Діалогах».</span>
          </EmptyState>
        </Card>
        <Card>
          <CardHead title="Що буде в розділі" />
          <ul className="flex flex-col gap-2.5">
            {planned.map((p) => (
              <li key={p} className="flex items-start gap-2.5 text-sm text-ink-2">
                <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-ok-bg text-ok">
                  <Check size={12} strokeWidth={2.6} aria-hidden="true" />
                </span>
                {p}
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </PageContainer>
  );
}
