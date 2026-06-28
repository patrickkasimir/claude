#!/usr/bin/env python3
"""Odoo-Analyzer – Web-App (Phase 2: Registrierung + Mehrnutzer).

- Benutzerkonten (Registrierung/Login), Passwörter via hashlib.scrypt,
  Sessions per Cookie + Token in der DB.
- Mandanten-Trennung: jede Instanz gehört einem Benutzer; jeder sieht nur
  seine eigenen Instanzen/Reports.
- API-Key wird NICHT gespeichert (Eingabe pro Analyse, nur zur Laufzeit).
- Nur Stammdaten + anonymisierte Analyse-Ergebnisse werden gespeichert.

Stack: Standardbibliothek (http.server) + jinja2 + sqlite3 (kein pip nötig).
Bindet nur an 127.0.0.1 -> Zugriff über nginx (TLS, vorerst zusätzl. Basic-Auth).

Start:  python3 odoo/webapp/app.py
"""
import os
import sys
import time
import hmac
import hashlib
import secrets
import sqlite3
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs

from jinja2 import Template

HOST, PORT = "127.0.0.1", 3010
WEBAPP = Path(__file__).resolve().parent
ODOO = WEBAPP.parent
DATA = WEBAPP / "data"
INSTANCES = DATA / "instances"
DB = DATA / "app.db"

SCRIPTS = ["analyze.py", "extract_processes.py", "extract_technical.py",
           "extract_security.py", "extract_modules.py", "advisor.py"]
PAGES = ["index.html", "technik.html", "prozesse.html", "sicherheit.html", "advisor.html"]
CTYPE = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".css": "text/css"}

SESSION_MAX_AGE = 14 * 86400          # Session-Ablauf: 14 Tage
RL_WINDOW, RL_LIMIT = 600, 10         # max. 10 Auth-Versuche je IP / 10 min
_rl = {}
_rl_lock = threading.Lock()


def error_page(title, msg):
    return ("<!DOCTYPE html><meta charset='utf-8'><title>" + title + "</title>"
            "<div style=\"font-family:'Segoe UI',system-ui,sans-serif;max-width:480px;margin:80px auto;"
            "padding:24px;text-align:center;color:#2b2733\">"
            "<h1 style='font-size:1.4rem;color:#714B67'>" + title + "</h1>"
            "<p style='color:#8b8794;margin-top:8px'>" + msg + "</p>"
            "<p style='margin-top:18px'><a href='/' style='color:#714B67'>Zur Startseite</a></p></div>")

DATA.mkdir(parents=True, exist_ok=True)
INSTANCES.mkdir(parents=True, exist_ok=True)


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


