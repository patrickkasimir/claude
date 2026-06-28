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
  `odoo/.env` aus `odoo/.env.example` neu anlegen (Instanz-Zugang + API-Key).
  `odoo/webapp/.env` aus `odoo/webapp/.env.example` neu anlegen (SMTP-Zugangsdaten).

## 2. Komponenten (alle unter `odoo/`)
**Extraktoren (portabel, nur API, Output nach `ODOO_OUT_DIR` bzw. `odoo/report/`, gitignored):**
- `connect.py` – Verbindungstest
- `analyze.py` – Überblick (Version, Module, Modelle, Apps, Geschäftsdaten)
- `extract_processes.py` – Prozesse (Pipelines/Stadien, Belegstatus, Automatisierungen, Mails, Config)
- `extract_technical.py` – Customizing (Custom-Modelle/-Felder, Studio, Server-Aktionen, Datensatzregeln, Sequenzen)
- `extract_security.py` – Benutzer/Gruppen/Rechte (Gruppen mit App-Bezug via `res.groups.privilege`)
  **Neu:** lädt parallel deutsche Übersetzungen (`de_DE`-Kontext) → `name_de`, `full_name_de`,
  `category_de`, `privilege_de` je Gruppe + `model_de` je Zugriffsrecht. `"languages"` im JSON.
- `extract_modules.py` – App-Abhängigkeitsgraph (transitive Reduktion)
- `advisor.py` – liest die JSONs der anderen → Regelkatalog + gewichteter Health-Score
- `create_org_roles.py` – legt Organisationsrollen-Gruppen in der Instanz an

**Report-Seiten (`odoo/report/*.html`):** statisches HTML+JS, rendern **clientseitig** aus
den erzeugten `*.js` (`window.ODOO_*`). 5 Reiter, gegenseitig verlinkt.
- `sicherheit.html`: **DE/EN-Toggle** (oben rechts im Header) – schaltet Gruppen-Baum,
  App-Detailseite und Modellnamen zwischen Deutsch und Englisch um. Nur sichtbar wenn
  `de_DE` in der Odoo-Instanz installiert ist.

**Web-App (`odoo/webapp/app.py`):** stdlib http.server + jinja2 + sqlite3.
- Registrierung/Login/Logout (scrypt), E-Mail-Verifizierung, Passwort-Reset,
  Konto (PW ändern), **TOTP-2FA** (opt-in, PBKDF2+XOR+HMAC verschlüsselt im DB),
  **Recovery Codes** (8×, SHA-256 gehashed, einmalig verwendbar), Mandanten-Trennung.
- **Rollen:** `admin` (alle Instanzen sehen, Benutzerverwaltung) / `user` (nur eigene).
  Ältester Nutzer (`patrick@kasimir.info`) ist automatisch Admin.
- **Verbindungstest:** vor jeder Analyse Button „Verbindung testen" → 3-stufiger XML-RPC-Test.
- **API-Key wird NIE gespeichert** (Eingabe pro Analyse, transient). DB nur Stammdaten.
- Sicherheit: Rate-Limit, Session-Ablauf (14 T), Secure/HttpOnly/SameSite-Cookie.
- Impressum/Datenschutz: **ViaAlia GmbH**, Tulpenstr. 1, 85053 Ingolstadt,
  Barbara + Patrick Kasimir, 016096498283, info@viaalia.de.
- **SMTP:** läuft über Ionos `apppp@kasimir.info`, Kreds in `odoo/webapp/.env` (gitignored).
- DB/Daten: `odoo/webapp/data/` (gitignored: `app.db`, `instances/`, `mail_outbox/`, `backups/`).

## 3. Betrieb (auf dem Server backend.kasimir.info / Ionos, EU)
- **Web-App:** pm2-Prozess **`odoo-analyzer`**, `127.0.0.1:3010`, env **`BASE_PATH=/analyzer`**.
  `pm2 restart odoo-analyzer` nach Codeänderungen in `odoo/webapp/app.py`.
