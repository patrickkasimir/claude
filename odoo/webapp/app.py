#!/usr/bin/env python3
"""Odoo-Analyzer – Web-App (kundentauglicher Stand).

Funktionen:
- Registrierung/Login/Logout, E-Mail-Verifizierung, Passwort-Reset, Konto-Verwaltung
- Mandanten-Trennung (jede Instanz gehört einem Benutzer)
- Instanzen anlegen/bearbeiten/löschen; Analyse je Instanz; Reports unter /i/<id>/
- Landing-Page + Pflichtseiten (Impressum/Datenschutz)
- Sicherheit: scrypt-Passwörter, Session-Token (HttpOnly/Secure/SameSite),
  Session-Ablauf, Rate-Limit, Fehlerseiten

Datenschutz: API-Key wird NICHT gespeichert (Eingabe pro Analyse, transient).
Nur Stammdaten + anonymisierte Analyse-Ergebnisse werden gespeichert.

E-Mail: per SMTP_* Umgebungsvariablen. Ohne SMTP -> Mails landen als Datei in
data/mail_outbox/ (Dev-Fallback), damit Verifizierungs-/Reset-Links testbar sind.

Stack: Standardbibliothek + jinja2 + sqlite3 (kein pip nötig). Bindet 127.0.0.1.
Start:  python3 odoo/webapp/app.py
"""
import os
import sys
import time
import html
import hmac
import base64
import struct
import hashlib
import secrets
import sqlite3
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs, quote

from jinja2 import Environment

# .env laden (gitignored) – muss vor os.environ.get()-Aufrufen stehen
_ENV_FILE = Path(__file__).resolve().parent / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

HOST, PORT = "127.0.0.1", 3010
WEBAPP = Path(__file__).resolve().parent
ODOO = WEBAPP.parent
DATA = WEBAPP / "data"
INSTANCES = DATA / "instances"
DB = DATA / "app.db"
BASE_URL = os.environ.get("APP_BASE_URL", "https://backend.kasimir.info/analyzer").rstrip("/")
BASE = os.environ.get("BASE_PATH", "").rstrip("/")   # nginx-Unterpfad, z.B. /analyzer (für ausgehende Links)

SCRIPTS = ["analyze.py", "extract_processes.py", "extract_technical.py",
           "extract_security.py", "extract_modules.py", "advisor.py"]
PAGES = ["index.html", "technik.html", "prozesse.html", "sicherheit.html", "advisor.html"]
CTYPE = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".css": "text/css"}
SESSION_MAX_AGE = 14 * 86400
RL_WINDOW, RL_LIMIT = 600, 10
_rl, _rl_lock = {}, threading.Lock()
JENV = Environment(autoescape=True)

DATA.mkdir(parents=True, exist_ok=True)
INSTANCES.mkdir(parents=True, exist_ok=True)


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


