#!/usr/bin/env python3
"""Wiederverwendbarer Odoo-XML-RPC-Client für das Lieferantenvertrags-Projekt.

Liest Zugangsdaten aus Umgebungsvariablen oder aus der lokalen .env
(im selben Verzeichnis):
    ODOO_URL, ODOO_DB, ODOO_USER, ODOO_API_KEY

Der API-Key wird NIEMALS ausgegeben oder geloggt.

Besonderheiten für Odoo 19 (siehe IMPLEMENTATION_PLAN.md):
- execute_kw-Optionen IMMER als kwargs (context, fields, order ...), nie positional.
- Übersetzbare Felder immer mit explizitem context={'lang': <code>} lesen/schreiben.
"""
from __future__ import annotations

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


class OdooClient:
    """Dünne, gut lesbare Hülle um xmlrpc.client für ein Odoo-Konto."""

    def __init__(self, url: str, db: str, user: str, api_key: str):
        self.url = url.rstrip("/")
        self.db = db
        self.user = user
        self._key = api_key
        self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        self.uid: int | None = None
        self.version: dict = {}

    # ---- Verbindung -----------------------------------------------------
    @classmethod
    def from_env(cls) -> "OdooClient":
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
            raise SystemExit(
                "Fehlende Angaben: " + ", ".join(missing)
                + "\n→ odoo/lieferantenvertrag/.env ausfüllen "
                  "(Vorlage: .env.example)."
            )
        return cls(url, db, user, key)

    def connect(self) -> int:
        """Authentifiziert und gibt die UID zurück. Wirft bei Fehler."""
        self.version = self._common.version()
        uid = self._common.authenticate(self.db, self.user, self._key, {})
        if not uid:
            raise SystemExit(
                "Authentifizierung fehlgeschlagen – DB, Login oder API-Key prüfen."
            )
        self.uid = uid
        return uid

    # ---- Kern-RPC -------------------------------------------------------
    def execute(self, model: str, method: str, *args, **kwargs):
        """execute_kw mit kwargs-Optionen (context, fields, order, limit ...)."""
        assert self.uid, "Erst connect() aufrufen."
        return self._models.execute_kw(
            self.db, self.uid, self._key, model, method, list(args), kwargs
        )

    # ---- Bequeme Kurzformen --------------------------------------------
    def search(self, model, domain, **kw):
        return self.execute(model, "search", domain, **kw)

    def search_read(self, model, domain, fields=None, **kw):
        if fields is not None:
            kw["fields"] = fields
        return self.execute(model, "search_read", domain, **kw)

    def search_count(self, model, domain):
        return self.execute(model, "search_count", domain)

    def read(self, model, ids, fields=None, **kw):
        if fields is not None:
            kw["fields"] = fields
        return self.execute(model, "read", ids, **kw)

    def create(self, model, vals, **kw):
        return self.execute(model, "create", vals, **kw)

    def write(self, model, ids, vals, **kw):
        return self.execute(model, "write", ids, vals, **kw)

    def unlink(self, model, ids, **kw):
        return self.execute(model, "unlink", ids, **kw)

    def fields_get(self, model, attributes=None):
        kw = {}
        if attributes is not None:
            kw["attributes"] = attributes
        return self.execute(model, "fields_get", **kw)

    # ---- Idempotente Helfer --------------------------------------------
    def find_one(self, model, domain, fields=None):
        """Erster Treffer oder None."""
        res = self.search_read(model, domain, fields=fields, limit=1)
        return res[0] if res else None

    def ensure(self, model, match_domain, vals, fields=None):
        """Legt einen Datensatz an, falls per match_domain keiner existiert.

        Gibt (record_id, created: bool) zurück.
        """
        existing = self.find_one(model, match_domain, fields=fields or ["id"])
        if existing:
            return existing["id"], False
        return self.create(model, vals), True


def main() -> int:
    """Schneller Verbindungstest (wie das alte connect.py, aber instanzspezifisch)."""
    try:
        c = OdooClient.from_env()
        c.connect()
        print("Server erreichbar – Version:",
              c.version.get("server_version", "?"))
        print("Authentifiziert – UID:", c.uid)
        me = c.read("res.users", [c.uid], ["name", "login"])[0]
        print(f"Angemeldet als: {me['name']} ({me['login']})")
        print("res.partner Datensätze:", c.search_count("res.partner", []))
        print("\nVerbindung OK ✓")
        return 0
    except SystemExit as e:
        print(e)
        return 1
    except Exception as e:  # noqa: BLE001 – bewusst breit für klare Meldung
        print("Verbindungsfehler:", type(e).__name__, "-", str(e))
        return 3


if __name__ == "__main__":
    sys.exit(main())
