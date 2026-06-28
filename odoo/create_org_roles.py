#!/usr/bin/env python3
"""Legt 'Organisationsrollen'-Gruppen an, die OOTB-Gruppen bündeln.

Ziel: einem Mitarbeiter nur EINE Organisationsrolle zuweisen, statt vieler
Einzelgruppen. Die Rollen werden LEER angelegt (kein Benutzer zugewiesen) –
sie gewähren also erst Zugriff, wenn man sie einem Benutzer zuweist.

Idempotent: bei erneutem Lauf werden vorhandene Rollen aktualisiert, nicht
dupliziert. Portabel (nur API). Rückgängig: die drei Gruppen + Privileg +
Kategorie 'Organisationsrollen' löschen.

Aufruf:  python3 odoo/create_org_roles.py
"""
import os
import sys
from pathlib import Path
import xmlrpc.client

HERE = Path(__file__).parent

PRIVILEGE = "Organisationsrollen"

ROLES = {
    "Vertriebsmitarbeiter": {
        "comment": "Organisationsrolle: operative Vertriebsarbeit (Verkauf + Kontakte).",
        "groups": ["Sales / User: All Documents", "Contact / Creation"],
    },
    "Projektleiter": {
        "comment": "Organisationsrolle: Projektleitung (Projekte verwalten + alle Zeiterfassungen).",
        "groups": ["Project / Administrator", "Timesheets / User: all timesheets"],
    },
    "HR": {
        "comment": "Organisationsrolle: Personalwesen (Mitarbeiter, Abwesenheiten, Spesen).",
        "groups": ["Employees / Officer: Manage all employees",
                   "Time Off / Officer: Manage all requests",
                   "Expenses / All Approver"],
    },
}


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
    uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, user, key, {})
    if not uid:
        print("Authentifizierung fehlgeschlagen.")
        return 2
    M = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def ex(model, method, *args, **kw):
        return M.execute_kw(db, uid, key, model, method, list(args), kw)

    def find_one(model, domain, fields=("id",)):
        r = ex(model, "search_read", domain, fields=list(fields), limit=1)
        return r[0] if r else None

    # --- Privileg "Organisationsrollen" für saubere Gruppierung (optional) ---
    priv_id = False
    existing_priv = find_one("res.groups.privilege", [["name", "=", PRIVILEGE]])
    if existing_priv:
        priv_id = existing_priv["id"]
    else:
        try:
            priv_id = ex("res.groups.privilege", "create", {"name": PRIVILEGE})
        except Exception as e:
            print("  Hinweis: Privileg nicht anlegbar (Rollen ohne Privileg):", str(e).splitlines()[-1][:90])
            priv_id = False
    print(f"Privileg '{PRIVILEGE}': {priv_id or 'ohne'}")

    # --- Rollen anlegen/aktualisieren ---
    for role, spec in ROLES.items():
        gids, missing = [], []
        for fn in spec["groups"]:
            g = find_one("res.groups", [["full_name", "=", fn]])
            (gids.append(g["id"]) if g else missing.append(fn))
        if missing:
            print(f"  ! {role}: nicht gefunden: {missing}")

        vals = {"name": role, "comment": spec["comment"], "implied_ids": [(6, 0, gids)]}
        if priv_id:
            vals["privilege_id"] = priv_id
        existing = find_one("res.groups", [["name", "=", role]])
        if existing:
            ex("res.groups", "write", [existing["id"]], vals)
            print(f"  ~ aktualisiert: {role} (id {existing['id']}) -> {len(gids)} OOTB-Gruppen")
        else:
            gid = ex("res.groups", "create", vals)
            print(f"  + angelegt:    {role} (id {gid}) -> {len(gids)} OOTB-Gruppen")

    print("\nFertig. Rollen sind LEER (kein Benutzer zugewiesen).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