- **nginx:** `/etc/nginx/sites-enabled/codetalk`, `server_name backend.kasimir.info`.
  - `/analyzer/` → proxy 3010, **kein Basic-Auth** (seit Go-live, öffentliche Registrierung).
  - `/claudeapps/odoo-analyse/` → statischer Report (Einzel-Instanz), Basic-Auth bleibt.
  - `location = /claudeapps` → 301 Redirect auf `/claudeapps/` (Trailing-Slash-Fix).
  - Catch-all `location / → 127.0.0.1:3000` (Node „codetalk").
- **URLs:** App `https://backend.kasimir.info/analyzer/` ·
  Statischer Report `https://backend.kasimir.info/claudeapps/odoo-analyse/`
- **Landing-Page** `https://backend.kasimir.info/claudeapps/`:
  ODOO-ANALYZER-Kachel unter „Tools" → verlinkt direkt auf `/analyzer/`.
  (Eintrag in `claudeapps/shared/apps.js` im `main`-Branch des Repos.)

## 4. Wichtige Befehle
```bash
# Analyse starten (über die Web-App UI), danach Report automatisch verfügbar.

# Web-App lokal starten (Dev, ohne nginx → BASE_PATH leer lassen):
python3 odoo/webapp/app.py                # http://127.0.0.1:3010

# Statischen Report (Einzel-Instanz) neu erzeugen + deployen:
bash odoo/update.sh

# Nach Codeänderung in app.py:
pm2 restart odoo-analyzer

# DB-Backup:
bash odoo/webapp/backup.sh
```

## 5. Zugangsdaten / Secrets (NICHT im Git)

**`odoo/.env`** (Odoo-Instanz, wird vom Einzel-Extraktions-Workflow genutzt):
```
ODOO_URL=https://viaalia-test-saas19-0623.odoo.com
ODOO_DB=viaalia-test-saas19-0623
ODOO_USER=patrick.kasimir@viaalia.de
ODOO_API_KEY=…
```

**`odoo/webapp/.env`** (SMTP für die Web-App):
```
SMTP_HOST=smtp.ionos.de
SMTP_PORT=587
SMTP_USER=apppp@kasimir.info
SMTP_PASS=…   # → Patrick fragen
SMTP_FROM=apppp@kasimir.info
```

Auf neuem Rechner: beide `.env`-Dateien neu anlegen, App-Daten (`odoo/webapp/data/`) starten frisch.

## 6. Funktionsumfang – VOLLSTÄNDIG ERLEDIGT

| Feature | Status |
|---|---|
| Analyse (5 Reiter: Überblick, Technik, Prozesse, Sicherheit, Advisor) | ✅ |
| Health-Score + Regelkatalog (advisor.py) | ✅ |
| Gruppen-Baum (App-Bezug, klickbar, Richtung + Business/Technisch-Filter) | ✅ |
| Applikationen & Rollen (Detailseite mit CRUD-Rechten je Gruppe) | ✅ |
| **DE/EN-Sprachumschalter** in sicherheit.html | ✅ |
| App-Abhängigkeitsgraph | ✅ |
| SaaS-Web-App: Registrierung, Login, Konto, Mandantentrennung | ✅ |
| TOTP-2FA (verschlüsselt) + Recovery Codes | ✅ |
| E-Mail-Verifizierung + Passwort-Reset (SMTP Ionos) | ✅ |
| Admin-Rolle: Benutzerverwaltung + Alle-Instanzen-Ansicht | ✅ |
| Verbindungstest vor Analyse | ✅ |
| Impressum/Datenschutz (ViaAlia GmbH) | ✅ |
| Go-live: Basic-Auth entfernt, öffentliche Registrierung | ✅ |
| nginx Redirect /claudeapps → /claudeapps/ | ✅ |
| Landing-Page: ODOO-ANALYZER unter Tools | ✅ |

## 7. OFFEN / nächste Schritte
- **SOLVVision Test neu analysieren:** Analyse neu starten um (a) Kategorie-Fallback-Fix
  und (b) DE-Übersetzungen im JSON zu bekommen. → Einfach in der Web-App „Analyse starten".
- **Testnutzer aufräumen:** `u@test.de` und `z@test.de` über Admin-UI löschen.
- **Weitere Instanzen anlegen:** z. B. Produktiv-Instanz als zweite Instanz erfassen.
- Optional: Analyse-Verlauf pro Instanz, eigene Domain, AVV-Vorlage für Kundenbetrieb.

## 8. Stolpersteine / Lessons Learned
- **Kein pip auf dem Server** → nur Standardbibliothek (jinja2 ist als System-Paket da).
- **Odoo 19.2 Gruppenmodell:** `res.groups` nutzt `privilege_id → res.groups.privilege → category_id`
  (neu), NICHT mehr `category_id` direkt. Fallback: `category_id` direkt (OCA/ältere Module),
  dann `full_name`-Parsing für Custom-Gruppen.
- **XML-RPC Sprach-Kontext:** `context={"lang": "de_DE"}` in kwargs gibt übersetzte Namen zurück.
  `model_id[1]` in Many2one-Feldern wird dabei korrekt in der Zielsprache geliefert.
- **XML-RPC:** Optionen (`fields`/`order`/`context`) immer als kwargs, nie positional.
- **Report-JS:** Init/Render erst NACH allen const/function-Definitionen aufrufen (sonst TDZ).
- **nginx-Unterpfad:** App muss `BASE_PATH` kennen; Trailing-Slash-Redirect nötig für statische Roots.
- **Admin-Zuweisung:** DB-Migration weist automatisch dem Benutzer mit `id=1` Admin zu → bei
  Testnutzern kann das der falsche sein. Manuell korrigieren via `sqlite3` wenn nötig.

## 9. Datenschutz/DSGVO (Kurz)
Bei Analyse fremder Instanzen ist der Kunde Verantwortlicher, wir Auftragsverarbeiter (Art. 28 →
AVV nötig). Umgesetzt: Key wird nicht gespeichert, Datenminimierung, TLS, EU-Hosting, Löschfunktion.
Vor echtem Kundenbetrieb: AVV/Datenschutzerklärung/Verarbeitungsverzeichnis + juristische Prüfung.
Empfehlung an Kunden: dedizierter API-User (`odoo/docs/readonly-api-user.md`).

---
*Letzte relevante Commits siehe `git log --oneline`. Dieses Dokument bei größeren Änderungen aktualisieren.*
