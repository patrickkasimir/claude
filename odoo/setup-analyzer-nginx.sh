#!/usr/bin/env bash
#
# Macht die Analyzer-Web-App unter /analyzer/ erreichbar (nginx + Basic-Auth).
# Voraussetzung: App läuft via pm2 (odoo-analyzer) auf 127.0.0.1:3010 und das
# Login /etc/nginx/.htpasswd-odoo existiert (vom Report-Setup).
#
# Aufruf:  sudo bash odoo/setup-analyzer-nginx.sh
#
set -euo pipefail
NGINX=/etc/nginx/sites-available/codetalk

[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo starten:  sudo bash $0"; exit 1; }

if grep -q "location /analyzer/" "$NGINX"; then
  echo "Block existiert bereits – übersprungen."
else
  BACKUP="$NGINX.bak.$(date +%s)"
  cp "$NGINX" "$BACKUP"
  echo "Backup: $BACKUP"
  python3 - "$NGINX" <<'PY'
import sys
path = sys.argv[1]
block = '''    location /analyzer/ {
        proxy_pass http://127.0.0.1:3010/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        auth_basic "Odoo-Analyzer - Login";
        auth_basic_user_file /etc/nginx/.htpasswd-odoo;
        add_header X-Robots-Tag "noindex, nofollow" always;
    }

'''
s = open(path).read()
marker = "location /claudeapps/ {"
i = s.find(marker)
if i == -1:
    sys.exit("Marker 'location /claudeapps/ {' nicht gefunden - Abbruch.")
ls = s.rfind("\n", 0, i) + 1
open(path, "w").write(s[:ls] + block + s[ls:])
print("Block eingefügt.")
PY
fi

if nginx -t; then
  systemctl reload nginx
  echo "FERTIG ✓  ->  https://backend.kasimir.info/analyzer/  (Login: odoo)"
else
  echo "FEHLER in der Config! Spiele Backup zurück (es wird nichts geändert)."
  cp "$(ls -t "$NGINX".bak.* | head -1)" "$NGINX"
  exit 1
fi
