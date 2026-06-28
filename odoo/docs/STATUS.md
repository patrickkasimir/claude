# Odoo-Analyzer – Projektstatus & Handover

> **Zweck:** Dieses Dokument fasst den kompletten Stand zusammen, damit auf einem
> anderen Rechner / in einer neuen Session nahtlos weitergearbeitet werden kann.
> Stand: 2026-06-28. Branch: `odoo-remote-customizing`.

## TL;DR
Wir bauen einen **Odoo-Analyzer**: liest per XML-RPC eine beliebige Odoo-Instanz aus
(nur Metadaten/Zähler), erzeugt 5 Report-Seiten (Überblick · Technik · Prozesse ·
Sicherheit · Advisor mit Health-Score) und stellt das Ganze als **Multi-User-SaaS-Web-App**
bereit (Registrierung, 2FA, Mandanten-Trennung, Instanzen erfassen → Analyse → Report).
Alles mit **Python-Standardbibliothek + jinja2** (auf dem Server ist **kein pip** verfügbar).

## 1. Repository
- Remote: `git@github.com:patrickkasimir/claude.git` (SSH, token-frei).
- **Branch: `odoo-remote-customizing`** (das gesamte Odoo-Projekt liegt unter `odoo/`).
- `main` enthält die „claudeapps" (Spiele, Landing-Page) – nicht dieses Projekt.
- Wiedereinstieg auf neuem Rechner: clone → `git checkout odoo-remote-customizing` →
  `odoo/.env` aus `odoo/.env.example` neu anlegen (Instanz-Zugang + API-Key, s. u.).

## 2. Komponenten (alle unter `odoo/`)
**Extraktoren (portabel, nur API, Output nach `ODOO_OUT_DIR` bzw. `odoo/report/`, gitignored):**
- `connect.py` – Verbindungstest
- `analyze.py` – Überblick (Version, Module, Modelle, Apps, Geschäftsdaten)
- `extract_processes.py` – Prozesse (Pipelines/Stadien, Belegstatus, Automatisierungen, Mails, Config)
- `extract_technical.py` – Customizing (Custom-Modelle/-Felder, Studio, Server-Aktionen, Datensatzregeln, Sequenzen)
- `extract_security.py` – Benutzer/Gruppen/Rechte (Gruppen mit App-Bezug via `res.groups.privilege`)
- `extract_modules.py` – App-Abhängigkeitsgraph (transitive Reduktion)
- `advisor.py` – liest die JSONs der anderen → Regelkatalog + gewichteter Health-Score
- `create_org_roles.py` – legt Organisationsrollen-Gruppen in der Instanz an (Vertriebsmitarbeiter/Projektleiter/HR)

**Report-Seiten (`odoo/report/*.html`):** statisches HTML+JS, rendern **clientseitig** aus
den erzeugten `*.js` (`window.ODOO_*`). 5 Reiter, gegenseitig verlinkt.

**Web-App (`odoo/webapp/app.py`):** stdlib http.server + jinja2 + sqlite3.
- Registrierung/Login/Logout (scrypt), **E-Mail-Verifizierung**, **Passwort-Reset**,
  Konto (PW ändern), **TOTP-2FA** (opt-in), Mandanten-Trennung (`instances.user_id`).
- **API-Key wird NIE gespeichert** (Eingabe pro Analyse, transient). DB nur Stammdaten.
- Sicherheit: Rate-Limit, Session-Ablauf (14 T), Secure/HttpOnly/SameSite-Cookie, Fehlerseiten.
- Landing-Page, Impressum, Datenschutz (Templates mit Platzhaltern).
- Datenfluss-Schaubild (SVG) im Dashboard.
- DB/Daten: `odoo/webapp/data/` (gitignored: `app.db`, `instances/`, `mail_outbox/`, `backups/`).

## 3. Betrieb (auf dem Server backend.kasimir.info / Ionos, EU)
- **Web-App:** pm2-Prozess **`odoo-analyzer`**, `127.0.0.1:3010`, env **`BASE_PATH=/analyzer`**
  (für ausgehende Links unter dem nginx-Unterpfad). `pm2 restart odoo-analyzer` nach Codeänderung.
