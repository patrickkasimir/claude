#!/usr/bin/env python3
"""Automatische technische + fachliche Analyse der Odoo-Instanz.

Verbindet via odoo/.env (XML-RPC), sammelt Metadaten und schreibt das
Ergebnis als JS-Datendatei für die Doku-Website:

    odoo/report/data.js   ->  window.ODOO_ANALYSIS = {...}
    odoo/report/analysis.json (rohdaten)

Es werden ausschließlich Metadaten und Zähler erfasst – keine echten
Geschäftsdatensätze – und der API-Key wird nicht ausgegeben.

Aufruf:  python3 odoo/analyze.py
"""
import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
import xmlrpc.client

HERE = Path(__file__).parent


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


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

    def execute(model, method, *args, **kw):
        return models.execute_kw(db, uid, key, model, method, list(args), kw)

    def count(model, domain=None):
        try:
            return execute(model, "search_count", domain or [])
        except Exception:
            return None

    me = execute("res.users", "read", [uid], fields=["name", "login"])[0]

    # ---- technische Kennzahlen ----
    tech = {
        "modules_installed": count("ir.module.module", [["state", "=", "installed"]]),
        "modules_total":     count("ir.module.module", []),
        "apps_installed":    count("ir.module.module", [["state", "=", "installed"], ["application", "=", True]]),
        "models":            count("ir.model", []),
        "models_custom":     count("ir.model", [["state", "=", "manual"]]),
        "fields":            count("ir.model.fields", []),
        "fields_custom":     count("ir.model.fields", [["state", "=", "manual"]]),
        "crons":             count("ir.cron", []),
        "server_actions":    count("ir.actions.server", []),
        "automations":       count("base.automation", []),
        "users_total":       count("res.users", []),
        "users_active":      count("res.users", [["active", "=", True], ["share", "=", False]]),
        "companies":         count("res.company", []),
    }

    try:
        langs = execute("res.lang", "search_read", [["active", "=", True]],
                        fields=["name", "code"])
    except Exception:
        langs = []

    try:
        apps = execute("ir.module.module", "search_read",
                       [["state", "=", "installed"], ["application", "=", True]],
                       fields=["name", "shortdesc", "latest_version"], order="shortdesc")
    except Exception:
        apps = []

    try:
        all_mods = execute("ir.module.module", "search_read",
                           [["state", "=", "installed"]],
                           fields=["name", "shortdesc", "application"], order="name")
    except Exception:
        all_mods = []

    # ---- fachliche Geschäftsobjekte (nur Zähler) ----
    business = [
        ("res.partner", "Kontakte"),
        ("product.template", "Produkte"),
        ("product.product", "Produktvarianten"),
        ("sale.order", "Verkaufsaufträge"),
        ("purchase.order", "Einkaufsbestellungen"),
        ("account.move", "Buchungen / Rechnungen"),
        ("account.journal", "Journale"),
        ("crm.lead", "Leads / Chancen"),
        ("stock.picking", "Lieferungen"),
        ("stock.warehouse", "Lager"),
        ("mrp.production", "Fertigungsaufträge"),
        ("project.project", "Projekte"),
        ("project.task", "Aufgaben"),
        ("hr.employee", "Mitarbeiter"),
        ("hr.department", "Abteilungen"),
        ("calendar.event", "Termine"),
        ("helpdesk.ticket", "Helpdesk-Tickets"),
        ("pos.order", "Kassen-Bestellungen"),
        ("website", "Websites"),
    ]
    business_counts = []
    for model, label in business:
        c = count(model)
        if c is not None:
            business_counts.append({"model": model, "label": label, "count": c})

    data = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "server": {
            "version": version, "db": db, "url": url,
            "user": f"{me['name']} ({me['login']}, uid {uid})",
        },
        "tech": tech,
        "languages": langs,
        "apps": apps,
        "modules": all_mods,
        "business_counts": business_counts,
    }

    out_dir = Path(os.environ.get("ODOO_OUT_DIR") or (HERE / "report"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data.js").write_text(
        "// Automatisch erzeugt von odoo/analyze.py – nicht manuell editieren.\n"
        "window.ODOO_ANALYSIS = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    (out_dir / "analysis.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Analyse geschrieben →", out_dir / "data.js")
    print(f"  Apps installiert  : {tech['apps_installed']}")
    print(f"  Module installiert: {tech['modules_installed']} / {tech['modules_total']}")
    print(f"  Modelle           : {tech['models']} (custom: {tech['models_custom']})")
    print(f"  Felder custom     : {tech['fields_custom']}")
    print(f"  Benutzer (intern) : {tech['users_active']}")
    print(f"  Geschäftsobjekte  : {len(business_counts)} erfasst")
    return 0


if __name__ == "__main__":
    sys.exit(main())
