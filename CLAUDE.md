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
- Інтеграція з MDS Connect (`ikenlo/m-d`) — docs/integration/README.md. Якщо задано MDS_URL/MDS_TOKEN,
  записи живуть у MDS: інструменти агента — app/agent/mds_tools.py, клієнт — app/integrations/mds.py.
  MDS працює в naive-часі Києва й копійках; конвертація — лише в MdsClient.
- Мітки джерел: conversation.lead_source (з /start <мітка> або Instagram referral) → атрибуція запису;
  звіт /sources — app/marketing.py.
- AI для контенту — app/ai/: router.py (Gemini для масових текстів/картинок, Claude — аналіз),
  gemini.py (REST), prices.py, budget.py (місячний ліміт). Кожен платний виклик → ai_usage з cost_usd.
- Аналітика — app/analytics/: meta.py (Graph API: IG, сторінка FB, пости → metric_daily, post_stats, ad_daily;
  щодня о 06:30 Київ), google_ads.py (кампанії → ad_daily platform=google, о 06:40), daily.py (вчора vs
  середнє 7 днів), dashboard.py (оголошення ↔ записи через мітки ig_ad_<id> / gads_<campaign_id>).
- AI-аналітик — app/ai/analyst.py: Claude (ANALYST_MODEL) зі structured outputs → ai_report
  (daily о 07:05). У промпт — лише агрегати, ніколи імена/телефони клієнтів. Спільний виклик —
  app/ai/claude_json.py, фонові задачі з сайту — app/ai/jobs.py.
- Контент-план — app/content/: schedule.py (слоти: пост щотижня, сторіс раз на 2 дні — рахує код),
  studio.py (ідеї, підтвердити/відхилити: 3-тє відхилення → нова тема; фото салону → Gemini трохи
  підправляє, результат послуги не змінюється), storage.py (фото без EXIF). Відео не робимо.
- Веб-застосунок MDS Manager — app/web/: static/ (SPA на дизайні MDS Connect: style.css і шрифти
  скопійовані з ikenlo/m-d, app.js — VIEWS/NAV, DOM лише через h()), api.py (/api/*), session.py
  (вхід логіном MDS Connect; director → owner, admin → admin без грошей/реклами; майстрам — ні).
- app/core/: audit.py (журнал дій — кожна дія людини чи AI), approvals.py (черга погоджень:
  публікація, розсилка, реклама — лише після «Підтвердити»).
- Роадмап і що вирізано з MyChatBot — docs/PLATFORM_PLAN.md. Стара /panel → редирект на /.

## Команди
- docker compose up -d — запуск
- pytest — тести
- ruff check . && ruff format . — лінт
- alembic upgrade head — застосувати міграції
- alembic revision --autogenerate -m "..." — міграція
- python seed.py — заповнити послуги, майстрів, графік із seed.yaml