- **nginx:** `/etc/nginx/sites-available/codetalk`, `server_name backend.kasimir.info`.
  - `/analyzer/` → proxy 3010, Basic-Auth (`/etc/nginx/.htpasswd-odoo`, User `odoo`).
  - `/claudeapps/odoo-analyse/` → statischer Report (Single-Instanz), Basic-Auth.
  - Catch-all `location / → 127.0.0.1:3000` (Node „codetalk") – daher kommt „Cannot GET" bei falschem Pfad.
- **URLs (mit Login):** App `https://backend.kasimir.info/analyzer/` ·
  Report `https://backend.kasimir.info/claudeapps/odoo-analyse/`

## 4. Wichtige Befehle
```bash
# Einzel-Instanz-Analyse + Deploy des statischen Reports:
bash odoo/update.sh                       # alle Extraktoren + advisor + Deploy

# Web-App lokal starten (Dev, ohne nginx -> BASE_PATH leer lassen):
python3 odoo/webapp/app.py                # http://127.0.0.1:3010

# Einmalige Server-Einrichtung (sudo):
sudo bash odoo/setup-webserver.sh         # Report unter /claudeapps/odoo-analyse/ (Basic-Auth, fragt PW)
sudo bash odoo/setup-analyzer-nginx.sh    # App unter /analyzer/ (Basic-Auth)
sudo bash odoo/setup-analyzer-public.sh   # GO-LIVE: Basic-Auth entfernen (öffentliche Registrierung)

bash odoo/webapp/backup.sh                # DB-Backup (cron-fähig)
```

## 5. Zugangsdaten / Secrets (NICHT im Git)
- **Odoo-Test-Instanz:** `https://viaalia-test-saas19-0623.odoo.com` (saas~19.2 Enterprise).
  DB = `viaalia-test-saas19-0623` (= Subdomain). Login `patrick.kasimir@viaalia.de`.
  **API-Key liegt in `odoo/.env`** (gitignored; Vorlage: `odoo/.env.example`).
- App-Login (nginx Basic-Auth): User `odoo`, Passwort wurde beim Setup gesetzt.
- Auf neuem Rechner: `odoo/.env` neu anlegen, App-Daten (`odoo/webapp/data/`) starten frisch.

## 6. Funktionsumfang – ERLEDIGT
Analyse (5 Reiter), Health-Score + Regelkatalog, Gruppen-Baum (App-Bezug, klickbar,
Richtung umschaltbar, OOTB/Custom), App-Abhängigkeitsgraph, Pro-Bereich-Narrativ,
Organisationsrollen in der Instanz angelegt. SaaS: Registrierung, Login, **2FA (TOTP)**,
E-Mail-Verifizierung, Passwort-Reset, Konto, Instanz add/edit/delete/analyze, Mandanten-
Trennung, Rate-Limit, Datenminimierung, **kein Key-Storage**, Pflichtseiten, Datenfluss-Bild,
Backup-/Go-live-Skripte, AVV-Vorlage, BASE_PATH-Fix für Unterpfad.

## 7. OFFEN / nächste Schritte
- **SMTP einrichten** (aktuell KEINER konfiguriert → Mails landen nur in `data/mail_outbox/`).
  App liest `SMTP_HOST/PORT/USER/PASS/FROM`. Geplant: kleiner `.env`-Loader in `odoo/webapp/`,
  Werte (z. B. Ionos: `smtp.ionos.de:587`) trägt der Nutzer in gitignorierte Datei ein.
- **TOTP-Secrets verschlüsseln** (liegen aktuell im Klartext in der DB; Fernet wurde entfernt).
- **2FA-Recovery-Codes** (sonst Lockout bei verlorenem Authenticator).
- **Echte Rechtsinhalte** in Impressum/Datenschutz/AVV + juristische Prüfung.
- **Go-live**: `setup-analyzer-public.sh` (Basic-Auth weg → öffentliche Registrierung).
- Optional: Konto-Mgmt-Komfort, Analyse-Verlauf, eigene Domain.

## 8. Stolpersteine / Lessons Learned
- **Kein pip auf dem Server** → nur Standardbibliothek (jinja2 ist als System-Paket da).
- **Odoo 19.2 Gruppenmodell:** `res.groups` nutzt `user_ids`/`all_user_ids` + `privilege_id`
  (→ `res.groups.privilege.category_id` = App), NICHT mehr `users`/`category_id`.
- **XML-RPC:** Optionen (`fields`/`order`/`attributes`) immer als kwargs, nie positional.
  Vor neuen Modellen Felder per `fields_get` prüfen.
- **Report-JS:** Init/Render erst NACH allen const/function-Definitionen aufrufen (sonst TDZ → leere Seite).
- **nginx-Unterpfad:** App muss `BASE_PATH` kennen (ausgehende Links/Redirects), sonst „Cannot GET".
- **Datenminimierung:** keine Namen/E-Mails (privilegierte User nur als Anzahl, `server.user` = `uid N`).

## 9. Datenschutz/DSGVO (Kurz)
Bei Analyse fremder Instanzen ist der Kunde Verantwortlicher, wir Auftragsverarbeiter (Art. 28 →
AVV nötig). Umgesetzt: Key wird nicht gespeichert, Datenminimierung, TLS, EU-Hosting, Löschfunktion.
Vor echtem Kundenbetrieb: AVV/Datenschutzerklärung/Verarbeitungsverzeichnis + juristische Prüfung.
Empfehlung an Kunden: dedizierter API-User (`odoo/docs/readonly-api-user.md`).

---
*Letzte relevante Commits siehe `git log --oneline`. Dieses Dokument bei größeren Änderungen aktualisieren.*
