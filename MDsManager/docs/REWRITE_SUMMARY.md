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

## Phase 2 (COMPLETE)

- **Real outbound worker (30s, retry, backoff)** — `outbound_queue` → `MetaAdapter` (поки `MockMetaAdapter`)
  → статус повідомлення `queued → sent | failed`; повтори через 60 с × спробу, максимум 5; APScheduler у lifespan.
- **DB schema 0002** — Meta-ідентифікатори клієнтів і каналів, `unread_count`, `last_inbound_at/last_outbound_at`,
  статуси й напрям повідомлень, вкладення (JSON), таблиці `outbound_queue` і `media_assets`.
  Міграції SQLite безпечні для даних: FK вимикаються на час міграції, після — `foreign_key_check`.
- **WebSocket real-time updates** — `WS /api/ws?token=…`, менеджер з'єднань, сервер шле ping і закриває сокет,
  коли сесія завершилась (1008).
- **All 3 events: new_message, message_status, dialogue_updated** — шина подій (`app/services/events.py`) → усі вкладки.
- **Test endpoints for simulation** — `/api/_test/simulate_inbound`, `simulate_attachment`, `trigger_outbound_failure`
  (лише `MOCK_META=true` і не production) + `GET /api/media/{uuid}`.
- **Frontend live updates (badges, statuses, new dialogues)** — інбокс читає реальні діалоги з API,
  надсилає через `POST`, оновлюється через WebSocket; перепідключення з паузою 1–30 с і дозавантаженням
  пропущеного; банер «Немає з'єднання»; тост про нове повідомлення й про невдалу відправку.
  Dev-панель (лише `npm run dev`) для симуляції.
- Тести: бекенд 71 (WS, черга, тестові ендпоінти, міграції туди й назад); наскрізний сценарій на двох вкладках
  (24 перевірки, Playwright) — нове вхідне, статуси, вкладення, збій, обрив сервера, F5, вихід.

### Обмеження після Phase 2

- «Прочитано» — лише локально у вкладці: після F5 лічильник непрочитаних повертається (mark_read — Фаза 3).
- Перемикач «AI веде / Веде людина» не зберігається на сервері.
- Mock-дані (`src/data/mock.ts`) лишились тільки для демо-входу без бекенда (dev).
- Вкладення роздаються за UUID без Bearer (`<img>` не вміє заголовки) — як посилання CDN Meta.

## Phase 3 Part 1 (COMPLETE — AI foundation)

### What was done
- OllamaAdapter interface (async chat with tools support)
- MockOllamaAdapter (delay, `__FAIL__` / `__TOOL_CALL__` markers for testing)
- RealOllamaAdapter (httpx.AsyncClient, 120s timeout, strips `<think>` tags, `health()` method)
- Factory: `get_ollama_adapter()` based on `MOCK_OLLAMA` env
- System prompt: `backend/prompts/sales_agent.md` (editable file, Ukrainian, salon tone, all services; 1591 chars)
- Loader: `services/ai_prompt.py` with `lru_cache` + `reload_sales_prompt()`
- Config: 7 `OLLAMA_*` env vars (enabled, mock, host, model, timeout, temperature, num_ctx)
- Error classes: `OllamaError`, `OllamaDisabledError`
- `httpx` moved from dev to runtime dependencies in `requirements.txt`

### Tests
- 19 tests for adapters (`tests/test_ollama_adapters.py`): mock + real with `httpx.MockTransport`; 18 run, 1 integration test skipped
- 10 new tests for prompt loader (`tests/test_ai_prompt.py`)
- Total: 99 passed, 1 skipped (integration test skipped without Ollama in container)

### Known limitations (to fix in later phases)
- `reload_sales_prompt()` exists but is not called automatically; after editing prompt, restart backend
- No `/api/admin/reload-prompt` endpoint yet (planned for Phase 3 Part 3 or later)
- Integration test with real Ollama requires running `ollama serve` + `ollama pull qwen3:14b` on PC

### What's next
- Part 2: AI Agent service (orchestrator) + tools (`get_services`, `get_slots`, `create_appointment`) + intent detection
- Part 3: Frontend (toggle AI lead/human lead, approve UI for bookings, real-time "AI typing" indicator)

## Phase 3 Part 2 (IN PROGRESS — AI agent + human-in-the-loop)

### Tools and agent
- `services/tools/`: `get_services`, `get_slots` (mock data) and `create_appointment` + registry `execute_tool`.
- `services/ai_agent.py`: tool-calling loop (max 3 iterations), intent detection
  (booking / question / escalate / unknown), `build_messages_from_dialogue`.
- Write-tools (`create_appointment`) are NOT executed by the agent: args are validated and the model gets
  `{"pending_approval": true}`; the booking is executed only after admin approval. LLM errors → `escalate`.
- Prompt: two-step approval — the model never tells the client "ви записані" before the admin approves.

### DB: ai_suggestions
- Table for pending AI suggestions awaiting admin approval.
- Fields: content (proposed text), proposed_booking (booking to execute on approve), intent, status
  (pending / approved / rejected / expired), resolved_at, resolved_by_user_id, message_id (client message).
- Cascade: deleting dialogue removes its suggestions.
- Migration 0003.

## What's next (Phase 2.5 / 3)

- Connect v0.3.1: webhook queue in Connect repo
- Sync job: Manager pulls webhooks from Connect
- Phase 2.5: реальний `MetaAdapter` (Graph API) замість `MockMetaAdapter` — інтерфейс і фабрика вже є
  (`app/services/adapters/`), вмикається `MOCK_META=false`; вхідні вебхуки Meta → ті самі події `new_message`
- Статуси `delivered/read` від Meta (зараз воркер доводить лише до `sent`/`failed`)
- Phase 3: mark_read і typing через WebSocket, AI Sales Agent

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

- ~~Demo data loads in production~~ — з Phase 2 інбокс читає реальні дані з API.
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
