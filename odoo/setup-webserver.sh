#!/usr/bin/env bash
#
# Richtet den Odoo-Analyse-Report geschützt auf dem Webserver ein.
# Aufruf:  sudo bash setup-webserver.sh
# Fragt nur nach einem Passwort. Sichert die nginx-Config, testet sie und
# spielt bei Fehler automatisch das Backup zurück (ändert dann nichts).
#
set -euo pipefail

NGINX_CONF=/etc/nginx/sites-available/codetalk
HTPASSWD=/etc/nginx/.htpasswd-odoo
SRC=/home/elija/apps/projects_claude-odoo-remote-customizing/odoo/report
DEST=/var/www/html/claudeapps/odoo-analyse
OWNER=elija

if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte mit sudo starten:  sudo bash $0"; exit 1
fi
if [ ! -f "$SRC/index.html" ] || [ ! -f "$SRC/data.js" ]; then
  echo "FEHLER: Report-Dateien fehlen in $SRC (zuerst 'python3 odoo/analyze.py' laufen lassen)."; exit 1
fi

echo "== Schritt 1/5: Passwort festlegen (Benutzername: odoo) =="
read -s -p "   Neues Passwort: " PW1; echo
read -s -p "   Passwort wiederholen: " PW2; echo
[ -n "$PW1" ] || { echo "   Leeres Passwort - Abbruch."; exit 1; }
[ "$PW1" = "$PW2" ] || { echo "   Passwoerter stimmen nicht ueberein - Abbruch."; exit 1; }
if command -v openssl >/dev/null 2>&1; then
  HASH="$(printf '%s\n' "$PW1" | openssl passwd -apr1 -stdin)"
else
  HASH="$(printf '%s' "$PW1" | python3 -W ignore -c 'import sys,crypt; print(crypt.crypt(sys.stdin.read(), crypt.mksalt(crypt.METHOD_SHA512)))')"
fi
printf 'odoo:%s\n' "$HASH" > "$HTPASSWD"
unset PW1 PW2
chown root:www-data "$HTPASSWD"; chmod 640 "$HTPASSWD"
echo "   -> Passwort gespeichert (nur als Hash)."

echo "== Schritt 2/5: nginx-Config sichern =="
BACKUP="$NGINX_CONF.bak.$(date +%s)"
cp "$NGINX_CONF" "$BACKUP"
echo "   -> Backup: $BACKUP"

echo "== Schritt 3/5: Schutz-Regel einfügen =="
if grep -q "location /claudeapps/odoo-analyse/" "$NGINX_CONF"; then
  echo "   -> Regel bereits vorhanden, übersprungen."
else
  python3 - "$NGINX_CONF" <<'PY'
import sys
path = sys.argv[1]
block = '''    location /claudeapps/odoo-analyse/ {
        alias /var/www/html/claudeapps/odoo-analyse/;
        index index.html;
        auth_basic "Odoo-Analyse - Login";
        auth_basic_user_file /etc/nginx/.htpasswd-odoo;
        add_header X-Robots-Tag "noindex, nofollow" always;
    }

'''
s = open(path).read()
marker = "location /claudeapps/ {"
i = s.find(marker)
if i == -1:
    sys.exit("Marker 'location /claudeapps/ {' nicht gefunden - Abbruch.")
line_start = s.rfind("\n", 0, i) + 1
open(path, "w").write(s[:line_start] + block + s[line_start:])
print("   -> Regel eingefügt.")
PY
fi

echo "== Schritt 4/5: nginx prüfen und neu laden =="
if nginx -t; then
  systemctl reload nginx
  echo "   -> nginx neu geladen."
else
  echo "   -> FEHLER in der Config! Spiele Backup zurück (es wird nichts geändert)."
  cp "$BACKUP" "$NGINX_CONF"
  exit 1
fi

echo "== Schritt 5/5: Report-Dateien bereitstellen =="
mkdir -p "$DEST"
cp "$SRC"/*.html "$DEST/" 2>/dev/null || true
cp "$SRC"/*.js   "$DEST/" 2>/dev/null || true
chown -R "$OWNER":"$OWNER" "$DEST"
chmod -R a+rX "$DEST"
echo "   -> Dateien kopiert ($(ls "$SRC"/*.html "$SRC"/*.js 2>/dev/null | wc -l) Stück)."

echo
echo "FERTIG ✓"
echo "Aufrufbar (nur mit Login, Benutzer 'odoo'):"
echo "   https://backend.kasimir.info/claudeapps/odoo-analyse/"
