#!/usr/bin/env bash
# Sichert die App-Datenbank (data/app.db) – per Cron z.B. täglich aufrufen.
# Aufruf:  bash odoo/webapp/backup.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/data/app.db"
DST="$HERE/data/backups"
[ -f "$SRC" ] || { echo "Keine DB gefunden ($SRC)"; exit 0; }
mkdir -p "$DST"
# konsistente Kopie auch bei laufendem Server (sqlite backup-API)
sqlite3 "$SRC" ".backup '$DST/app-$(date +%Y%m%d-%H%M%S).db'" 2>/dev/null || cp "$SRC" "$DST/app-$(date +%Y%m%d-%H%M%S).db"
# nur die letzten 14 Backups behalten
ls -1t "$DST"/app-*.db 2>/dev/null | tail -n +15 | xargs -r rm -f
echo "Backup ok -> $DST  ($(ls -1 "$DST"/app-*.db | wc -l) Stück)"
