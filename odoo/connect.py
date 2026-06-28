#!/usr/bin/env python3
"""Odoo External API – Verbindungstest via XML-RPC.

Liest die Zugangsdaten aus Umgebungsvariablen oder aus odoo/.env:
    ODOO_URL, ODOO_DB, ODOO_USER, ODOO_API_KEY

Verifiziert die Verbindung (Serverversion + authenticate) und liest
den eigenen Benutzer aus. Der API-Key wird NICHT ausgegeben.

Aufruf:
    python3 odoo/connect.py
"""
import os
import sys
import xmlrpc.client
from pathlib import Path


def load_env(path: Path) -> None:
    """Minimaler .env-Loader (KEY=VALUE pro Zeile)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def main() -> int:
    load_env(Path(__file__).parent / ".env")

    url = os.environ.get("ODOO_URL", "").rstrip("/")
    db = os.environ.get("ODOO_DB", "")
    user = os.environ.get("ODOO_USER", "")
    key = os.environ.get("ODOO_API_KEY", "")

    missing = [n for n, v in [
        ("ODOO_URL", url), ("ODOO_DB", db),
        ("ODOO_USER", user), ("ODOO_API_KEY", key),
    ] if not v]
    if missing:
        print("Fehlende Angaben:", ", ".join(missing))
        print("→ odoo/.env ausfüllen (Vorlage: odoo/.env.example).")
        return 1

    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        version = common.version()
        print("Server erreichbar – Version:", version.get("server_version", "?"))

        uid = common.authenticate(db, user, key, {})
        if not uid:
            print("Authentifizierung fehlgeschlagen – DB, Login oder API-Key prüfen.")
            return 2
        print("Authentifiziert – UID:", uid)

        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        me = models.execute_kw(db, uid, key, "res.users", "read",
                               [[uid]], {"fields": ["name", "login"]})
        print(f"Angemeldet als: {me[0]['name']} ({me[0]['login']})")

        partners = models.execute_kw(db, uid, key, "res.partner", "search_count", [[]])
        print("res.partner Datensätze:", partners)
        print("\nVerbindung OK ✓")
        return 0
    except Exception as e:  # noqa: BLE001 – bewusst breit für klare Fehlermeldung
        print("Verbindungsfehler:", type(e).__name__, "-", str(e))
        return 3


if __name__ == "__main__":
    sys.exit(main())
