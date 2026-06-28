#!/usr/bin/env python3
"""Modul-Abhängigkeiten – App-zu-App-Abhängigkeitsgraph.

Portabel (nur API). Liest die Abhängigkeiten der installierten Module und
reduziert sie auf App-Ebene (transitive Reduktion): zeigt, welche App direkt
auf welche andere App aufbaut. Nützlich für Kopplung & Migrationsreihenfolge.

Ausgabe (gitignored):  odoo/report/modules.js  (window.ODOO_MODULES)
Aufruf:  python3 odoo/extract_modules.py
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
    db, user, key = os.environ.get("ODOO_DB", ""), os.environ.get("ODOO_USER", ""), os.environ.get("ODOO_API_KEY", "")
    if not all([url, db, user, key]):
        print("Zugangsdaten fehlen (odoo/.env).")
        return 1
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    version = common.version().get("server_version")
    uid = common.authenticate(db, user, key, {})
    if not uid:
        print("Authentifizierung fehlgeschlagen.")
        return 2
    M = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def ex(model, method, *args, **kw):
        return M.execute_kw(db, uid, key, model, method, list(args), kw)

    # installierte Module
    mods = ex("ir.module.module", "search_read", [["state", "=", "installed"]],
              fields=["name", "shortdesc", "application"])
    installed = {m["name"] for m in mods}
    id2name = {m["id"]: m["name"] for m in mods}
    apps = {m["name"] for m in mods if m.get("application")}
    label = {m["name"]: (m.get("shortdesc") or m["name"]) for m in mods}

    # direkte Abhängigkeiten (nur zwischen installierten Modulen)
    deps = {n: set() for n in installed}
    for d in ex("ir.module.module.dependency", "search_read", [], fields=["module_id", "name"]):
        mid = d.get("module_id")
        src = id2name.get(mid[0]) if mid else None
        dep = d.get("name")
        if src in installed and dep in installed:
            deps[src].add(dep)

    # transitive Hülle (über alle installierten Module)
    from functools import lru_cache
    import sys as _sys
    _sys.setrecursionlimit(10000)

    @lru_cache(maxsize=None)
    def closure(mod):
        out = set()
        for d in deps.get(mod, ()):  # direkte
            if d not in out:
                out.add(d)
                out |= closure(d)
        return out

    # App-Abhängigkeiten = Apps in der Hülle; transitive Reduktion auf App-Ebene
    app_dep = {}
    for a in apps:
        cl_apps = {x for x in closure(a) if x in apps}
        reduced = set()
        for b in cl_apps:
            # b ist direkt, wenn kein anderer App-Dep c von a das b ebenfalls enthält
            if not any(c != b and b in (closure(c) & apps) for c in cl_apps):
                reduced.add(b)
        app_dep[a] = sorted(reduced, key=lambda x: label.get(x, x).lower())

    apps_out = sorted(({"name": a, "label": label.get(a, a)} for a in apps),
                      key=lambda x: x["label"].lower())

    data = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "server": {"version": version, "db": db, "url": url},
        "apps": apps_out,
        "deps": app_dep,  # app -> [direkte App-Abhängigkeiten]
    }

    out = HERE / "report"
    out.mkdir(exist_ok=True)
    (out / "modules.js").write_text(
        "// Automatisch erzeugt von odoo/extract_modules.py - nicht manuell editieren.\n"
        "window.ODOO_MODULES = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8")
    (out / "modules.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    edges = sum(len(v) for v in app_dep.values())
    print("Modul-Abhängigkeiten geschrieben →", out / "modules.js")
    print(f"  Apps: {len(apps)} | App-zu-App-Kanten (reduziert): {edges}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
