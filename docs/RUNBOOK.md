# RUNBOOK — MDs manager на VPS

Усі команди — з каталогу проєкту на сервері (напр. `/opt/mds-manager`), від root або sudo.

## Перше розгортання

1. **Сервер**: Ubuntu 24.04, 1–2 vCPU, 2 GB RAM. SSH лише за ключем:
   `PasswordAuthentication no` у `/etc/ssh/sshd_config`, потім `systemctl restart ssh`.
2. **Фаєрвол**: `ufw allow 22,80,443/tcp && ufw enable`.
3. **DNS**: A-запис `bot.<ваш-домен>` → IP сервера (до старту Caddy, інакше не буде сертифіката).
4. **Docker**: `curl -fsSL https://get.docker.com | sh`.
5. **Код** (репозиторій приватний — deploy key або токен):
   ```bash
   git clone git@github.com:ikenlo/md-managment.git /opt/mds-manager && cd /opt/mds-manager
   cp .env.example .env && nano .env      # усі ключі, DOMAIN, ADMIN_IDS, TG_WEBHOOK_SECRET
   chmod 600 .env
   mkdir -p data backups && chown -R 1000:1000 data backups   # контейнер працює від uid 1000
   ```
   `TG_WEBHOOK_SECRET`: `openssl rand -hex 32`.
6. **Дані салону**: відредагуйте `seed.yaml` (послуги, ціни, майстри, графік), потім:
   ```bash
   docker compose up -d --build
   docker compose exec app python seed.py
   ```
7. **Перевірка**: `curl https://bot.<домен>/health` → `{"status":"ok"}`.
8. **Telegram**: вебхук ставиться автоматично на старті. Перевірка:
   `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"` — url має бути `https://bot.<домен>/webhook/telegram`.
   Бот має бути адміністратором адмін-групи; ID групи (від’ємне число) → `TG_ADMIN_CHAT_ID`.
9. **Instagram** (Meta App Dashboard → Instagram → Webhooks):
   callback `https://bot.<домен>/webhook/instagram`, verify token = `IG_VERIFY_TOKEN`,
   підписка на поле `messages`. Поки апка в режимі розробки — бот бачить лише тестерів.

## Оновлення

```bash
cd /opt/mds-manager
./scripts/backup.sh                       # завжди бекап перед оновленням
git fetch && git log --oneline HEAD..origin/main   # що приїде
git tag -f prev HEAD                      # точка для відкату
git pull
docker compose up -d --build              # міграції Alembic застосовуються на старті
docker compose logs -f app --since 2m     # перевірити, що піднялось
```
Після оновлення: `/health`, написати боту в Telegram, `/today` в адмін-групі.

## Відкат

Код без змін схеми БД:
```bash
git checkout prev && docker compose up -d --build
```
Якщо оновлення змінювало схему (нова міграція в `alembic/versions/`):
```bash
docker compose exec app alembic downgrade -1   # ДО повернення старого коду
git checkout prev && docker compose up -d --build
```
Якщо дані пошкоджені — відновлення з бекапу (нижче).

## Логи

```bash
docker compose logs -f app                # потік
docker compose logs app --since 1h | grep -E "ERROR|WARNING"
docker compose logs caddy --since 1h      # HTTPS, сертифікати
docker compose ps                         # стан і healthcheck
```
Логи не містять телефонів і текстів повідомлень — лише ID діалогів і записів.
Ротація: 5 файлів по 10 МБ (див. `docker-compose.yml`).

Що шукати:
- `agent timeout` / `agent api error` — Claude не відповів; діалог автоматично передано адміну.
- `instagram send failed: 400` — закрите 24-год вікно або прострочений токен.
- `instagram token refresh failed` — згенеруйте новий токен у Meta App Dashboard, впишіть у `.env`
  (`IG_ACCESS_TOKEN`), видаліть збережений у БД і перезапустіть:
  ```bash
  docker compose exec app python -c "import sqlite3; c = sqlite3.connect('/data/mds.db'); \
    c.execute(\"DELETE FROM salon_settings WHERE key IN ('ig_access_token', 'ig_token_refreshed_at')\"); c.commit()"
  docker compose restart app
  ```

## Бекапи

Щоденно о 03:30 (Київ) через cron на хості:
```bash
apt install -y gnupg rclone
rclone config                             # remote «gdrive» → ваш Google Drive
openssl rand -base64 32 > /root/.mds-backup-pass && chmod 600 /root/.mds-backup-pass
# пароль збережіть ще й у менеджері паролів — без нього бекап не розшифрувати
crontab -e
# 30 1 * * * cd /opt/mds-manager && ./scripts/backup.sh >> /var/log/mds-backup.log 2>&1
```
(01:30 UTC = 03:30 за Києвом узимку, 04:30 влітку.) Зберігається 14 днів — локально в `backups/` і в `gdrive:mds-backups`.

Перевірка бекапу (раз на місяць): `./scripts/backup.sh`, потім `rclone ls gdrive:mds-backups`.

**Відновлення:**
```bash
rclone copy gdrive:mds-backups/mds-2026-11-05_0130.db.gz.gpg backups/
./scripts/restore.sh backups/mds-2026-11-05_0130.db.gz.gpg
```
Скрипт зупиняє застосунок, зберігає поточну БД поруч (`data/mds.db.before-restore.*`) і запускає знову.

## Аварійні дії

- **AI каже дурниці** — `/pause_all` в адмін-групі (усі повідомлення йдуть адмінам), `/resume_all` назад.
- **Перехопити діалог** — кнопка «Перехопити» або `/takeover <id>`, відповідати `/reply <id> текст`.
- **Видалити клієнта на прохання** — `/forget <телефон>`.
- **Модель плутається** — `AI_MODEL=claude-sonnet-5-5` у `.env`, `docker compose up -d` (дорожче ~20×).

## Розробка

```bash
pip install -e '.[dev]' && pre-commit install   # ruff + pytest перед кожним комітом
pytest && ruff check .
```
