#!/usr/bin/env python3
"""Sicherheits-Extraktor – Benutzer, Gruppen, Rechte, Datensatzregeln.

Portabel (nur API). Liefert u. a. die Gruppen samt Kategorie (App-Bezug)
und Vererbung (implied_ids) für eine grafische Tree-Darstellung sowie
Kennzahlen/Funde für den Sicherheitscheck. Nur Metadaten, keine Inhalte.

Ausgabe (gitignored):  odoo/report/security.js  (window.ODOO_SECURITY)
Aufruf:  python3 odoo/extract_security.py
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

    def group_id(xmlname):
        r = sread("ir.model.data", [["module", "=", "base"], ["name", "=", xmlname], ["model", "=", "res.groups"]], fields=["res_id"])
        return r[0]["res_id"] if r else None

    # ---- Privilegien -> App-Kategorie (Odoo 19: category_id wanderte in res.groups.privilege) ----
    priv_map = {}
    for p in sread("res.groups.privilege", [], fields=["name", "category_id"]):
        cat = p.get("category_id")
        priv_map[p["id"]] = {"name": p.get("name"), "category": cat[1] if cat else (p.get("name") or "Ohne Kategorie")}

    # ---- OOTB vs. Custom: definierendes Modul je Gruppe (via XML-ID) ----
    grp_modules = {}
    for r in sread("ir.model.data", [["model", "=", "res.groups"]], fields=["res_id", "module"]):
        grp_modules[r["res_id"]] = r.get("module")
    STUDIO_MODULES = ("studio_customization", "__custom__", "__export__")

    # ---- Gruppen (für Tree + Analyse) ----
    grp_recs = pick("res.groups", [], ["name", "full_name", "privilege_id", "implied_ids", "comment", "user_ids", "all_user_ids"], order="id")
    id2name = {g["id"]: (g.get("full_name") or g.get("name")) for g in grp_recs}
    groups = []
    for g in grp_recs:
        pv = g.get("privilege_id")
        pinfo = priv_map.get(pv[0]) if pv else None
        mod = grp_modules.get(g["id"])
        custom = (mod is None) or (mod in STUDIO_MODULES)
        groups.append({
            "id": g["id"],
            "name": g.get("name"),
            "full_name": g.get("full_name") or g.get("name"),
            "privilege": pinfo["name"] if pinfo else (pv[1] if pv else ""),
            "category": pinfo["category"] if pinfo else "Technisch / ohne Privileg",
            "implies": [id2name.get(i, str(i)) for i in (g.get("implied_ids") or [])],
            "users": len(g.get("user_ids") or []),
            "users_effective": len(g.get("all_user_ids") or []),
            "module": mod or "",
            "custom": custom,
        })

    # ---- Privilegierte Benutzer ----
    def members(xmlname):
        gid = group_id(xmlname)
        if not gid:
            return []
        rec = sread("res.groups", [["id", "=", gid]], fields=["all_user_ids"])
        ids = rec[0]["all_user_ids"] if rec else []
        if not ids:
            return []
        return [f"{u.get('name')} ({u.get('login')})" for u in sread("res.users", [["id", "in", ids]], fields=["name", "login"])]

    privileged = {
        "Einstellungen / Administration (group_system)": members("group_system"),
        "Administration: Zugriffsrechte (group_erp_manager)": members("group_erp_manager"),
    }

    # ---- Benutzer-Kennzahlen ----
    users = {
        "internal_active": count("res.users", [["share", "=", False], ["active", "=", True]]),
        "internal_inactive": count("res.users", [["share", "=", False], ["active", "=", False]]),
        "portal_external": count("res.users", [["share", "=", True], ["active", "=", True]]),
    }
    try:
        users["with_2fa"] = count("res.users", [["share", "=", False], ["active", "=", True], ["totp_enabled", "=", True]])
    except Exception:
        users["with_2fa"] = None

    # ---- Rechte & Regeln ----
    access_total = count("ir.model.access", [])
    rule_global = count("ir.rule", [["global", "=", True]])
    rule_total = count("ir.rule", [])

    # globale Regeln mit „alle Datensätze"-Domain
    broad = []
    for r in pick("ir.rule", [["global", "=", True]], ["name", "model_id", "domain_force"]):
        dom = (r.get("domain_force") or "").replace(" ", "")
        if dom in ("", "[]", "[(1,'=',1)]", '[(1,"=",1)]'):
            mid = r.get("model_id")
            broad.append({"name": r.get("name"), "model": mid[1] if mid else ""})

    # Custom-Modelle ohne Zugriffsregel
    custom_models = [m["model"] for m in sread("ir.model", [["state", "=", "manual"]], fields=["model"])]
    models_without_access = []
    for m in custom_models:
        n = count("ir.model.access", [["model_id.model", "=", m]])
        if n == 0:
            models_without_access.append(m)

    data = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "server": {"version": version, "db": db, "url": url},
        "groups": groups,
        "privileged": privileged,
        "users": users,
        "access_total": access_total,
        "rules": {"total": rule_total, "global": rule_global, "broad": broad},
        "models_without_access": models_without_access,
    }

    out = Path(os.environ.get("ODOO_OUT_DIR") or (HERE / "report"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "security.js").write_text(
        "// Automatisch erzeugt von odoo/extract_security.py - nicht manuell editieren.\n"
        "window.ODOO_SECURITY = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    (out / "security.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    cats = len({g["category"] for g in groups})
    print("Sicherheits-Analyse geschrieben →", out / "security.js")
    print(f"  Gruppen          : {len(groups)} in {cats} Kategorien")
    print(f"  Privilegiert     : " + ", ".join(f"{k.split(' (')[0]}={len(v)}" for k, v in privileged.items()))
    print(f"  Benutzer         : intern {users['internal_active']}, portal {users['portal_external']}, 2FA {users['with_2fa']}")
    print(f"  Zugriffsrechte   : {access_total} | Regeln {rule_total} (global {rule_global}, broad {len(broad)})")
    print(f"  Custom o. Rechte : {len(models_without_access)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
