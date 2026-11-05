#!/usr/bin/env bash
# Відновлення з бекапу: ./scripts/restore.sh backups/mds-2026-11-05_0317.db.gz.gpg
# (або спершу: rclone copy gdrive:mds-backups/<файл> backups/)
set -euo pipefail

cd "$(dirname "$0")/.."
FILE="$1"
PASS_FILE="${BACKUP_PASS_FILE:-/root/.mds-backup-pass}"

docker compose stop app
cp data/mds.db "data/mds.db.before-restore.$(date -u +%s)" 2>/dev/null || true
rm -f data/mds.db-wal data/mds.db-shm
gpg --batch --decrypt --passphrase-file "$PASS_FILE" "$FILE" | gunzip > data/mds.db
docker compose start app
echo "restored from $FILE"
