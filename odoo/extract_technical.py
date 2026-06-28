#!/usr/bin/env python3
"""Technischer Extraktor – erfasst das Customizing-Bild einer Odoo-Instanz.

Portabel (nur API, prüft Modelle/Felder dynamisch). Erfasst:
- Custom-Modelle (state=manual) inkl. Feldzahl
- Custom-Felder (state=manual): Modell, Name, Typ, related/stored, Hilfetext
- Studio-Fußabdruck (ir.model.data module=studio_customization), gruppiert
- Server-Aktionen: Gesamt + Aufschlüsselung nach Typ; Custom (Studio) gelistet
- Datensatzregeln (ir.rule): Modell, global/Gruppen, Domain  (sicherheitsrelevant)
- Sequenzen (ir.sequence)
- Benutzergruppen: Gesamt + Custom

Ausgabe (gitignored):  odoo/report/technical.js  (window.ODOO_TECH)
Aufruf:  python3 odoo/extract_technical.py
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

    def count(model, domain=None):
        try:
            return ex(model, "search_count", domain or [])
        except Exception:
            return None

    def fields_of(model):
        try:
            return set(ex(model, "fields_get", [], attributes=["type"]).keys())
        except Exception:
            return set()

    def pick(model, domain, wanted, order=None):
        avail = fields_of(model)
        flds = [f for f in wanted if f in avail]
        kw = {"fields": flds} if flds else {}
        if order and order in avail:
            kw["order"] = order
        return sread(model, domain, **kw)

    def resolve_models(ids):
        ids = [i for i in set(ids) if i]
        out = {}
        if ids:
            try:
                for m in ex("ir.model", "read", ids, fields=["model", "name"]):
                    out[m["id"]] = {"model": m["model"], "label": m["name"]}
            except Exception:
                pass
        return out

    def m2o(rec, field):
        v = rec.get(field)
        return v[0] if isinstance(v, (list, tuple)) and v else None

    # ---- Studio-Fußabdruck: was hat Studio angefasst? ----
    studio = {}            # model -> count
    studio_ids = {}        # target-model -> set(res_id)  (für Custom-Erkennung)
    for r in sread("ir.model.data", [["module", "=", "studio_customization"]],
                   fields=["model", "res_id", "name"]):
        m = r.get("model")
        studio[m] = studio.get(m, 0) + 1
        studio_ids.setdefault(m, set()).add(r.get("res_id"))

    def is_custom(target_model, res_id, present_in_data):
        # Custom, wenn von Studio angelegt ODER ohne XML-ID (rein in der UI erstellt)
        if res_id in studio_ids.get(target_model, set()):
            return True
        return res_id not in present_in_data

    def xmlid_res_ids(target_model):
        ids = set()
        for r in sread("ir.model.data", [["model", "=", target_model]], fields=["res_id"]):
            ids.add(r.get("res_id"))
        return ids

    # ---- Custom-Modelle ----
    custom_models = []
    for r in pick("ir.model", [["state", "=", "manual"]], ["model", "name"], order="model"):
        nflds = count("ir.model.fields", [["model", "=", r["model"]]])
        ncust = count("ir.model.fields", [["model", "=", r["model"]], ["state", "=", "manual"]])
        custom_models.append({"model": r.get("model"), "label": r.get("name"),
                              "fields": nflds, "custom_fields": ncust})

    # ---- Custom-Felder ----
    custom_fields = []
    for r in pick("ir.model.fields", [["state", "=", "manual"]],
                  ["model", "name", "field_description", "ttype", "related", "store", "required", "help"],
                  order="model"):
        custom_fields.append({
            "model": r.get("model"), "name": r.get("name"),
            "label": r.get("field_description"), "type": r.get("ttype"),
            "related": r.get("related") or "", "stored": bool(r.get("store")),
            "required": bool(r.get("required")), "help": (r.get("help") or "").strip(),
        })

    # ---- Server-Aktionen ----
    sa_recs = pick("ir.actions.server", [], ["name", "model_id", "state"])
    sa_models = resolve_models([m2o(r, "model_id") for r in sa_recs])
    sa_data_ids = xmlid_res_ids("ir.actions.server")
    by_type = {}
    server_actions_custom = []
    for r in sa_recs:
        st = r.get("state") or "?"
        by_type[st] = by_type.get(st, 0) + 1
        rid = r.get("id")
        if is_custom("ir.actions.server", rid, sa_data_ids):
            mm = sa_models.get(m2o(r, "model_id"))
            server_actions_custom.append({
                "name": r.get("name"), "state": st,
                "model": mm["model"] if mm else "",
            })
    server_actions = {"total": len(sa_recs), "by_type": by_type, "custom": server_actions_custom}

    # ---- Datensatzregeln (ir.rule) ----
    rule_recs = pick("ir.rule", [],
                     ["name", "model_id", "global", "domain_force", "active",
                      "perm_read", "perm_write", "perm_create", "perm_unlink"])
    rule_models = resolve_models([m2o(r, "model_id") for r in rule_recs])
    rule_data_ids = xmlid_res_ids("ir.rule")
    rules = []
    for r in rule_recs:
        mm = rule_models.get(m2o(r, "model_id"))
        dom = (r.get("domain_force") or "").strip()
        rules.append({
            "name": r.get("name"), "model": mm["model"] if mm else "",
            "global": bool(r.get("global")), "active": bool(r.get("active", True)),
            "domain": dom[:160],
            "perms": "".join([p for p, f in [("R", "perm_read"), ("W", "perm_write"),
                              ("C", "perm_create"), ("D", "perm_unlink")] if r.get(f)]),
            "custom": is_custom("ir.rule", r.get("id"), rule_data_ids),
        })

    # ---- Sequenzen ----
    sequences = pick("ir.sequence", [], ["name", "prefix", "padding", "number_next_actual"], order="name")

    # ---- Benutzergruppen ----
    groups_total = count("res.groups", [])
    grp_data_ids = xmlid_res_ids("res.groups")
    grp_recs = pick("res.groups", [], ["name", "full_name"])
    groups_custom = [(g.get("full_name") or g.get("name"))
                     for g in grp_recs if is_custom("res.groups", g.get("id"), grp_data_ids)]

    data = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "server": {"version": version, "db": db, "url": url},
        "studio_footprint": [{"model": k, "count": v} for k, v in sorted(studio.items(), key=lambda x: -x[1])],
        "custom_models": custom_models,
        "custom_fields": custom_fields,
        "server_actions": server_actions,
        "record_rules": rules,
        "sequences": sequences,
        "groups": {"total": groups_total, "custom": groups_custom},
    }

    out = HERE / "report"
    out.mkdir(exist_ok=True)
    (out / "technical.js").write_text(
        "// Automatisch erzeugt von odoo/extract_technical.py - nicht manuell editieren.\n"
        "window.ODOO_TECH = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    (out / "technical.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Technische Analyse geschrieben →", out / "technical.js")
    print(f"  Custom-Modelle   : {len(custom_models)}")
    print(f"  Custom-Felder    : {len(custom_fields)}")
    print(f"  Studio-Objekte   : {sum(s['count'] for s in data['studio_footprint'])}")
    print(f"  Server-Aktionen  : {server_actions['total']} (custom: {len(server_actions_custom)})")
    print(f"  Datensatzregeln  : {len(rules)} (custom: {sum(1 for r in rules if r['custom'])})")
    print(f"  Sequenzen        : {len(sequences)}  | Gruppen: {groups_total} (custom: {len(groups_custom)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