with db() as con:
    con.execute("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL, pwhash TEXT NOT NULL, verified INTEGER DEFAULT 0,
        totp_secret TEXT, created_at TEXT)""")
    try:
        con.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT")   # Migration für bestehende DBs
    except sqlite3.OperationalError:
        pass
    con.execute("""CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER, created_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS tokens(token TEXT PRIMARY KEY, user_id INTEGER, kind TEXT, created_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS instances(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        name TEXT, url TEXT, db TEXT, login TEXT, created_at TEXT, last_run TEXT, last_status TEXT)""")


# ───────── Auth / Token / Mail ─────────
def hash_pw(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${hashlib.scrypt(pw.encode(), salt=salt, n=16384, r=8, p=1, dklen=32).hex()}"


def verify_pw(pw, stored):
    try:
        _, salt_hex, _ = stored.split("$")
        return hmac.compare_digest(stored, hash_pw(pw, bytes.fromhex(salt_hex)))
    except Exception:
        return False


def new_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_at(secret, t):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    h = hmac.new(key, struct.pack(">Q", int(t // 30)), hashlib.sha1).digest()
    o = h[-1] & 0x0f
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000).zfill(6)


def verify_totp(secret, code):
    code = (code or "").strip().replace(" ", "")
    if not (secret and code.isdigit()):
        return False
    now = time.time()
    return any(hmac.compare_digest(totp_at(secret, now + d * 30), code) for d in (-1, 0, 1))


def user_by_session(token):
    if not token:
        return None
    with db() as con:
        row = con.execute("SELECT u.*, s.created_at AS s_created FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=?", (token,)).fetchone()
        if not row:
            return None
        try:
            if (datetime.now() - datetime.fromisoformat(row["s_created"])).total_seconds() > SESSION_MAX_AGE:
                con.execute("DELETE FROM sessions WHERE token=?", (token,))
                return None
        except Exception:
            pass
        return row


def new_session(uid):
    t = secrets.token_urlsafe(32)
    with db() as con:
        con.execute("INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)", (t, uid, datetime.now().isoformat()))
    return t


def make_token(uid, kind):
    t = secrets.token_urlsafe(32)
    with db() as con:
        con.execute("INSERT INTO tokens(token,user_id,kind,created_at) VALUES(?,?,?,?)", (t, uid, kind, datetime.now().isoformat()))
    return t


def consume_token(t, kind, max_age=86400):
    with db() as con:
        row = con.execute("SELECT * FROM tokens WHERE token=? AND kind=?", (t, kind)).fetchone()
        if not row:
            return None
        con.execute("DELETE FROM tokens WHERE token=?", (t,))
        try:
            if (datetime.now() - datetime.fromisoformat(row["created_at"])).total_seconds() > max_age:
                return None
        except Exception:
            pass
        return row["user_id"]


def send_mail(to, subject, body):
    host = os.environ.get("SMTP_HOST")
    if not host:                                  # Dev-Fallback: in Datei schreiben
        box = DATA / "mail_outbox"
        box.mkdir(exist_ok=True)
        (box / f"{int(time.time()*1000)}.txt").write_text(f"To: {to}\nSubject: {subject}\n\n{body}", encoding="utf-8")
        return
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "noreply@localhost"))
    msg["To"], msg["Subject"] = to, subject
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
        s.starttls()
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
        s.send_message(msg)


def send_verify(uid, email):
    link = f"{BASE_URL}/verify?token={make_token(uid, 'verify')}"
    send_mail(email, "E-Mail bestätigen – Odoo-Analyzer",
              f"Bitte bestätige deine E-Mail-Adresse:\n\n{link}\n\nFalls du dich nicht registriert hast, ignoriere diese Mail.")


# ───────── Analyse (Key transient) ─────────
def run_analysis(inst_id, api_key):
    with db() as con:
        row = con.execute("SELECT * FROM instances WHERE id=?", (inst_id,)).fetchone()
        if not row:
            return
        con.execute("UPDATE instances SET last_status=? WHERE id=?", ("läuft …", inst_id))
    out = INSTANCES / str(inst_id) / "report"
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({"ODOO_URL": row["url"], "ODOO_DB": row["db"], "ODOO_USER": row["login"],
                "ODOO_API_KEY": api_key, "ODOO_OUT_DIR": str(out)})
    status = "ok"
    try:
        for s in SCRIPTS:
            r = subprocess.run([sys.executable, str(ODOO / s)], env=env, capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                tail = (r.stdout + r.stderr).strip().splitlines()
                status = f"Fehler in {s}: " + (tail[-1][:120] if tail else "unbekannt")
                break
        for p in PAGES:
            (out / p).write_text((ODOO / "report" / p).read_text(encoding="utf-8"), encoding="utf-8")
    except Exception as e:
        status = f"Fehler: {e}"
    finally:
        api_key = None
    with db() as con:
        con.execute("UPDATE instances SET last_run=?, last_status=? WHERE id=?",
                    (datetime.now().strftime("%d.%m.%Y %H:%M"), status, inst_id))


# ───────── HTML ─────────
CSS = """<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#f4f3f7;color:#2b2733;font-family:'Segoe UI',system-ui,sans-serif;font-size:15px;display:flex;flex-direction:column;min-height:100vh}
header{background:linear-gradient(120deg,#714B67,#9b6a8c);color:#fff;padding:20px 28px;display:flex;justify-content:space-between;align-items:center}
header a.brand{color:#fff;text-decoration:none;font-size:1.4rem;font-weight:600}
header .u{font-size:.85rem}header .u a{color:#fff;margin-left:12px;text-decoration:none}
main{max-width:980px;width:100%;margin:0 auto;padding:28px;flex:1}
.card{background:#fff;border:1px solid #e7e3ec;border-radius:12px;padding:18px 20px;margin-bottom:18px;box-shadow:0 1px 3px #2b273310}
h2{font-size:1.05rem;margin-bottom:14px}h3{font-size:.95rem;margin:14px 0 6px}
p{line-height:1.6}p+p{margin-top:8px}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th{text-align:left;color:#8b8794;font-weight:400;font-size:.72rem;text-transform:uppercase;letter-spacing:.5px;padding:8px;border-bottom:1px solid #e7e3ec}
td{padding:10px 8px;border-bottom:1px solid #00000008;vertical-align:middle}
.mono{font-family:ui-monospace,monospace;font-size:.78rem;color:#714B67}
.btn{display:inline-block;border:none;border-radius:7px;padding:7px 13px;font-size:.82rem;cursor:pointer;text-decoration:none}
.btn.p{background:#714B67;color:#fff}.btn.s{background:#f0e9ef;color:#714B67}.btn.d{background:#fbeaea;color:#b14}
.st{font-size:.78rem;padding:2px 8px;border-radius:999px;background:#f1efe8;color:#5f5e5a}
.st.ok{background:#e6f4ec;color:#2f8f63}.st.err{background:#fbeaea;color:#b14}.st.run{background:#fbf0dc;color:#c98a2b}
form.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;align-items:end}
label{display:block;font-size:.72rem;color:#8b8794;margin-bottom:3px}
input{width:100%;padding:8px 10px;border:1px solid #e7e3ec;border-radius:7px;font-size:.88rem}
input:focus{outline:none;border-color:#714B67}
.muted{color:#8b8794;font-size:.82rem}.empty{color:#8b8794;padding:14px 0}
.aform{display:flex;gap:6px;align-items:center}.aform input{width:130px}
.flow-notes{list-style:none;margin-top:14px;font-size:.85rem;color:#5f5e5a}
.flow-notes li{padding:3px 0 3px 22px;position:relative}.flow-notes li:before{content:"✓";position:absolute;left:0;color:#2f8f63;font-weight:700}
.auth{max-width:380px;margin:50px auto}.auth input{margin-bottom:12px}
.msg{padding:9px 12px;border-radius:7px;font-size:.85rem;margin-bottom:12px}.msg.e{background:#fbeaea;color:#b14}.msg.i{background:#e7f0fa;color:#1e5aa0}.msg.w{background:#fbf0dc;color:#9a6a12}
.alt{margin-top:14px;font-size:.85rem;color:#8b8794;text-align:center}.alt a{color:#714B67}
.hero{text-align:center;padding:36px 20px}.hero h1{font-size:1.8rem;color:#714B67}.hero p{color:#5f5e5a;max-width:560px;margin:12px auto 22px}
footer{color:#8b8794;font-size:.8rem;text-align:center;padding:18px}footer a{color:#714B67;text-decoration:none;margin:0 6px}
.legal{font-size:.92rem}.legal p,.legal li{color:#444}
</style>"""

FOOTER = '<footer>© Odoo-Analyzer · <a href="/impressum">Impressum</a> · <a href="/datenschutz">Datenschutz</a></footer>'

FLOW_SVG = """<svg viewBox="0 0 780 330" width="100%" style="max-width:780px" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Datenfluss">
<defs><marker id="ar" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#714B67"/></marker>
<marker id="arm" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#8b8794"/></marker></defs>
<rect x="24" y="112" width="150" height="72" rx="12" fill="#fff" stroke="#e7e3ec"/><text x="99" y="142" text-anchor="middle" font-size="14" font-weight="600" fill="#2b2733">Nutzer</text><text x="99" y="162" text-anchor="middle" font-size="12" fill="#8b8794">Browser</text>
<rect x="298" y="80" width="214" height="134" rx="14" fill="#f0e9ef" stroke="#d9c9d4"/><text x="405" y="104" text-anchor="middle" font-size="14" font-weight="600" fill="#714B67">Ionos-Server (EU / DE)</text><text x="405" y="124" text-anchor="middle" font-size="12" fill="#5f5e5a">Analyzer-App · Datenbank</text>
<line x1="318" y1="138" x2="492" y2="138" stroke="#e7e3ec"/><text x="405" y="158" text-anchor="middle" font-size="11" fill="#5f5e5a">speichert: Name · URL · DB · Login</text><text x="405" y="178" text-anchor="middle" font-size="11" font-weight="600" fill="#b14">speichert NICHT: API-Key</text>
<rect x="628" y="112" width="128" height="72" rx="12" fill="#fff" stroke="#e7e3ec"/><text x="692" y="142" text-anchor="middle" font-size="14" font-weight="600" fill="#2b2733">Kunden-Odoo</text><text x="692" y="162" text-anchor="middle" font-size="12" fill="#8b8794">Instanz</text>
<rect x="305" y="250" width="200" height="54" rx="12" fill="#fff8ee" stroke="#c98a2b" stroke-dasharray="5 4"/><text x="405" y="274" text-anchor="middle" font-size="13" font-weight="600" fill="#7a5b1e">KI-Modell</text><text x="405" y="292" text-anchor="middle" font-size="11" fill="#a07a2e">optional / geplant</text>
<line x1="174" y1="148" x2="294" y2="148" stroke="#714B67" marker-end="url(#ar)"/><text x="234" y="140" text-anchor="middle" font-size="11" fill="#714B67">HTTPS · Login</text>
<line x1="514" y1="132" x2="624" y2="132" stroke="#714B67" marker-end="url(#ar)"/><text x="569" y="124" text-anchor="middle" font-size="10.5" fill="#714B67">API-Key nur zur Laufzeit</text>
<line x1="624" y1="166" x2="514" y2="166" stroke="#8b8794" marker-end="url(#arm)"/><text x="569" y="182" text-anchor="middle" font-size="10.5" fill="#8b8794">nur Metadaten / Zähler</text>
<line x1="405" y1="214" x2="405" y2="248" stroke="#c98a2b" stroke-dasharray="5 4" marker-end="url(#ar)"/></svg>"""


def shell(title, inner, user=None):
    hdr = f'<header><a class="brand" href="/">Odoo-Analyzer</a>'
    if user:
        hdr += f'<div class="u">{html.escape(user["email"])} <a href="/account">Konto</a> <form method="post" action="/logout" style="display:inline"><button class="btn s" style="padding:4px 10px">Logout</button></form></div>'
    hdr += "</header>"
    page = f"<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Odoo-Analyzer · {title}</title>{CSS}</head><body>{hdr}<main>{inner}</main>{FOOTER}</body></html>"
    return page.replace('href="/', f'href="{BASE}/').replace('action="/', f'action="{BASE}/') if BASE else page


def error_page(title, msg):
    return shell(title, f'<div class="card"><h2>{title}</h2><p class="muted">{msg}</p></div>')


DASH_TPL = JENV.from_string("""
{% if not user.verified %}<div class="card"><div class="msg w">Bitte bestätige deine E-Mail-Adresse. <form method="post" action="/resend-verify" style="display:inline"><button class="btn s">Bestätigungs-Mail erneut senden</button></form></div></div>{% endif %}
<div class="card"><h2>Datenfluss &amp; Datenschutz</h2>{{ flow|safe }}
  <ul class="flow-notes"><li>Hosting in der EU (Ionos, Deutschland).</li><li>Der API-Key wird nur zur Analyse eingegeben und <b>niemals gespeichert</b>.</li><li>Übertragen werden nur Struktur/Metadaten/Zähler – keine Geschäftsinhalte.</li></ul></div>
<div class="card"><h2>Meine Instanzen</h2>
{% if rows %}<table><thead><tr><th>Name</th><th>Instanz</th><th>Letzte Analyse</th><th>Status</th><th>Analyse (API-Key)</th><th></th></tr></thead><tbody>
{% for r in rows %}<tr>
  <td><b>{{ r.name }}</b><div class="muted">{{ r.login }}</div></td><td class="mono">{{ r.db }}</td><td>{{ r.last_run or "–" }}</td>
  <td>{% set s = r.last_status or "" %}<span class="st {{ 'ok' if s=='ok' else 'run' if 'läuft' in s else 'err' if s else '' }}">{{ s or "neu" }}</span></td>
  <td><form class="aform" method="post" action="/analyze"><input type="hidden" name="id" value="{{ r.id }}"><input type="password" name="key" placeholder="API-Key" required autocomplete="off"><button class="btn p">Analysieren</button></form></td>
  <td style="white-space:nowrap;text-align:right">{% if r.has_report %}<a class="btn s" href="/i/{{ r.id }}/" target="_blank">Öffnen</a>{% endif %}
    <a class="btn s" href="/edit?id={{ r.id }}">Bearbeiten</a>
    <form method="post" action="/delete" style="display:inline" onsubmit="return confirm('Instanz löschen?')"><input type="hidden" name="id" value="{{ r.id }}"><button class="btn d">Löschen</button></form></td>
</tr>{% endfor %}</tbody></table>{% else %}<div class="empty">Noch keine Instanz erfasst.</div>{% endif %}</div>
<div class="card"><h2>Instanz hinzufügen</h2>
  <form class="grid" method="post" action="/add">
    <div><label>Name</label><input name="name" required></div><div><label>URL</label><input name="url" placeholder="https://firma.odoo.com" required></div>
    <div><label>Datenbank</label><input name="db" required></div><div><label>Login</label><input name="login" required></div>
    <div><button class="btn p" style="width:100%">Speichern</button></div></form>
  <div class="muted" style="margin-top:10px">Kein API-Key hier – der wird erst beim Analysieren eingegeben (und nicht gespeichert).</div></div>""")

LANDING = JENV.from_string("""<div class="card"><div class="hero">
  <h1>Odoo-Analyzer</h1>
  <p>Analysiere jede Odoo-Instanz technisch und fachlich – Sicherheit, Prozesse, Customizing-Fallstricke und ein Health-Score. Datenschutzfreundlich: der API-Key wird nie gespeichert.</p>
  <a class="btn p" href="/register">Kostenlos registrieren</a> <a class="btn s" href="/login">Anmelden</a>
</div>{{ flow|safe }}</div>""")

AUTH = JENV.from_string("""<div class="auth"><div class="card"><h2>{{ title }}</h2>
  {% if msg %}<div class="msg {{ msgtype }}">{{ msg }}</div>{% endif %}
  <form method="post" action="{{ action }}">
    {% for f in fields %}<label>{{ f.label }}</label><input name="{{ f.name }}" type="{{ f.type }}" {{ 'required' if f.required }} {% if f.attr %}{{ f.attr|safe }}{% endif %}>{% endfor %}
    {% if token %}<input type="hidden" name="token" value="{{ token }}">{% endif %}
    <button class="btn p" style="width:100%">{{ title }}</button></form>
  <div class="alt">{{ alt|safe }}</div></div></div>""")

ACCOUNT = JENV.from_string("""<div class="card"><h2>Konto</h2><p class="muted">Angemeldet als {{ user.email }} · {{ 'E-Mail bestätigt' if user.verified else 'E-Mail nicht bestätigt' }}</p></div>
<div class="card"><h2>Passwort ändern</h2>{% if msg %}<div class="msg {{ msgtype }}">{{ msg }}</div>{% endif %}
  <form method="post" action="/account" style="max-width:360px">
    <label>Aktuelles Passwort</label><input name="current" type="password" required>
    <label>Neues Passwort</label><input name="new" type="password" minlength="8" required>
    <button class="btn p" style="margin-top:12px">Ändern</button></form></div>
<div class="card"><h2>Zwei-Faktor-Authentifizierung (2FA)</h2>
{% if user.totp_secret %}<p class="muted">Status: <b style="color:#2f8f63">aktiv</b>.</p>
  <form method="post" action="/2fa/disable" style="max-width:360px;margin-top:10px"><label>Passwort zum Deaktivieren</label><input name="password" type="password" required><button class="btn d" style="margin-top:10px">2FA deaktivieren</button></form>
{% else %}<p class="muted">Status: nicht aktiv. Schütze dein Konto zusätzlich mit einer Authenticator-App.</p>
  <p style="margin-top:10px"><a class="btn p" href="/2fa/setup">2FA einrichten</a></p>{% endif %}</div>""")

EDIT = JENV.from_string("""<div class="card"><h2>Instanz bearbeiten</h2>
  <form class="grid" method="post" action="/edit"><input type="hidden" name="id" value="{{ r.id }}">
    <div><label>Name</label><input name="name" value="{{ r.name }}" required></div><div><label>URL</label><input name="url" value="{{ r.url }}" required></div>
    <div><label>Datenbank</label><input name="db" value="{{ r.db }}" required></div><div><label>Login</label><input name="login" value="{{ r.login }}" required></div>
    <div><button class="btn p" style="width:100%">Speichern</button></div></form>
  <p style="margin-top:12px"><a class="btn s" href="/">Zurück</a></p></div>""")

TWOFA_SETUP = JENV.from_string("""<div class="card"><h2>Zwei-Faktor-Authentifizierung einrichten</h2>
  <p>Scanne den QR-Code mit einer Authenticator-App (z. B. Google Authenticator, Authy) – oder gib den Schlüssel manuell ein.</p>
  <div id="qr" style="margin:16px 0"></div>
  <p class="muted">Schlüssel: <span class="mono">{{ secret }}</span></p>
  {% if msg %}<div class="msg e">{{ msg }}</div>{% endif %}
  <form method="post" action="/2fa/enable" style="max-width:300px;margin-top:6px">
    <input type="hidden" name="secret" value="{{ secret }}">
    <label>6-stelliger Code aus der App</label><input name="code" inputmode="numeric" pattern="[0-9]*" autocomplete="off" required>
    <button class="btn p" style="margin-top:10px">Aktivieren</button></form>
  <p style="margin-top:12px"><a class="btn s" href="/account">Abbrechen</a></p>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
  <script>new QRCode(document.getElementById('qr'),{text:{{ otpauth|tojson }},width:172,height:172});</script></div>""")

TWOFA_LOGIN = JENV.from_string("""<div class="auth"><div class="card"><h2>Zwei-Faktor-Code</h2>
  {% if msg %}<div class="msg e">{{ msg }}</div>{% endif %}
  <form method="post" action="/2fa/verify"><input type="hidden" name="token" value="{{ token }}">
    <label>6-stelliger Code aus deiner App</label><input name="code" inputmode="numeric" pattern="[0-9]*" autocomplete="off" autofocus required>
    <button class="btn p" style="width:100%;margin-top:10px">Anmelden</button></form>
  <div class="alt"><a href="/login">Abbrechen</a></div></div></div>""")

IMPRESSUM = JENV.from_string("""<div class="card legal"><h2>Impressum</h2>
  <p><b>Angaben gemäß § 5 DDG / § 5 TMG</b></p>
  <p>ViaAlia GmbH<br>Tulpenstr. 1<br>85053 Ingolstadt</p>
  <h3>Vertreten durch</h3><p>Barbara Kasimir (Geschäftsführerin), Patrick Kasimir (Geschäftsführer)</p>
  <h3>Kontakt</h3><p>Telefon: 016096498283<br>E-Mail: info@viaalia.de</p>
  <h3>Verantwortlich für den Inhalt</h3><p>Patrick Kasimir, Tulpenstr. 1, 85053 Ingolstadt</p>
</div>""")

DATENSCHUTZ = JENV.from_string("""<div class="card legal"><h2>Datenschutzerklärung</h2>
  <h3>1. Verantwortlicher</h3><p>ViaAlia GmbH, Tulpenstr. 1, 85053 Ingolstadt, info@viaalia.de.</p>
  <h3>2. Zweck &amp; verarbeitete Daten</h3>
  <p><b>Konto:</b> E-Mail und (gehashtes) Passwort zur Anmeldung. Rechtsgrundlage: Vertrag (Art. 6 Abs. 1 lit. b DSGVO).</p>
  <p><b>Hinterlegte Odoo-Instanzen:</b> Name, URL, Datenbank, Login. Der <b>API-Key wird nicht gespeichert</b> – er wird nur zur Laufzeit der Analyse verwendet.</p>
  <p><b>Analyse-Ergebnisse:</b> ausschließlich technische Struktur-/Metadaten und Zähler der Instanz – keine Geschäftsinhalte; personenbezogene Daten werden minimiert (z. B. nur Anzahl privilegierter Benutzer).</p>
  <h3>3. Auftragsverarbeitung</h3><p>Wird im Auftrag eines Kunden dessen Odoo-Instanz analysiert, handeln wir als <b>Auftragsverarbeiter</b> (Art. 28 DSGVO); Grundlage ist ein Auftragsverarbeitungsvertrag (AVV).</p>
  <h3>4. Hosting</h3><p>Server in der EU (Ionos, Deutschland). Übertragung TLS-verschlüsselt.</p>
  <h3>5. Cookies</h3><p>Nur ein technisch notwendiges Session-Cookie (HttpOnly, Secure, SameSite) – kein Tracking.</p>
  <h3>6. Speicherdauer</h3><p>Konto-/Instanzdaten bis zur Löschung durch den Nutzer. Analysen können jederzeit gelöscht werden.</p>
  <h3>7. Ihre Rechte</h3><p>Auskunft, Berichtigung, Löschung, Einschränkung, Datenübertragbarkeit, Widerspruch sowie Beschwerde bei einer Aufsichtsbehörde.</p>
</div>""")


def dashboard_html(user):
    with db() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM instances WHERE user_id=? ORDER BY id DESC", (user["id"],))]
    for r in rows:
        r["has_report"] = (INSTANCES / str(r["id"]) / "report" / "index.html").is_file()
    return shell("Dashboard", DASH_TPL.render(rows=rows, flow=FLOW_SVG, user=user), user)


# ───────── HTTP ─────────
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _user(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return user_by_session(c["sid"].value) if "sid" in c else None

    def _send(self, code, body, ctype="text/html; charset=utf-8", cookie=None):
        body = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, to=".", cookie=None):
        if to.startswith("/"):
            to = BASE + to
        self.send_response(303)
        self.send_header("Location", to)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def _form(self):
        n = int(self.headers.get("Content-Length", 0))
        return {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8")).items()}

    def _client_ip(self):
        return self.headers.get("X-Real-IP") or self.client_address[0]

    def _cookie(self, token=None, clear=False):
        sec = "; Secure" if self.headers.get("X-Real-IP") else ""
        return ("sid=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax" + sec) if clear else f"sid={token}; HttpOnly; Path=/; SameSite=Lax{sec}"

    def _rate_limited(self):
        ip, now = self._client_ip(), time.time()
        with _rl_lock:
            q = [t for t in _rl.get(ip, []) if now - t < RL_WINDOW]
            q.append(now)
            _rl[ip] = q
            return len(q) > RL_LIMIT

    def do_GET(self):
        try:
            self.route_get()
        except Exception:
            self._safe500()

    def do_POST(self):
        try:
            self.route_post()
        except Exception:
            self._safe500()

    def _safe500(self):
        try:
            self._send(500, error_page("Fehler", "Es ist ein interner Fehler aufgetreten."))
        except Exception:
            pass

    def route_get(self):
        q = urlparse(self.path)
        path, query = q.path, parse_qs(q.query)
        user = self._user()
        if path == "/impressum":
            return self._send(200, shell("Impressum", IMPRESSUM.render(), user))
        if path == "/datenschutz":
            return self._send(200, shell("Datenschutz", DATENSCHUTZ.render(), user))
        if path == "/login":
            return self._send(200, shell("Anmelden", AUTH.render(title="Anmelden", action="/login",
                fields=[{"label": "E-Mail", "name": "email", "type": "email", "required": 1},
                        {"label": "Passwort", "name": "password", "type": "password", "required": 1}],
                alt='Kein Konto? <a href="/register">Registrieren</a> · <a href="/forgot">Passwort vergessen?</a>')))
        if path == "/register":
            return self._send(200, shell("Registrieren", AUTH.render(title="Registrieren", action="/register",
                fields=[{"label": "E-Mail", "name": "email", "type": "email", "required": 1},
                        {"label": "Passwort (min. 8)", "name": "password", "type": "password", "required": 1, "attr": 'minlength="8"'}],
                alt='Schon ein Konto? <a href="/login">Anmelden</a>')))
        if path == "/forgot":
            return self._send(200, shell("Passwort vergessen", AUTH.render(title="Passwort zurücksetzen", action="/forgot",
                fields=[{"label": "E-Mail", "name": "email", "type": "email", "required": 1}],
                alt='<a href="/login">Zurück zur Anmeldung</a>')))
        if path == "/reset":
            tok = (query.get("token") or [""])[0]
            return self._send(200, shell("Neues Passwort", AUTH.render(title="Neues Passwort setzen", action="/reset", token=tok,
                fields=[{"label": "Neues Passwort (min. 8)", "name": "password", "type": "password", "required": 1, "attr": 'minlength="8"'}],
                alt="")))
        if path == "/verify":
            uid = consume_token((query.get("token") or [""])[0], "verify", max_age=7 * 86400)
            if uid:
                with db() as con:
                    con.execute("UPDATE users SET verified=1 WHERE id=?", (uid,))
            return self._send(200, error_page("E-Mail bestätigt" if uid else "Link ungültig",
                "Danke, deine E-Mail ist bestätigt." if uid else "Der Bestätigungslink ist ungültig oder abgelaufen."))
        if path == "/2fa":
            return self._send(200, shell("2FA", TWOFA_LOGIN.render(token=(query.get("token") or [""])[0], msg=None)))
        if path == "/":
            return self._send(200, dashboard_html(user)) if user else self._send(200, shell("Start", LANDING.render(flow=FLOW_SVG)))
        if not user:
            return self._redirect("/login")
        if path == "/account":
            return self._send(200, shell("Konto", ACCOUNT.render(user=user, msg=None), user))
        if path == "/2fa/setup":
            secret = new_totp_secret()
            otpauth = f"otpauth://totp/Odoo-Analyzer:{quote(user['email'])}?secret={secret}&issuer=Odoo-Analyzer&digits=6&period=30"
            return self._send(200, shell("2FA einrichten", TWOFA_SETUP.render(secret=secret, otpauth=otpauth, msg=None), user))
        if path == "/edit":
            iid = (query.get("id") or [""])[0]
            with db() as con:
                r = con.execute("SELECT * FROM instances WHERE id=? AND user_id=?", (iid, user["id"])).fetchone()
            if not r:
                return self._send(404, error_page("Nicht gefunden", "Instanz nicht gefunden."))
            return self._send(200, shell("Bearbeiten", EDIT.render(r=dict(r)), user))
        if path.startswith("/i/"):
            parts = path[3:].split("/", 1)
            iid = parts[0]
            rel = parts[1] if len(parts) > 1 and parts[1] else "index.html"
            if ".." in rel:
                return self._send(400, "bad path")
            with db() as con:
                own = con.execute("SELECT 1 FROM instances WHERE id=? AND user_id=?", (iid, user["id"])).fetchone()
            if not own:
                return self._send(403, error_page("Kein Zugriff", "Diese Instanz gehört nicht zu deinem Konto."))
            f = INSTANCES / iid / "report" / rel
            if not f.is_file():
                return self._send(404, error_page("Noch keine Analyse", "Für diese Instanz wurde noch keine Analyse erstellt."))
            return self._send(200, f.read_bytes(), CTYPE.get(f.suffix, "application/octet-stream"))
        return self._send(404, error_page("Nicht gefunden", "Diese Seite existiert nicht."))

    def route_post(self):
        path = urlparse(self.path).path
        if path in ("/login", "/register", "/forgot", "/2fa/verify") and self._rate_limited():
            return self._send(429, error_page("Zu viele Versuche", "Bitte in einigen Minuten erneut versuchen."))
        form = self._form()

        if path == "/register":
            email, pw = form.get("email", "").strip().lower(), form.get("password", "")
            if len(pw) < 8 or "@" not in email:
                return self._send(200, shell("Registrieren", AUTH.render(title="Registrieren", action="/register", msg="E-Mail ungültig oder Passwort < 8 Zeichen.", msgtype="e",
                    fields=[{"label": "E-Mail", "name": "email", "type": "email", "required": 1}, {"label": "Passwort (min. 8)", "name": "password", "type": "password", "required": 1, "attr": 'minlength="8"'}], alt='Schon ein Konto? <a href="/login">Anmelden</a>')))
            try:
                with db() as con:
                    uid = con.execute("INSERT INTO users(email,pwhash,created_at) VALUES(?,?,?)", (email, hash_pw(pw), datetime.now().isoformat())).lastrowid
            except sqlite3.IntegrityError:
                return self._send(200, shell("Registrieren", AUTH.render(title="Registrieren", action="/register", msg="E-Mail ist bereits registriert.", msgtype="e",
                    fields=[{"label": "E-Mail", "name": "email", "type": "email", "required": 1}, {"label": "Passwort (min. 8)", "name": "password", "type": "password", "required": 1, "attr": 'minlength="8"'}], alt='Schon ein Konto? <a href="/login">Anmelden</a>')))
            send_verify(uid, email)
            return self._redirect("/", cookie=self._cookie(new_session(uid)))

        if path == "/login":
            email, pw = form.get("email", "").strip().lower(), form.get("password", "")
            with db() as con:
                u = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not u or not verify_pw(pw, u["pwhash"]):
                return self._send(200, shell("Anmelden", AUTH.render(title="Anmelden", action="/login", msg="E-Mail oder Passwort falsch.", msgtype="e",
                    fields=[{"label": "E-Mail", "name": "email", "type": "email", "required": 1}, {"label": "Passwort", "name": "password", "type": "password", "required": 1}], alt='Kein Konto? <a href="/register">Registrieren</a> · <a href="/forgot">Passwort vergessen?</a>')))
            if u["totp_secret"]:
                return self._send(200, shell("2FA", TWOFA_LOGIN.render(token=make_token(u["id"], "2fa_login"), msg=None)))
            return self._redirect("/", cookie=self._cookie(new_session(u["id"])))

        if path == "/forgot":
            email = form.get("email", "").strip().lower()
            with db() as con:
                u = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if u:
                link = f"{BASE_URL}/reset?token={make_token(u['id'], 'reset')}"
                send_mail(email, "Passwort zurücksetzen – Odoo-Analyzer", f"Setze dein Passwort zurück:\n\n{link}\n\nGültig für 24 Stunden. Falls du das nicht warst, ignoriere diese Mail.")
            return self._send(200, shell("Passwort vergessen", AUTH.render(title="Passwort zurücksetzen", action="/forgot", msg="Falls ein Konto existiert, wurde eine E-Mail mit Reset-Link gesendet.", msgtype="i",
                fields=[{"label": "E-Mail", "name": "email", "type": "email", "required": 1}], alt='<a href="/login">Zurück zur Anmeldung</a>')))

        if path == "/reset":
            tok, pw = form.get("token", ""), form.get("password", "")
            uid = consume_token(tok, "reset", max_age=86400) if len(pw) >= 8 else None
            if not uid:
                return self._send(200, error_page("Link ungültig", "Der Reset-Link ist ungültig/abgelaufen oder das Passwort zu kurz."))
            with db() as con:
                con.execute("UPDATE users SET pwhash=? WHERE id=?", (hash_pw(pw), uid))
                con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            return self._send(200, error_page("Passwort geändert", "Dein Passwort wurde gesetzt. Du kannst dich jetzt anmelden."))

        if path == "/2fa/verify":
            tok, code = form.get("token", ""), form.get("code", "")
            with db() as con:
                row = con.execute("SELECT * FROM tokens WHERE token=? AND kind='2fa_login'", (tok,)).fetchone()
            ok_age = bool(row) and (datetime.now() - datetime.fromisoformat(row["created_at"])).total_seconds() < 300
            if not ok_age:
                return self._send(200, error_page("Abgelaufen", "Bitte erneut anmelden."))
            with db() as con:
                u = con.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()
            if u and verify_totp(u["totp_secret"], code):
                with db() as con:
                    con.execute("DELETE FROM tokens WHERE token=?", (tok,))
                return self._redirect("/", cookie=self._cookie(new_session(u["id"])))
            return self._send(200, shell("2FA", TWOFA_LOGIN.render(token=tok, msg="Code falsch – bitte erneut.")))

        user = self._user()
        if not user:
            return self._redirect("/login")

        if path == "/logout":
            c = SimpleCookie(self.headers.get("Cookie", ""))
            if "sid" in c:
                with db() as con:
                    con.execute("DELETE FROM sessions WHERE token=?", (c["sid"].value,))
            return self._redirect("/login", cookie=self._cookie(clear=True))
        if path == "/resend-verify":
            if not user["verified"]:
                send_verify(user["id"], user["email"])
            return self._redirect("/")
        if path == "/account":
            cur, new = form.get("current", ""), form.get("new", "")
            if not verify_pw(cur, user["pwhash"]):
                return self._send(200, shell("Konto", ACCOUNT.render(user=user, msg="Aktuelles Passwort falsch.", msgtype="e"), user))
            if len(new) < 8:
                return self._send(200, shell("Konto", ACCOUNT.render(user=user, msg="Neues Passwort muss min. 8 Zeichen haben.", msgtype="e"), user))
            with db() as con:
                con.execute("UPDATE users SET pwhash=? WHERE id=?", (hash_pw(new), user["id"]))
            return self._send(200, shell("Konto", ACCOUNT.render(user=user, msg="Passwort geändert.", msgtype="i"), user))
        if path == "/2fa/enable":
            secret, code = form.get("secret", ""), form.get("code", "")
            if verify_totp(secret, code):
                with db() as con:
                    con.execute("UPDATE users SET totp_secret=? WHERE id=?", (secret, user["id"]))
                return self._redirect("/account")
            otpauth = f"otpauth://totp/Odoo-Analyzer:{quote(user['email'])}?secret={secret}&issuer=Odoo-Analyzer&digits=6&period=30"
            return self._send(200, shell("2FA einrichten", TWOFA_SETUP.render(secret=secret, otpauth=otpauth, msg="Code falsch – bitte erneut versuchen."), user))
        if path == "/2fa/disable":
            if verify_pw(form.get("password", ""), user["pwhash"]):
                with db() as con:
                    con.execute("UPDATE users SET totp_secret=NULL WHERE id=?", (user["id"],))
            return self._redirect("/account")
        if path == "/add":
            with db() as con:
                con.execute("INSERT INTO instances(user_id,name,url,db,login,created_at) VALUES(?,?,?,?,?,?)",
                            (user["id"], form["name"].strip(), form["url"].strip().rstrip("/"), form["db"].strip(), form["login"].strip(), datetime.now().strftime("%d.%m.%Y %H:%M")))
            return self._redirect("/")
        if path == "/edit":
            with db() as con:
                con.execute("UPDATE instances SET name=?,url=?,db=?,login=? WHERE id=? AND user_id=?",
                            (form["name"].strip(), form["url"].strip().rstrip("/"), form["db"].strip(), form["login"].strip(), form["id"], user["id"]))
            return self._redirect("/")
        if path == "/analyze":
            iid, key = int(form["id"]), form.get("key", "")
            with db() as con:
                own = con.execute("SELECT 1 FROM instances WHERE id=? AND user_id=?", (iid, user["id"])).fetchone()
            if own and key:
                threading.Thread(target=run_analysis, args=(iid, key), daemon=True).start()
            return self._redirect("/")
        if path == "/delete":
            iid = form["id"]
            with db() as con:
                con.execute("DELETE FROM instances WHERE id=? AND user_id=?", (iid, user["id"]))
            d = INSTANCES / iid
            if d.exists():
                import shutil
                shutil.rmtree(d, ignore_errors=True)
            return self._redirect("/")
        return self._send(404, error_page("Nicht gefunden", "Diese Seite existiert nicht."))


if __name__ == "__main__":
    print(f"Odoo-Analyzer läuft auf http://{HOST}:{PORT}  (Strg+C zum Beenden)")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
