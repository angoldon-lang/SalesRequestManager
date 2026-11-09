#!/usr/bin/env bash
# Backup del DB in ./backups/srm-AAAA-MM-GG_HHMM.sql.gz (conserva gli ultimi 14). Uso: scripts/backup.sh [giorni]
set -euo pipefail
cd "$(dirname "$0")/.."
KEEP="${1:-14}"
mkdir -p backups
f="backups/srm-$(date +%F_%H%M).sql.gz"
docker compose exec -T db pg_dump -U srm --no-owner srm | gzip > "$f"
[ -s "$f" ] || { rm -f "$f"; echo "Backup vuoto: errore" >&2; exit 1; }
find backups -name 'srm-*.sql.gz' -mtime +"$KEEP" -delete
echo "Backup creato: $f"
