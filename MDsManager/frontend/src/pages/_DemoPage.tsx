/**
 * UI-kit showcase — available only in `npm run dev` at `/_demo` (see App.tsx).
 * Not linked from the app; the production bundle does not include this file.
 */
import { CalendarPlus, Mail, Phone, Search, Send, Trash2, User } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import {
  Avatar,
  Badge,
  Button,
  Chip,
  Divider,
  Field,
  Input,
  Sheet,
  Skeleton,
  Table,
  toast,
  type AvatarSize,
  type ButtonSize,
  type ButtonVariant,
  type ChipVariant,
  type SheetProps,
  type TableColumn,
} from '../components/ui';

const VARIANTS: ButtonVariant[] = ['primary', 'secondary', 'ghost', 'danger'];
const SIZES: ButtonSize[] = ['sm', 'md', 'lg'];
const CHIPS: Array<[ChipVariant, string]> = [
  ['new', 'Новий'],
  ['in_progress', 'В роботі'],
  ['ordered', 'Записано'],
  ['lost', 'Втрачено'],
  ['info', 'Інфо'],
];
const AVATAR_SIZES: AvatarSize[] = ['sm', 'md', 'lg', 'xl'];

interface Row extends Record<string, unknown> {
  id: number;
  client: string;
  status: ChipVariant;
  amount: number;
  date: string;
}

const ROWS: Row[] = [
  { id: 1, client: 'Олена Коваль', status: 'ordered', amount: 65000, date: '2026-11-12T15:30:00Z' },
  { id: 2, client: 'Марія Шевчук', status: 'new', amount: 0, date: '2026-11-12T09:10:00Z' },
  { id: 3, client: 'Ірина Ткачук', status: 'in_progress', amount: 120000, date: '2026-11-11T12:00:00Z' },
  { id: 4, client: 'Анна Бондар', status: 'ordered', amount: 45000, date: '2026-11-10T08:45:00Z' },
  { id: 5, client: 'Софія Мельник', status: 'lost', amount: 80000, date: '2026-11-08T16:20:00Z' },
];

const STATUS_LABEL = Object.fromEntries(CHIPS) as Record<ChipVariant, string>;
const money = (kop: number) => (kop ? `${(kop / 100).toLocaleString('uk-UA')} ₴` : '—');
const date = (iso: string) =>
  new Date(iso).toLocaleString('uk-UA', {
    timeZone: 'Europe/Kyiv',
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });

const COLUMNS: Array<TableColumn<Row>> = [
  { key: 'client', label: 'Клієнт', render: (r) => <span className="font-semibold">{r.client}</span> },
  {
    key: 'status',
    label: 'Статус',
    render: (r) => (
      <Chip variant={r.status} size="sm" dot>
        {STATUS_LABEL[r.status]}
      </Chip>
    ),
  },
  { key: 'amount', label: 'Сума', align: 'right', width: 120, render: (r) => money(r.amount) },
  { key: 'date', label: 'Дата', align: 'right', width: 140, render: (r) => date(r.date) },
];

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-4 shadow-sm sm:p-5">
      <header className="mb-4">
        <h2 className="text-lg font-bold text-ink">{title}</h2>
        {hint && <p className="mt-0.5 text-sm text-ink-3">{hint}</p>}
      </header>
      {children}
    </section>
  );
}

function Label({ children }: { children: ReactNode }) {
  return <div className="mb-2 text-2xs font-bold uppercase tracking-wider text-ink-3">{children}</div>;
}

type SheetDemo = { side: SheetProps['side']; width?: number; title: string };
const SHEETS: SheetDemo[] = [
  { side: 'right', title: 'Новий запис' },
  { side: 'right', width: 560, title: 'Широка шторка (560px)' },
  { side: 'bottom', title: 'Нижня шторка' },
];

