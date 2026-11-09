#!/usr/bin/env bash
# Ripristino da backup. ATTENZIONE: sostituisce i dati attuali. Uso: scripts/restore.sh backups/srm-XXXX.sql.gz
set -euo pipefail
cd "$(dirname "$0")/.."
f="${1:?indica il file di backup}"; [ -f "$f" ] || { echo "File non trovato: $f" >&2; exit 1; }
read -r -p "Sovrascrivo il database attuale con $f. Continuare? [s/N] " a; [ "$a" = s ] || exit 1
docker compose stop api worker web
docker compose exec -T db psql -U srm -d postgres -c "DROP DATABASE IF EXISTS srm WITH (FORCE)" -c "CREATE DATABASE srm OWNER srm"
gunzip -c "$f" | docker compose exec -T db psql -U srm -d srm -v ON_ERROR_STOP=1 -q
docker compose start api worker web
echo "Ripristino completato."
