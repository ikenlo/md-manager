// Демо-дані для оболонки «Діалоги» (Фаза 1, до підключення реального API).
// Час рахується відносно моменту завантаження, щоб список показував «сьогодні».
// Вхідні: delivered (ще не прочитано) / read. Вихідні — різні статуси для демо іконок
// (sent / delivered / read / failed; queued з'являється після «Надіслати»). Системні — без direction/status.
// Марія — прострочений токен каналу; Ірина — останнє вхідне 25 год тому (банер 24-годинного вікна).
import type { Dialogue, Message } from '../types';

const ago = (minutes: number): string => new Date(Date.now() - minutes * 60_000).toISOString();

const OLENA = 'demo-dlg-olena';
const MARIA = 'demo-dlg-maria';
const IRYNA = 'demo-dlg-iryna';

export const mockMessages: Record<string, Message[]> = {
  [OLENA]: [
    {
      uuid: 'demo-msg-olena-1',
      sender_type: 'client',
      direction: 'inbound',
      status: 'read',
      content: 'Добрий день! Хочу записатися на манікюр з покриттям.',
      created_at: ago(48),
    },
    {
      uuid: 'demo-msg-olena-2',
      sender_type: 'agent',
      direction: 'outbound',
      status: 'read',
      content: 'Вітаю, Олено! Манікюр з покриттям — 650 грн, триває близько 1,5 год. На який день вам зручно?',
      created_at: ago(47),
    },
    {
      uuid: 'demo-msg-olena-3',
      sender_type: 'client',
      direction: 'inbound',
      status: 'read',
      content: 'А можна одразу з дизайном на два нігті? Ось приклади 👇',
      created_at: ago(30),
      attachments: [
        { url: '/mock-attachment.png', type: 'image/png', name: 'design-1.png', size: 70 },
        { url: '/mock-attachment.png', type: 'image/png', name: 'design-2.png', size: 70 },
      ],
    },
    {
      uuid: 'demo-msg-olena-4',
      sender_type: 'human',
      direction: 'outbound',
      status: 'delivered',
      content: 'Так, звісно! Дизайн +50 грн за ніготь, майстер Ірина зробить 😊',
      created_at: ago(20),
    },
    {
      uuid: 'demo-msg-olena-5',
      sender_type: 'client',
      direction: 'inbound',
      status: 'delivered',
      content: 'Дякую! Підкажіть, чи є вільний час на четвер після 17:00?',
      created_at: ago(5),
    },
  ],
  [MARIA]: [
    {
      uuid: 'demo-msg-maria-1',
      sender_type: 'client',
      direction: 'inbound',
      status: 'read',
      content: 'Доброго дня!',
      created_at: ago(16),
    },
    {
      uuid: 'demo-msg-maria-2',
      sender_type: 'agent',
      direction: 'outbound',
      status: 'failed',
      content: 'Вітаємо в M&D! Чим можемо допомогти?',
      created_at: ago(15),
    },
    {
      uuid: 'demo-msg-maria-3',
      sender_type: 'client',
      direction: 'inbound',
      status: 'delivered',
      content: 'Доброго дня, скільки коштує педикюр?',
      created_at: ago(12),
    },
  ],
  [IRYNA]: [
    {
      uuid: 'demo-msg-iryna-1',
      sender_type: 'client',
      direction: 'inbound',
      status: 'read',
      content: 'Привіт! Є вільне віконце на стрижку завтра зранку?',
      created_at: ago(25 * 60 + 12),
    },
    {
      uuid: 'demo-msg-iryna-2',
      sender_type: 'agent',
      direction: 'outbound',
      status: 'sent',
      content: 'Вітаю, Ірино! Завтра є 10:00 та 11:30 у майстра Олександри. Записати вас?',
      created_at: ago(25 * 60 + 10),
    },
    {
      uuid: 'demo-msg-iryna-3',
      sender_type: 'client',
      direction: 'inbound',
      status: 'read',
      content: 'Так, записуюсь на завтра о 10:00',
      created_at: ago(25 * 60 + 2),
    },
    {
      uuid: 'demo-msg-iryna-4',
      sender_type: 'system',
      content: 'Створено запис: стрижка, завтра о 10:00',
      created_at: ago(25 * 60 + 1),
    },
  ],
};

const lastAt = (id: string): string => {
  const list = mockMessages[id]!;
  return list[list.length - 1]!.created_at;
};

export const mockDialogues: Dialogue[] = [
  {
    uuid: OLENA,
    status: 'in_progress',
    channel: 'instagram',
    client: { uuid: 'demo-cl-olena', name: 'Олена К.', instagram_handle: 'olena.k', phone: null },
    tags: ['манікюр'],
    last_message_at: lastAt(OLENA),
    preview: 'Дякую! Підкажіть, чи є вільний час на четвер після 17:00?',
    unread_count: 1,
    ai_active: false,
  },
  {
    uuid: MARIA,
    status: 'new',
    channel: 'facebook',
    client: { uuid: 'demo-cl-maria', name: 'Марія П.', instagram_handle: null, phone: null },
    tags: ['педикюр'],
    last_message_at: lastAt(MARIA),
    preview: 'Доброго дня, скільки коштує педикюр?',
    unread_count: 1,
    ai_active: true,
    webhook_status: 'expired', // демо банера «токен прострочений»
  },
  {
    uuid: IRYNA,
    status: 'ordered',
    channel: 'instagram',
    client: { uuid: 'demo-cl-iryna', name: 'Ірина Т.', instagram_handle: 'iryna.t', phone: null },
    tags: ['стрижка'],
    last_message_at: lastAt(IRYNA),
    preview: 'Так, записуюсь на завтра о 10:00',
    unread_count: 0,
    ai_active: true,
  },
];