with db() as con:
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
        pwhash TEXT NOT NULL, created_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS instances (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        name TEXT NOT NULL, url TEXT NOT NULL, db TEXT NOT NULL, login TEXT NOT NULL,
        created_at TEXT, last_run TEXT, last_status TEXT)""")


# ---------- Auth-Helfer ----------
def hash_pw(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_pw(pw, stored):
    try:
        _, salt_hex, _ = stored.split("$")
        return hmac.compare_digest(stored, hash_pw(pw, bytes.fromhex(salt_hex)))
    except Exception:
        return False


def user_by_session(token):
    if not token:
        return None
    with db() as con:
        row = con.execute(
            "SELECT u.*, s.created_at AS s_created FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=?",
            (token,)).fetchone()
        if not row:
            return None
        try:
            age = (datetime.now() - datetime.fromisoformat(row["s_created"])).total_seconds()
        except Exception:
            age = 0
        if age > SESSION_MAX_AGE:
            con.execute("DELETE FROM sessions WHERE token=?", (token,))
            return None
        return row


def new_session(user_id):
    token = secrets.token_urlsafe(32)
    with db() as con:
        con.execute("INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)",
                    (token, user_id, datetime.now().isoformat()))
    return token


# ---------- Analyse (Key transient) ----------
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
            r = subprocess.run([sys.executable, str(ODOO / s)], env=env,
                               capture_output=True, text=True, timeout=300)
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


# ---------- Templates ----------
HEAD = """<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#f4f3f7;color:#2b2733;font-family:'Segoe UI',system-ui,sans-serif;font-size:15px}
header{background:linear-gradient(120deg,#714B67,#9b6a8c);color:#fff;padding:22px 28px;display:flex;justify-content:space-between;align-items:center}
header h1{font-size:1.4rem;font-weight:600}header .u{font-size:.85rem;opacity:.95}
header .u a{color:#fff;margin-left:12px}
main{max-width:980px;margin:0 auto;padding:28px}
.card{background:#fff;border:1px solid #e7e3ec;border-radius:12px;padding:18px 20px;margin-bottom:18px;box-shadow:0 1px 3px #2b273310}
h2{font-size:1.05rem;margin-bottom:14px}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th{text-align:left;color:#8b8794;font-weight:400;font-size:.72rem;text-transform:uppercase;letter-spacing:.5px;padding:8px;border-bottom:1px solid #e7e3ec}
td{padding:10px 8px;border-bottom:1px solid #00000008;vertical-align:middle}
.mono{font-family:ui-monospace,monospace;font-size:.78rem;color:#714B67}
.btn{display:inline-block;border:none;border-radius:7px;padding:7px 13px;font-size:.82rem;cursor:pointer;text-decoration:none}
.btn.p{background:#714B67;color:#fff}.btn.s{background:#f0e9ef;color:#714B67}.btn.d{background:#fbeaea;color:#b14}
.st{font-size:.78rem;padding:2px 8px;border-radius:999px;background:#f1efe8;color:#5f5e5a}
.st.ok{background:#e6f4ec;color:#2f8f63}.st.err{background:#fbeaea;color:#b14}.st.run{background:#fbf0dc;color:#c98a2b}
form.add{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;align-items:end}
label{display:block;font-size:.72rem;color:#8b8794;margin-bottom:3px}
input{width:100%;padding:8px 10px;border:1px solid #e7e3ec;border-radius:7px;font-size:.88rem}
input:focus{outline:none;border-color:#714B67}
.muted{color:#8b8794;font-size:.82rem}.empty{color:#8b8794;padding:14px 0}
.aform{display:flex;gap:6px;align-items:center}.aform input{width:130px}
.flow-notes{list-style:none;margin-top:14px;font-size:.85rem;color:#5f5e5a}
.flow-notes li{padding:3px 0 3px 22px;position:relative}.flow-notes li:before{content:"✓";position:absolute;left:0;color:#2f8f63;font-weight:700}
.auth{max-width:380px;margin:60px auto;padding:0 20px}
.auth .card h2{margin-bottom:6px}.auth .sub{color:#8b8794;font-size:.85rem;margin-bottom:16px}
.auth input{margin-bottom:12px}.auth .err{background:#fbeaea;color:#b14;padding:8px 12px;border-radius:7px;font-size:.85rem;margin-bottom:12px}
.auth .alt{margin-top:14px;font-size:.85rem;color:#8b8794;text-align:center}
</style>"""

AUTH = Template("""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Odoo-Analyzer · {{ title }}</title>""" + HEAD + """</head>
<body><div class="auth"><div class="card">
  <h2>{{ title }}</h2><div class="sub">Odoo-Analyzer</div>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  <form method="post" action="{{ action }}">
    <label>E-Mail</label><input name="email" type="email" required autofocus>
    <label>Passwort</label><input name="password" type="password" required {% if action=='register' %}minlength="8"{% endif %}>
    <button class="btn p" style="width:100%">{{ title }}</button>
  </form>
  <div class="alt">{{ alt|safe }}</div>
</div></div></body></html>""")

DASH = Template("""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Odoo-Analyzer</title>""" + HEAD + """</head><body>
<header><h1>Odoo-Analyzer</h1><div class="u">{{ user.email }} <form method="post" action="logout" style="display:inline"><button class="btn s" style="padding:4px 10px">Logout</button></form></div></header>
<main>
  <div class="card">
    <h2>Datenfluss &amp; Datenschutz</h2>
    {{ flow_svg|safe }}
    <ul class="flow-notes">
      <li>Hosting in der EU (Ionos, Deutschland).</li>
      <li>Der API-Key wird nur zur Analyse eingegeben und <b>niemals gespeichert</b>.</li>
      <li>Übertragen werden nur Struktur/Metadaten/Zähler – keine Geschäftsinhalte.</li>
      <li>Das KI-Modell ist optional/geplant; derzeit fließen dorthin keine Daten.</li>
    </ul>
  </div>
  <div class="card">
    <h2>Meine Instanzen</h2>
    {% if rows %}
    <table><thead><tr><th>Name</th><th>Instanz</th><th>Letzte Analyse</th><th>Status</th><th>Analyse (API-Key)</th><th></th></tr></thead><tbody>
    {% for r in rows %}
      <tr>
        <td><b>{{ r.name }}</b><div class="muted">{{ r.login }}</div></td>
        <td class="mono">{{ r.db }}</td>
        <td>{{ r.last_run or "–" }}</td>
        <td>{% set s = r.last_status or "" %}<span class="st {{ 'ok' if s=='ok' else 'run' if 'läuft' in s else 'err' if s else '' }}">{{ s or "neu" }}</span></td>
        <td><form class="aform" method="post" action="analyze"><input type="hidden" name="id" value="{{ r.id }}"><input type="password" name="key" placeholder="API-Key" required autocomplete="off"><button class="btn p">Analysieren</button></form></td>
        <td style="white-space:nowrap;text-align:right">
          {% if r.has_report %}<a class="btn s" href="i/{{ r.id }}/" target="_blank">Öffnen</a>{% endif %}
          <form method="post" action="delete" style="display:inline" onsubmit="return confirm('Instanz löschen?')"><input type="hidden" name="id" value="{{ r.id }}"><button class="btn d">Löschen</button></form>
        </td>
      </tr>
    {% endfor %}
    </tbody></table>
    {% else %}<div class="empty">Noch keine Instanz erfasst.</div>{% endif %}
  </div>
  <div class="card">
    <h2>Instanz hinzufügen</h2>
    <form class="add" method="post" action="add">
      <div><label>Name</label><input name="name" placeholder="Test-Instanz" required></div>
      <div><label>URL</label><input name="url" placeholder="https://firma.odoo.com" required></div>
      <div><label>Datenbank</label><input name="db" placeholder="firma" required></div>
      <div><label>Login</label><input name="login" placeholder="user@firma.de" required></div>
      <div><button class="btn p" style="width:100%">Speichern</button></div>
    </form>
    <div class="muted" style="margin-top:10px">Kein API-Key hier – der wird erst beim Analysieren eingegeben (und nicht gespeichert).</div>
  </div>
</main></body></html>""")


FLOW_SVG = """<svg viewBox="0 0 780 330" width="100%" style="max-width:780px" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Datenfluss zwischen Nutzer, Ionos-Server, Kundeninstanz und optionalem KI-Modell">
<defs><marker id="ar" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#714B67"/></marker>
<marker id="arm" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#8b8794"/></marker></defs>
<rect x="24" y="112" width="150" height="72" rx="12" fill="#fff" stroke="#e7e3ec"/>
<text x="99" y="142" text-anchor="middle" font-size="14" font-weight="600" fill="#2b2733">Nutzer</text>
<text x="99" y="162" text-anchor="middle" font-size="12" fill="#8b8794">Browser</text>
<rect x="298" y="80" width="214" height="134" rx="14" fill="#f0e9ef" stroke="#d9c9d4"/>
<text x="405" y="104" text-anchor="middle" font-size="14" font-weight="600" fill="#714B67">Ionos-Server (EU / DE)</text>
<text x="405" y="124" text-anchor="middle" font-size="12" fill="#5f5e5a">Analyzer-App · Datenbank</text>
<line x1="318" y1="138" x2="492" y2="138" stroke="#e7e3ec"/>
<text x="405" y="158" text-anchor="middle" font-size="11" fill="#5f5e5a">speichert: Name · URL · DB · Login</text>
<text x="405" y="178" text-anchor="middle" font-size="11" font-weight="600" fill="#b14">speichert NICHT: API-Key</text>
<rect x="628" y="112" width="128" height="72" rx="12" fill="#fff" stroke="#e7e3ec"/>
<text x="692" y="142" text-anchor="middle" font-size="14" font-weight="600" fill="#2b2733">Kunden-Odoo</text>
<text x="692" y="162" text-anchor="middle" font-size="12" fill="#8b8794">Instanz</text>
<rect x="305" y="250" width="200" height="54" rx="12" fill="#fff8ee" stroke="#c98a2b" stroke-dasharray="5 4"/>
<text x="405" y="274" text-anchor="middle" font-size="13" font-weight="600" fill="#7a5b1e">KI-Modell</text>
<text x="405" y="292" text-anchor="middle" font-size="11" fill="#a07a2e">optional / geplant</text>
<line x1="174" y1="148" x2="294" y2="148" stroke="#714B67" marker-end="url(#ar)"/>
<text x="234" y="140" text-anchor="middle" font-size="11" fill="#714B67">HTTPS · Login</text>
<line x1="514" y1="132" x2="624" y2="132" stroke="#714B67" marker-end="url(#ar)"/>
<text x="569" y="124" text-anchor="middle" font-size="10.5" fill="#714B67">API-Key nur zur Laufzeit</text>
<line x1="624" y1="166" x2="514" y2="166" stroke="#8b8794" marker-end="url(#arm)"/>
<text x="569" y="182" text-anchor="middle" font-size="10.5" fill="#8b8794">nur Metadaten / Zähler</text>
<line x1="405" y1="214" x2="405" y2="248" stroke="#c98a2b" stroke-dasharray="5 4" marker-end="url(#ar)"/>
<text x="448" y="236" text-anchor="middle" font-size="10" fill="#a07a2e">optional</text>
</svg>"""


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
        sec = "; Secure" if self.headers.get("X-Real-IP") else ""   # Secure nur hinter nginx/HTTPS
        if clear:
            return "sid=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax" + sec
        return f"sid={token}; HttpOnly; Path=/; SameSite=Lax{sec}"

    def _rate_limited(self):
        ip, now = self._client_ip(), time.time()
        with _rl_lock:
            q = [t for t in _rl.get(ip, []) if now - t < RL_WINDOW]
            q.append(now)
            _rl[ip] = q
            return len(q) > RL_LIMIT

    def _safe500(self):
        try:
            self._send(500, error_page("Fehler", "Es ist ein interner Fehler aufgetreten."))
        except Exception:
            pass

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

    def route_get(self):
        path = urlparse(self.path).path
        user = self._user()
        if path == "/login":
            return self._send(200, AUTH.render(title="Anmelden", action="login", error=None,
                              alt='Kein Konto? <a href="register">Registrieren</a>'))
        if path == "/register":
            return self._send(200, AUTH.render(title="Registrieren", action="register", error=None,
                              alt='Schon ein Konto? <a href="login">Anmelden</a>'))
        if not user:
            return self._redirect("login")
        if path == "/":
            return self._send(200, dashboard_html(user))
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
                return self._send(404, "Noch keine Analyse für diese Instanz.")
            return self._send(200, f.read_bytes(), CTYPE.get(f.suffix, "application/octet-stream"))
        return self._send(404, error_page("Nicht gefunden", "Diese Seite existiert nicht."))

    def route_post(self):
        path = urlparse(self.path).path
        if path in ("/login", "/register") and self._rate_limited():
            return self._send(429, error_page("Zu viele Versuche", "Bitte in einigen Minuten erneut versuchen."))
        form = self._form()
        if path == "/register":
            email, pw = form.get("email", "").strip().lower(), form.get("password", "")
            if len(pw) < 8 or "@" not in email:
                return self._send(200, AUTH.render(title="Registrieren", action="register",
                                  error="E-Mail ungültig oder Passwort < 8 Zeichen.",
                                  alt='Schon ein Konto? <a href="login">Anmelden</a>'))
            try:
                with db() as con:
                    cur = con.execute("INSERT INTO users(email,pwhash,created_at) VALUES(?,?,?)",
                                      (email, hash_pw(pw), datetime.now().isoformat()))
                    uid = cur.lastrowid
            except sqlite3.IntegrityError:
                return self._send(200, AUTH.render(title="Registrieren", action="register",
                                  error="E-Mail ist bereits registriert.",
                                  alt='Schon ein Konto? <a href="login">Anmelden</a>'))
            return self._redirect(".", cookie=self._cookie(new_session(uid)))
        if path == "/login":
            email, pw = form.get("email", "").strip().lower(), form.get("password", "")
            with db() as con:
                u = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not u or not verify_pw(pw, u["pwhash"]):
                return self._send(200, AUTH.render(title="Anmelden", action="login",
                                  error="E-Mail oder Passwort falsch.",
                                  alt='Kein Konto? <a href="register">Registrieren</a>'))
            return self._redirect(".", cookie=self._cookie(new_session(u['id'])))

        user = self._user()
        if not user:
            return self._redirect("login")
        if path == "/logout":
            c = SimpleCookie(self.headers.get("Cookie", ""))
            if "sid" in c:
                with db() as con:
                    con.execute("DELETE FROM sessions WHERE token=?", (c["sid"].value,))
            return self._redirect("login", cookie=self._cookie(clear=True))
        if path == "/add":
            with db() as con:
                con.execute("INSERT INTO instances(user_id,name,url,db,login,created_at) VALUES(?,?,?,?,?,?)",
                            (user["id"], form["name"].strip(), form["url"].strip().rstrip("/"),
                             form["db"].strip(), form["login"].strip(), datetime.now().strftime("%d.%m.%Y %H:%M")))
            return self._redirect()
        if path == "/analyze":
            iid, key = int(form["id"]), form.get("key", "")
            with db() as con:
                own = con.execute("SELECT 1 FROM instances WHERE id=? AND user_id=?", (iid, user["id"])).fetchone()
            if own and key:
                threading.Thread(target=run_analysis, args=(iid, key), daemon=True).start()
            return self._redirect()
        if path == "/delete":
            iid = form["id"]
            with db() as con:
                con.execute("DELETE FROM instances WHERE id=? AND user_id=?", (iid, user["id"]))
            d = INSTANCES / iid
            if d.exists():
                import shutil
                shutil.rmtree(d, ignore_errors=True)
            return self._redirect()
        return self._send(404, error_page("Nicht gefunden", "Diese Seite existiert nicht."))


def dashboard_html(user):
    with db() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM instances WHERE user_id=? ORDER BY id DESC", (user["id"],))]
    for r in rows:
        r["has_report"] = (INSTANCES / str(r["id"]) / "report" / "index.html").is_file()
    return DASH.render(rows=rows, flow_svg=FLOW_SVG, user=user)


if __name__ == "__main__":
    print(f"Odoo-Analyzer läuft auf http://{HOST}:{PORT}  (Strg+C zum Beenden)")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
