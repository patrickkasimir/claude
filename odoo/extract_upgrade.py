#!/usr/bin/env python3
"""Upgrade-Risiko-Extraktor (read-only, statisch) – Reiter „Upgradefähigkeit".

Nutzt das gemeinsame Modul upgrade_checks.py (DRY mit updatesets/run.py lint).
Nur Metadaten/Zähler + technische Namen, keine Inhalte (Datenminimierung).

Ausgabe (gitignored):  odoo/report/upgrade.js  (window.ODOO_UPGRADE)
Aufruf:  python3 odoo/extract_upgrade.py
"""
import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
import xmlrpc.client

import upgrade_checks

HERE = Path(__file__).parent


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class _Adapter:
    """Dünner Client im von upgrade_checks erwarteten Interface (search_read/read/fields_get)."""
    def __init__(self, ex):
        self._ex = ex

    def search_read(self, model, domain, fields=None, **kw):
        if fields is not None:
            kw["fields"] = fields
        try:
            return self._ex(model, "search_read", domain or [], **kw)
        except Exception:
            return []

    def read(self, model, ids, fields=None):
        if not ids:
            return []
        kw = {"fields": fields} if fields else {}
        try:
            return self._ex(model, "read", ids, **kw)
        except Exception:
            return []

    def fields_get(self, model):
        try:
            return self._ex(model, "fields_get", [], attributes=["type"])
        except Exception:
            return {}


def main() -> int:
    load_env(HERE / ".env")
    url = os.environ.get("ODOO_URL", "").rstrip("/")
    db = os.environ.get("ODOO_DB", "")
    user = os.environ.get("ODOO_USER", "")
    key = os.environ.get("ODOO_API_KEY", "")
    if not all([url, db, user, key]):
        print("Zugangsdaten fehlen (odoo/.env).")
        return 1

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    version = common.version().get("server_version")
    uid = common.authenticate(db, user, key, {})
    if not uid:
        print("Authentifizierung fehlgeschlagen.")
        return 2
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def ex(model, method, *args, **kw):
        return models.execute_kw(db, uid, key, model, method, list(args), kw)

    findings = upgrade_checks.run(_Adapter(ex))
    summary = upgrade_checks.summarize(findings)

    SEV_RANK = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (SEV_RANK.get(f["severity"], 9), f["kind"], f["title"]))

    data = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "server": {"version": version, "db": db, "url": url},
        "score": summary["score"],
        "grade": summary["grade"],
        "by_severity": summary["by_severity"],
        "counts": summary["counts"],
        "findings": findings,
    }

    out = Path(os.environ.get("ODOO_OUT_DIR") or (HERE / "report"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "upgrade.js").write_text(
        "// Automatisch erzeugt von odoo/extract_upgrade.py - nicht manuell editieren.\n"
        "window.ODOO_UPGRADE = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    (out / "upgrade.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Upgrade-Risiko-Analyse geschrieben →", out / "upgrade.js")
    print(f"  Score        : {summary['score']}/100 ({summary['grade']})")
    print(f"  Schweregrade : {summary['by_severity']}")
    print(f"  Arten        : {summary['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
