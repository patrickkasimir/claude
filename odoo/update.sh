#!/usr/bin/env bash
#
# Ein-Klick-Gesamtlauf: alle Extraktoren ausführen und den Report deployen.
# Aufruf:  bash odoo/update.sh        (kein sudo nötig – Zielordner gehört dem User)
#
# Voraussetzung: einmalig die geschützte Bereitstellung eingerichtet via
#   sudo bash odoo/setup-webserver.sh
#
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DST=/var/www/html/claudeapps/odoo-analyse

echo "== 1/2: Daten aus Odoo extrahieren =="
for s in analyze.py extract_processes.py extract_technical.py extract_security.py extract_modules.py advisor.py; do
  echo "  → $s"
  python3 "$HERE/$s" >/dev/null || { echo "  FEHLER in $s"; exit 1; }
done
echo "  alle Extraktoren ok"

echo "== 2/2: Report deployen =="
if [ -d "$DST" ]; then
  cp "$HERE"/report/*.html "$DST/" 2>/dev/null || true
  cp "$HERE"/report/*.js   "$DST/" 2>/dev/null || true
  echo "  → nach $DST kopiert"
else
  echo "  Zielordner $DST fehlt – bitte einmalig:  sudo bash odoo/setup-webserver.sh"
  exit 1
fi

echo
echo "FERTIG ✓   https://backend.kasimir.info/claudeapps/odoo-analyse/"