export default function DemoPage() {
  const [sheet, setSheet] = useState<SheetDemo | null>(null);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState('');
  const nameError = name.length > 0 && name.trim().length < 2 ? "Ім'я занадто коротке" : undefined;

  const save = () => {
    setSaving(true);
    setTimeout(() => {
      setSaving(false);
      setSheet(null);
      toast.success('Запис збережено');
    }, 900);
  };

  return (
    <div className="min-h-full bg-bg">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-4 px-4 py-6 sm:px-7">
        <header className="flex items-center gap-3">
          <div className="grid h-[38px] w-[38px] place-items-center rounded-md bg-gradient-to-br from-[#d8b46a] to-[#a9823b] text-[11px] font-bold tracking-tight text-[#1a1408]">
            M&amp;D
          </div>
          <div>
            <h1 className="font-serif text-2xl font-semibold leading-none text-brand">MDs Manager · UI kit</h1>
            <p className="mt-1 text-sm text-ink-3">Компоненти на токенах MDS Connect. Сторінка доступна лише в dev.</p>
          </div>
        </header>

        <Section title="Buttons" hint="4 варіанти × 3 розміри, завантаження, вимкнена, з іконками">
          <div className="flex flex-col gap-3">
            {VARIANTS.map((v) => (
              <div key={v} className="flex flex-wrap items-center gap-2">
                <span className="w-20 text-xs text-ink-3">{v}</span>
                {SIZES.map((s) => (
                  <Button key={s} variant={v} size={s}>
                    {s.toUpperCase()}
                  </Button>
                ))}
              </div>
            ))}
            <Divider className="my-1" />
            <div className="flex flex-wrap items-center gap-2">
              <Button loading>Зберегти</Button>
              <Button variant="secondary" loading>
                Зберегти
              </Button>
              <Button disabled>Вимкнена</Button>
              <Button variant="secondary" disabled>
                Вимкнена
              </Button>
              <Button iconLeft={<Send size={16} />}>Надіслати</Button>
              <Button variant="secondary" iconRight={<CalendarPlus size={16} />}>
                Записати
              </Button>
              <Button variant="danger" iconLeft={<Trash2 size={16} />}>
                Видалити
              </Button>
            </div>
            <Button fullWidth size="lg" iconLeft={<Send size={18} />}>
              fullWidth
            </Button>
          </div>
        </Section>

        <Section title="Inputs">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Input placeholder="Без підпису" aria-label="Без підпису" />
            <Input label="З підписом" placeholder="Олена Коваль" />
            <Input label="З помилкою" defaultValue="+380 67" error="Номер має містити 12 цифр" />
            <Input label="З підказкою" placeholder="olena.k" helper="Без @, як в Instagram" />
            <Input label="З іконкою" type="email" iconLeft={<Mail size={16} />} placeholder="admin@mds.local" required />
            <Input label="Вимкнене" defaultValue="Лише перегляд" disabled />
          </div>
        </Section>

        <Section title="Fields" hint="Обгортка для будь-якого контрола: підпис, помилка, підказка">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Майстер" htmlFor="demo-master" required helper="Хто виконує послугу">
              <select
                id="demo-master"
                className="h-10 w-full rounded-md border border-line-strong bg-surface px-3 text-base text-ink outline-none focus:border-brand focus:ring-2 focus:ring-brand/20 md:text-sm"
              >
                <option>Ірина</option>
                <option>Олександра</option>
              </select>
            </Field>
            <Field label="Коментар" htmlFor="demo-note" error="Коментар обов'язковий для скасування">
              <textarea
                id="demo-note"
                rows={2}
                className="w-full rounded-md border border-danger bg-surface px-3 py-2 text-base text-ink outline-none focus:ring-2 focus:ring-danger/20 md:text-sm"
              />
            </Field>
            <Field label="Без контрола" helper="Field можна використати і для тексту">
              <span className="text-sm text-ink-2">Салон краси M&amp;D · Київ</span>
            </Field>
          </div>
        </Section>

        <Section title="Chips" hint="5 варіантів × 2 розміри, з крапкою і без">
          <div className="flex flex-col gap-3">
            {(['md', 'sm'] as const).map((size) =>
              [true, false].map((dot) => (
                <div key={`${size}-${dot}`} className="flex flex-wrap items-center gap-2">
                  <span className="w-20 text-xs text-ink-3">
                    {size}
                    {dot ? ' · dot' : ''}
                  </span>
                  {CHIPS.map(([v, label]) => (
                    <Chip key={v} variant={v} size={size} dot={dot}>
                      {label}
                    </Chip>
                  ))}
                </div>
              )),
            )}
          </div>
        </Section>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Section title="Badges" hint="Понад 99 → «99+»; 0 не показується">
            {(['brand', 'danger'] as const).map((v) => (
              <div key={v} className="mb-3 flex items-center gap-3 last:mb-0">
                <span className="w-20 text-xs text-ink-3">{v}</span>
                {[1, 5, 99, 150].map((n) => (
                  <Badge key={n} count={n} variant={v} />
                ))}
              </div>
            ))}
          </Section>

          <Section title="Avatars" hint="sm / md / lg / xl, фото або літера, статус">
            <Label>Без фото · online / offline / away</Label>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              {AVATAR_SIZES.map((s, i) => (
                <Avatar
                  key={s}
                  name={['Олена', 'Марія', 'Ірина', 'Анна'][i]!}
                  size={s}
                  status={(['online', 'offline', 'away', 'online'] as const)[i]}
                />
              ))}
            </div>
            <Label>З фото · фото не завантажилось → літера</Label>
            <div className="flex flex-wrap items-center gap-3">
              {AVATAR_SIZES.map((s) => (
                <Avatar key={s} name="Фото" size={s} src="/mock-attachment.png" />
              ))}
              <Avatar name="Софія" size="lg" src="/missing-photo.png" status="away" />
            </div>
          </Section>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Section title="Sheets" hint="Справа на десктопі, знизу на екранах < 900px">
            <div className="flex flex-wrap gap-2">
              {SHEETS.map((s) => (
                <Button key={s.title} variant="secondary" onClick={() => setSheet(s)}>
                  {s.side === 'bottom' ? 'Знизу' : s.width ? 'Справа, 560px' : 'Справа'}
                </Button>
              ))}
            </div>
          </Section>

          <Section title="Toasts" hint="Зникають за 5 с; на телефоні — по центру">
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => toast.success('Запис створено')}>
                success
              </Button>
              <Button variant="secondary" onClick={() => toast.error('Не вдалося надіслати повідомлення')}>
                error
              </Button>
              <Button variant="secondary" onClick={() => toast.warning('Instagram-токен спливає за 3 дні')}>
                warning
              </Button>
              <Button variant="secondary" onClick={() => toast.info('Нове повідомлення від Олени')}>
                info
              </Button>
            </div>
          </Section>
        </div>

        <Section title="Table" hint="Клік по рядку → тост; порожня таблиця нижче">
          <Table
            columns={COLUMNS}
            data={ROWS}
            onRowClick={(r) => toast.info(`Відкрити: ${r.client}`)}
          />
          <Table className="mt-4" columns={COLUMNS} data={[]} emptyText="Немає записів за період" />
        </Section>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Section title="Skeletons">
            <Label>text</Label>
            <div className="mb-4 flex flex-col gap-2">
              <Skeleton width="80%" />
              <Skeleton width="55%" height={12} />
            </div>
            <Label>circle + text</Label>
            <div className="mb-4 flex items-center gap-3">
              <Skeleton variant="circle" width={40} />
              <div className="flex flex-1 flex-col gap-2">
                <Skeleton width="60%" />
                <Skeleton width="35%" height={12} />
              </div>
            </div>
            <Label>rect</Label>
            <Skeleton variant="rect" height={58} />
          </Section>

          <Section title="Dividers">
            <div className="flex flex-col gap-5 py-2">
              <Divider />
              <Divider label="Сьогодні" />
              <Divider label="або" />
            </div>
          </Section>
        </div>
      </div>

      <Sheet
        open={sheet !== null}
        onClose={() => setSheet(null)}
        side={sheet?.side}
        width={sheet?.width}
        title={sheet?.title}
        footer={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setSheet(null)} className="flex-1">
              Скасувати
            </Button>
            <Button onClick={save} loading={saving} className="flex-1">
              Зберегти
            </Button>
          </div>
        }
      >
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          <Input
            label="Клієнт"
            iconLeft={<User size={16} />}
            value={name}
            onChange={(e) => setName(e.target.value)}
            error={nameError}
            placeholder="Ім'я та прізвище"
            required
          />
          <Input label="Телефон" type="tel" iconLeft={<Phone size={16} />} placeholder="+380" />
          <Input label="Пошук послуги" iconLeft={<Search size={16} />} placeholder="Манікюр, стрижка…" />
          <Divider label="Деталі" />
          <Field label="Статус">
            <div className="flex flex-wrap gap-2">
              {CHIPS.slice(0, 4).map(([v, label]) => (
                <Chip key={v} variant={v} dot>
                  {label}
                </Chip>
              ))}
            </div>
          </Field>
        </form>
      </Sheet>
    </div>
  );
}
