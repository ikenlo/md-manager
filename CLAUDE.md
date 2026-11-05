# MDs manager
AI-адміністратор салону M&D: Instagram Direct + Telegram, запис, нагадування.
Повна специфікація: docs/SPEC.md — читай перед будь-якою задачею.

## Правила
- Python 3.12, FastAPI, aiogram 3, SQLAlchemy 2, APScheduler, anthropic SDK.
- Усі часи в БД — UTC; показ клієнту — Europe/Kyiv через zoneinfo.
- Слоти рахує лише app/booking/slots.py; AI ніколи не вигадує час.
- Будь-яка зміна слотів/записів = тест у tests/.
- Секрети лише через config.py; ніколи не логувати телефони й тексти.
- Тексти для клієнтів — українською.
- Перед комітом: pytest і ruff.

## Як влаштовано ядро
- app/booking/slots.py — чистий алгоритм (без БД, `now` передається параметром).
- app/booking/service.py — операції з БД: find_free_slots, create_booking,
  reschedule_booking, set_status. Запис і перевірка слоту — в одній транзакції
  `write_transaction()` (SQLite: BEGIN IMMEDIATE).
- app/db/types.py — UTCDateTime: naive datetime на вході → помилка.

- app/dialog.py — вхідне повідомлення будь-якого каналу → пауза/handoff/агент.
- app/agent/ — runner.py (цикл Claude + tool use), tools.py (7 інструментів), usage.py.
- app/channels/ — telegram.py (aiogram; хендлери через registry.py), instagram.py.
- app/admin/ — commands.py (хендлери), queries.py (логіка, тестується окремо).
- app/reminders.py + app/scheduler.py — нагадування, автоповернення AI, токен IG, чистка.
- Тести Telegram — через справжній Dispatcher (tests/tg_harness.py), агента — FakeClaude.
- Деплой і експлуатація — docs/RUNBOOK.md.

## Команди
- docker compose up -d — запуск
- pytest — тести
- ruff check . && ruff format . — лінт
- alembic upgrade head — застосувати міграції
- alembic revision --autogenerate -m "..." — міграція
- python seed.py — заповнити послуги, майстрів, графік із seed.yaml
