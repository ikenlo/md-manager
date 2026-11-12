# MDs Manager Phase 1.5 — Design Rewrite Summary

Гілка: `claude/mdsmanager-phase1` · 12.11.2026 · основа — аудит [CONNECT_DESIGN_AUDIT.md](CONNECT_DESIGN_AUDIT.md)

## What was done

- **Design tokens from Connect** — 25 кольорів, 2 шрифти (Manrope 400–700, Cormorant Garamond 400/600/700),
  радіуси, тіні, тривалості анімацій — у `frontend/tailwind.config.js`. Шрифти локальні (`public/fonts/*.woff2`,
  кирилиця + латиниця, ліцензії OFL поруч), Google Fonts більше не використовується.
- **UI components (11)** у `frontend/src/components/ui/`: Button, Input, Field, Chip, Badge, Avatar, Sheet, Toast
  (+ стор `src/store/toast.ts` і хелпер `toast.success/error/warning/info`), Table, Skeleton, Divider.
  Вітрина — `/_demo` (лише `npm run dev`, у production-збірку не потрапляє).
- **Auth rewrite**:
  - вхід «Логін або Email» (`admin` → `admin@mds.local`), помилки 401/429 з відліком;
  - 401 на будь-якому запиті → `/login` + тост; перевірка сесії через `/api/auth/me` при старті;
  - автовихід після 30 хв без дій (спільний для всіх вкладок; `VITE_IDLE_MINUTES`);
  - тихе оновлення токена за 5 хв до кінця (`POST /api/auth/refresh`, новий ендпоінт бекенда) з блокуванням
    між вкладками і синхронізацією через `storage`-подію;
  - кнопка виходу (бокова панель; на телефоні — у шапці списку).
- **Inbox rewrite**: 3 колонки (панель · список 380 px · чат), < 900 px — або список, або чат з «Назад»;
  фільтри (Всі / Нові / В роботі / Записані / Непрочитані), пошук; іконки статусів
  (queued / sent / delivered / read / failed); вкладення (мініатюри й файли); банери «токен прострочений»
  і «вікно 24 год минуло»; швидкі відповіді; перемикач «AI веде / Веде людина»;
  WebSocket-заглушка `src/lib/ws.ts`, підключена в `InboxPage`.
- **Removed**: старі `components/Avatar.tsx`, `ChatView.tsx`, `StatusTag.tsx`, експорт `useAuth`,
  ключі `localStorage` `mds.token` / `mds.user`.
- **Fixed during the rewrite**: `.gitignore` відсікав `frontend/src/data/` (збірка не проходила);
  бейдж непрочитаних у боковій панелі був записаний числом «4» — тепер рахується зі стору.

## What was preserved

- Mock data (3 діалоги, 12 повідомлень у `src/data/mock.ts`) — до появи реальних даних у Фазі 2.
- Backend — без змін, крім одного нового ендпоінта `POST /api/auth/refresh` (окремий коміт, з тестами).
- All 38 backend tests pass (`python -m pytest -q`), `ruff check` чистий.
- Frontend: `npm run build` і `npm run typecheck` без помилок.

## What's next (Phase 2)

- Connect v0.3.1: webhook queue in Connect repo
- Sync job: Manager pulls webhooks from Connect
- Real Meta API integration (адаптера Meta в бекенді Manager ще немає — його треба створити)
- WebSocket real connection (`src/lib/ws.ts` already stubbed; стор уже має `appendIncomingMessage`,
  `upsertDialogue`, `setMessageStatus`)
- Реальна відправка: статус `queued` → `sent/delivered/read/failed` від черги вихідних

> Нагадування з канону Connect (`docs/CANON.md`, D-5): Manager читає Connect лише через `/api/ext/v1`,
> записів у Connect немає. Черга вебхуків у Connect має це враховувати.

## How to run

Backend (перший раз — `.env` з `.env.example`, `alembic upgrade head`, `python -m app.seed`):

```bash
cd MDsManager/backend && uvicorn app.main:app --reload
```

Frontend (dev, `/api` проксі на :8000):

```bash
cd MDsManager/frontend && npm run dev        # http://localhost:5173, UI kit — /_demo
```

Production: `npm run build && npm run preview` для локальної перевірки; на сервері зібраний
`frontend/dist` віддає сам FastAPI (той самий домен, тому `VITE_API_URL` лишається порожнім).

## Known limitations (to fix in Phase 2)

- Demo data loads in production (until real data from API).
- Buttons «Записати», «Картка клієнта», «Позначити», «Перепідключити» show a «Фаза 2» toast.
- Green squares in attachments (test 1×1 px image).
- Таблиця на телефоні гортається вбік — перетворення на картки (як у Connect, ≤ 640 px) ще не зроблено.
- Темної теми Connect немає: кольори в Tailwind задані сталими значеннями, а не CSS-змінними.
- Відлік на 429 завжди починається з 15:00 — бекенд у `Retry-After` віддає довжину вікна, а не залишок.
- У `package.json` немає скрипта `lint` (ESLint не налаштовано); типи перевіряє `npm run typecheck`.
- Інші пункти бокової панелі (Записи, Клієнти…) ще не ведуть на сторінки.

## Screenshots

`docs/screenshots/`: `login-final.png`, `inbox-final-desktop.png`, `inbox-final-mobile-list.png`,
`inbox-final-mobile-chat.png`, `ui-kit-final.png` (+ проміжні `inbox-*.png`, `ui-kit-*.png`).
