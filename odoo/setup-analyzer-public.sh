#!/usr/bin/env bash
#
# GO-LIVE: entfernt die nginx-Basic-Auth aus dem /analyzer/-Block, damit sich
# Nutzer ÖFFENTLICH selbst registrieren können. Bewusste Exposition!
#
# Voraussetzung: Pflichtseiten (Impressum/Datenschutz) gefüllt & geprüft,
# E-Mail-Verifizierung aktiv (SMTP konfiguriert). Die App hat eigene
# Anmeldung/Registrierung – die Basic-Auth davor ist dann redundant.
#
# Aufruf:  sudo bash odoo/setup-analyzer-public.sh
#
set -euo pipefail
NGINX=/etc/nginx/sites-available/codetalk
[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo starten:  sudo bash $0"; exit 1; }
grep -q "location /analyzer/ {" "$NGINX" || { echo "/analyzer/-Block fehlt – zuerst setup-analyzer-nginx.sh."; exit 1; }

BACKUP="$NGINX.bak.$(date +%s)"; cp "$NGINX" "$BACKUP"; echo "Backup: $BACKUP"
python3 - "$NGINX" <<'PY'
import sys, re
p = sys.argv[1]; s = open(p).read()
i = s.find("location /analyzer/ {")
j = s.find("}", i)
block = re.sub(r'\n[ \t]*auth_basic[^\n]*', '', s[i:j])   # entfernt auth_basic + auth_basic_user_file
open(p, "w").write(s[:i] + block + s[j:])
print("Basic-Auth aus /analyzer/ entfernt.")
PY
if nginx -t; then
  systemctl reload nginx
  echo "FERTIG ✓  Öffentlich erreichbar:  https://backend.kasimir.info/analyzer/"
else
  echo "FEHLER – Backup zurück"; cp "$BACKUP" "$NGINX"; exit 1
fi
