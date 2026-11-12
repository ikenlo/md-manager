#!/usr/bin/env bash
# Щоденний бекап: знімок SQLite → gzip → gpg (AES256) → rclone у віддалене сховище.
# Зберігаємо 14 днів локально і віддалено. Запуск з cron на хості (див. docs/RUNBOOK.md).
#
# Потрібно на хості: gpg, rclone (налаштований remote, напр. Google Drive),
# файл з паролем шифрування /root/.mds-backup-pass (chmod 600).
set -euo pipefail

cd "$(dirname "$0")/.."
REMOTE="${BACKUP_REMOTE:-gdrive:mds-backups}"
PASS_FILE="${BACKUP_PASS_FILE:-/root/.mds-backup-pass}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
STAMP="$(date -u +%Y-%m-%d_%H%M)"
NAME="mds-${STAMP}.db.gz"

mkdir -p backups
docker compose exec -T app python -m app.backup "/backups/${NAME}" >/dev/null
gpg --batch --yes --symmetric --cipher-algo AES256 \
    --passphrase-file "$PASS_FILE" -o "backups/${NAME}.gpg" "backups/${NAME}"
rm -f "backups/${NAME}"

rclone copy "backups/${NAME}.gpg" "$REMOTE"
find backups -name 'mds-*.db.gz.gpg' -mtime +"$KEEP_DAYS" -delete
rclone delete "$REMOTE" --min-age "${KEEP_DAYS}d" --include 'mds-*.db.gz.gpg'

echo "backup ok: ${NAME}.gpg"
