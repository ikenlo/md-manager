# MDs Manager — Фаза 1

Локальний AI-асистент і омніканальний диспетчер салону M&D (Windows, `D:/MDsManager/`).

**Фаза 1:** ядро бекенду (БД, вхід, налаштування, діалоги) + оболонка інтерфейсу з демо-даними.
Реальних інтеграцій Instagram/Facebook/Telegram і AI-агентів ще немає.

![Діалоги](docs/inbox.png)

## Стек

| Частина | Технології |
|---|---|
| backend | Python 3.12, FastAPI, SQLAlchemy 2 (`Mapped[T]`), Alembic, SQLite (WAL), Fernet, bcrypt |
| frontend | React 18 + Vite + TypeScript, Tailwind CSS 3, Zustand, React Router, axios, lucide-react |

## Запуск (Windows, PowerShell)

### Backend

```powershell
cd D:/MDsManager/backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
copy .env.example .env      # вставте ключ у ENCRYPTION_KEY=
alembic upgrade head
python -m app.seed          # admin@mds.local / admin   (+ --demo — 3 демо-діалоги в БД)
uvicorn app.main:app --reload
```

API: http://localhost:8000, документація: http://localhost:8000/docs.

> Не втрачайте `ENCRYPTION_KEY`: без нього секрети в `settings` і токени каналів не розшифрувати.

### Frontend

```powershell
cd D:/MDsManager/frontend
npm install
npm run dev
```

Відкрити http://localhost:5173 → вхід `admin@mds.local` / `admin`.
Vite проксіює `/api` на `localhost:8000`. Якщо бекенд не запущено, ці ж облікові дані відкривають
демо-режим (позначка внизу праворуч). Список і чат у Фазі 1 — демо-дані з `src/data/mock.ts`.

## Перевірки

```powershell
cd backend;  pytest;  ruff check .;  ruff format --check .
cd frontend; npm run build
```

## Структура

```
backend/
  app/main.py, config.py, database.py   # FastAPI, pydantic-settings, PRAGMA WAL/foreign_keys/busy_timeout
  app/models/                           # 10 таблиць: users, sessions, settings, channels, agents,
                                        #   dialogues, messages, dialog_tags, crm_clients, client_links
  app/schemas/  app/api/routes/  app/services/ (crypto, auth, dialogues, settings_store)
  alembic/versions/0001_initial.py
  seed.py → app/seed.py
  tests/                                # pytest: auth, шифрування, налаштування, діалоги
frontend/src/
  components/ pages/ api/ store/ types/ data/mock.ts lib/format.ts
data/                                   # SQLite (mds.db)
```

## API

| Метод | Шлях | Опис |
|---|---|---|
| POST | `/api/auth/login` | `{email, password}` → `{token, expires_at, user}` |
| GET | `/api/auth/me` | поточний користувач |
| POST | `/api/auth/logout` | завершити сесію |
| GET | `/api/dialogues` | фільтри: `status`, `channel`, `tag`, `q`, `limit`, `offset` |
| GET | `/api/dialogues/{uuid}/messages` | `limit`, `before_id` |
| POST | `/api/dialogues/{uuid}/messages` | `{content}` — відповідь адміністратора (`sender_type=human`) |
| POST | `/api/settings` | `{key, value, is_secret}` — значення шифрується Fernet |
| GET | `/api/settings` | список; секрети повертаються як `null` |

Авторизація: `Authorization: Bearer <token>`. Токен — `secrets.token_urlsafe(48)`, у БД лише SHA-256,
TTL 7 днів. Паролі — bcrypt. Усі часи в БД — UTC (naive datetime на вході → помилка).
