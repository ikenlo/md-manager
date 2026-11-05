# MDs manager ↔ MDS Connect

**MDS Connect** (`ikenlo/m-d`) — внутрішня система салону й **джерело правди** для записів, клієнтів,
графіка й грошей. **MDs manager** (цей репозиторій) — AI-адміністратор у Telegram/Instagram і
маркетинг. Коли задано `MDS_URL` і `MDS_TOKEN`, MDs manager не веде записи сам — читає й пише їх у MDS.

## Що куди йде

| Напрям | Що | Як |
|---|---|---|
| MDs manager → MDS | Запис від клієнта (AI у Telegram чи Instagram) | `POST /api/ext/v1/appointments` (антиспам, графік і захист від подвійних записів — у MDS) |
| MDs manager → MDS | Звідки прийшов клієнт: мітка посилання / оголошення | поле `attribution.lead_source` у тому ж запиті |
| MDs manager → MDS | Instagram ID клієнта, перше джерело клієнта | там само |
| MDS → MDs manager | Послуги, ціни, майстри, вільний час | `GET /catalog`, `GET /slots` |
| MDS → MDs manager | Візити, неявки, скасування, виручка за джерелами | `GET /visits` → команда `/sources` |
| MDS → MDs manager | Витрати на рекламу | `GET /ad-spend` (категорія «Реклама» у MDS) |

## Мітки джерел

- Telegram: `/link ig_reels_1201` → `https://t.me/<бот>?start=ig_reels_1201`. Хто перейде — мітка збережеться.
- Instagram: реклама з кнопкою «Написати» — мітка `ig_ad_<id оголошення>` автоматично;
  або посилання `ig.me/m/<акаунт>?ref=<мітка>`.
- Звіт: `/sources [днів]` в адмін-групі — записи, візити, неявки й виручка за мітками, витрати на рекламу.

## Налаштування

1. MDS Connect: злити гілку `feat/ext-api-md-manager` (PR, як вимагає його CLAUDE.md), задати змінну
   `MDS_INTEGRATION_TOKEN` (`openssl rand -hex 32`) на Railway.
2. MDs manager: у `.env` — `MDS_URL=https://m-d-production.up.railway.app` і `MDS_TOKEN=<той самий токен>`.
3. Перезапустити обидва.

Зміни для MDS Connect — у гілці `feat/ext-api-md-manager` і як патч `mds-connect-ext-api.patch`
(`git am mds-connect-ext-api.patch`): службовий API, міграція 0025, 10 тестів, `docs/INTEGRATION.md`.

## У режимі MDS

- Розклад, ручні записи, прайс, вихідні — у панелі MDS. Команди `/today`, `/book`, `/cancel`, `/move`,
  `/dayoff`, `/price` в адмін-групі підказують це.
- Нагадування клієнтам надсилає MDS Connect; наш планувальник їх не дублює.
- Клієнтський `/book` у нашому боті передає запис AI-помічнику в чаті.

## Відомі обмеження

- Нагадування MDS іде через **бот MDS**. Клієнт, який записався лише через наш AI-бот чи Instagram і ніколи
  не писав боту MDS, нагадування в Telegram не отримає (MDS має SMS через TurboSMS — це закриє питання).
- Перенесення = новий запис + скасування старого (не атомарно; якщо новий час зайнятий — старий лишається).
