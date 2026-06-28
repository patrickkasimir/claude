#!/usr/bin/env python3
"""Prozess-Extraktor – liest 'wie laufen die Prozesse' aus einer Odoo-Instanz.

Portabel: arbeitet nur über die Odoo-API (XML-RPC) und prüft dynamisch,
welche Modelle/Felder vorhanden sind -> läuft auf beliebigen Instanzen.
Erfasst nur Konfiguration/Metadaten, KEINE Geschäftsdatensätze.

Ausgabe (gitignored):  odoo/report/processes.js  (window.ODOO_PROCESSES)
Aufruf:  python3 odoo/extract_processes.py
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

    def ex(model, method, *args, **kw):
        return models.execute_kw(db, uid, key, model, method, list(args), kw)

    def sread(model, domain=None, **kw):
        try:
            return ex(model, "search_read", domain or [], **kw)
        except Exception:
            return []

    try:
        PRESENT = {r["model"] for r in ex("ir.model", "search_read", [], fields=["model"])}
    except Exception:
        PRESENT = set()

    def has(m):
        return m in PRESENT

    def fields_of(model):
        try:
            return set(ex(model, "fields_get", [], attributes=["type"]).keys())
        except Exception:
            return set()

    def selection(model, field):
        try:
            fg = ex(model, "fields_get", [field], attributes=["selection"])
            return fg.get(field, {}).get("selection") or []
        except Exception:
            return []

    AREA = [
        ("crm", "CRM"), ("sale", "Vertrieb"), ("purchase", "Einkauf"),
        ("account", "Buchhaltung"), ("project", "Projekt"), ("hr", "Personal"),
        ("stock", "Lager"), ("mrp", "Fertigung"), ("mail", "Kommunikation"),
        ("website", "Website"), ("pos", "Kasse"), ("event", "Events"),
    ]

    def area_of(model):
        prefix = (model or "").split(".")[0]
        for k, label in AREA:
            if prefix == k:
                return label
        return "Sonstiges"

    def pick(model, wanted, order_field=None):
        avail = fields_of(model)
        flds = [f for f in wanted if f in avail]
        if "name" not in flds and "name" in avail:
            flds.insert(0, "name")
        kw = {"fields": flds} if flds else {}
        if order_field and order_field in avail:
            kw["order"] = order_field
        return sread(model, [], **kw)

    # ---- Pipelines / Stadien ----
    pipelines = []
    for model, label in [
        ("crm.stage", "CRM-Pipeline"),
        ("project.task.type", "Projekt-/Aufgaben-Stadien"),
        ("helpdesk.stage", "Helpdesk-Stufen"),
    ]:
        if not has(model):
            continue
        recs = pick(model, ["name", "sequence", "is_won", "fold"], order_field="sequence")
        if recs:
            pipelines.append({"model": model, "label": label, "area": area_of(model), "stages": recs})

    # ---- Dokument-Status (Selection 'state') ----
    doc_states = []
    for model, label in [
        ("sale.order", "Verkaufsauftrag"), ("purchase.order", "Einkaufsbestellung"),
        ("account.move", "Buchung / Rechnung"), ("account.payment", "Zahlung"),
        ("stock.picking", "Lieferung"), ("mrp.production", "Fertigungsauftrag"),
    ]:
        if not has(model):
            continue
        sel = selection(model, "state")
        if sel:
            doc_states.append({"model": model, "label": label, "area": area_of(model), "states": sel})

    # ---- Automatisierungsregeln ----
    autos = []
    if has("base.automation"):
        trig = dict(selection("base.automation", "trigger"))
        recs = pick("base.automation", ["name", "trigger", "active", "model_id"])
        mids = list({r["model_id"][0] for r in recs if r.get("model_id")})
        mmap = {}
        if mids:
            try:
                for m in ex("ir.model", "read", mids, fields=["model", "name"]):
                    mmap[m["id"]] = {"model": m["model"], "label": m["name"]}
            except Exception:
                pass
        for r in recs:
            mi = r.get("model_id")
            mm = mmap.get(mi[0]) if mi else None
            tech = mm["model"] if mm else ""
            autos.append({
                "name": r.get("name", ""),
                "active": r.get("active", True),
                "trigger": trig.get(r.get("trigger"), r.get("trigger") or ""),
                "model": tech,
                "model_label": mm["label"] if mm else (mi[1] if mi else ""),
                "area": area_of(tech),
            })

    # ---- Geplante Aktionen (Cron) ----
    crons = pick("ir.cron", ["name", "interval_number", "interval_type", "active", "nextcall"]) if has("ir.cron") else []

    # ---- Mail-Vorlagen (was wird automatisch gemailt) ----
    mail_templates = []
    if has("mail.template"):
        by = {}
        for r in pick("mail.template", ["name", "model"]):
            m = r.get("model") or "—"
            by.setdefault(m, []).append(r.get("name", ""))
        for m, names in sorted(by.items(), key=lambda x: -len(x[1])):
            mail_templates.append({"model": m, "area": area_of(m), "count": len(names), "examples": names[:6]})

    # ---- Prozessrelevante Konfiguration ----
    config = {}
    if has("account.journal"):
        config["journals"] = pick("account.journal", ["name", "type"], order_field="type")
    if has("account.payment.term"):
        config["payment_terms"] = [r.get("name", "") for r in pick("account.payment.term", ["name"])]
    if has("account.tax"):
        config["taxes_count"] = len(sread("account.tax", [], fields=["id"]))
    if has("crm.team"):
        config["crm_teams"] = [r.get("name", "") for r in pick("crm.team", ["name"])]
    if has("sale.order.template"):
        config["sale_templates"] = [r.get("name", "") for r in pick("sale.order.template", ["name"])]
    if has("account.fiscal.position"):
        config["fiscal_positions"] = [r.get("name", "") for r in pick("account.fiscal.position", ["name"])]

    data = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "server": {"version": version, "db": db, "url": url},
        "pipelines": pipelines,
        "doc_states": doc_states,
        "automations": autos,
        "crons": crons,
        "mail_templates": mail_templates,
        "config": config,
    }

    out = Path(os.environ.get("ODOO_OUT_DIR") or (HERE / "report"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "processes.js").write_text(
        "// Automatisch erzeugt von odoo/extract_processes.py - nicht manuell editieren.\n"
        "window.ODOO_PROCESSES = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    (out / "processes.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Prozess-Analyse geschrieben →", out / "processes.js")
    print(f"  Pipelines/Stadien     : {len(pipelines)}")
    print(f"  Dokument-Status        : {len(doc_states)}")
    print(f"  Automatisierungsregeln : {len(autos)}  (Cron: {len(crons)})")
    print(f"  Mail-Vorlagen-Modelle  : {len(mail_templates)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
