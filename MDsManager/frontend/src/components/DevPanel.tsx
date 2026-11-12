/**
 * Симуляція Meta для розробки (лише `npm run dev`; бекенд з MOCK_META=true).
 * Результат приходить назад через WebSocket — так перевіряється весь ланцюжок.
 */
import axios from 'axios';
import { AlertOctagon, FlaskConical, Image, MessageSquarePlus, X } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { devApi } from '../api/inbox';
import { useInboxStore } from '../store/inbox';
import { Button, Field, Input, Sheet, cn, toast } from './ui';

const NAMES = ['Оксана Левчук', 'Дарина Мороз', 'Катерина Бойко', 'Юлія Савчук', 'Вікторія Ткач'];
const TEXTS = [
  'Добрий день! Чи є вільний час на манікюр у суботу?',
  'Скільки коштує фарбування коренів?',
  'Хочу записатися на брови на цьому тижні',
];
const pick = <T,>(a: T[]) => a[Math.floor(Math.random() * a.length)]!;

function errorText(e: unknown): string {
  if (axios.isAxiosError(e) && e.response?.status === 404) return 'Тестові ендпоінти вимкнені (MOCK_META=false?)';
  return 'Не вдалося виконати запит';
}

export default function DevPanel() {
  const active = useInboxStore((s) => s.activeDialogueUuid);
  const [open, setOpen] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [form, setForm] = useState({ name: '', username: '', text: '', channel: 'instagram' as 'instagram' | 'facebook' });

  const openSheet = () => {
    const name = pick(NAMES);
    setForm({ name, username: name.split(' ')[0]!.toLowerCase() + '.' + Math.floor(Math.random() * 90 + 10), text: pick(TEXTS), channel: 'instagram' });
    setSheet(true);
  };

  const run = async (key: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(key);
    try {
      await fn();
      toast.success(ok);
      return true;
    } catch (e) {
      toast.error(errorText(e));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const done = await run(
      'inbound',
      () => devApi.simulateInbound({ client_name: form.name, username: form.username, text: form.text, channel: form.channel }),
      'Вхідне створено — чекайте його через WebSocket',
    );
    if (done) setSheet(false);
  };

  return (
    <>
      <div className="fixed bottom-24 right-3 z-40 flex flex-col items-end gap-2 min-[900px]:bottom-32 min-[900px]:right-5">
        {open && (
          <div className="flex w-56 flex-col gap-1.5 rounded-lg border border-line bg-surface/95 p-2 shadow-lg backdrop-blur">
            <div className="px-1 pb-0.5 text-2xs font-bold uppercase tracking-wider text-ink-3">Dev · симуляція Meta</div>
            <Button size="sm" variant="secondary" iconLeft={<MessageSquarePlus size={14} />} onClick={openSheet} className="justify-start">
              Simulate inbound
            </Button>
            <Button
              size="sm"
              variant="secondary"
              iconLeft={<Image size={14} />}
              disabled={!active}
              loading={busy === 'att'}
              title={active ? undefined : 'Спершу відкрийте діалог'}
              onClick={() => active && run('att', () => devApi.simulateAttachment(active), 'Фото додано')}
              className="justify-start"
            >
              Simulate attachment
            </Button>
            <Button
              size="sm"
              variant="secondary"
              iconLeft={<AlertOctagon size={14} />}
              disabled={!active}
              loading={busy === 'fail'}
              title={active ? undefined : 'Спершу відкрийте діалог'}
              onClick={() =>
                active && run('fail', () => devApi.triggerFailure(active, 'Повідомлення, яке не дійде'), 'Збій поставлено в чергу')
              }
              className="justify-start"
            >
              Trigger failure
            </Button>
          </div>
        )}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-label="Dev-панель"
          className={cn(
            'grid h-10 w-10 place-items-center rounded-full bg-ink text-white shadow-lg transition hover:opacity-100 focus-visible:outline-none focus-visible:shadow-ring',
            open ? 'opacity-100' : 'opacity-60',
          )}
        >
          {open ? <X size={18} /> : <FlaskConical size={18} />}
        </button>
      </div>

      <Sheet
        open={sheet}
        onClose={() => setSheet(false)}
        title="Simulate inbound"
        footer={
          <Button type="submit" form="dev-inbound" fullWidth loading={busy === 'inbound'}>
            Надіслати як клієнт
          </Button>
        }
      >
        <form id="dev-inbound" onSubmit={submit} className="flex flex-col gap-4">
          <Input label="Ім'я клієнта" name="client_name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          <Input label="Нікнейм" name="username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          <Input label="Текст" name="text" value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} required />
          <Field label="Канал">
            <div className="flex gap-2">
              {(['instagram', 'facebook'] as const).map((c) => (
                <Button key={c} size="sm" variant={form.channel === c ? 'primary' : 'secondary'} onClick={() => setForm({ ...form, channel: c })}>
                  {c === 'instagram' ? 'Instagram' : 'Facebook'}
                </Button>
              ))}
            </div>
          </Field>
        </form>
      </Sheet>
    </>
  );
}
