#!/usr/bin/env python3
"""Schritt 1 — Vorbereitung & Discovery.

- Verbindung/Version
- Aktive Sprachen (einzige Quelle für 'alle installierten Sprachen')
- Ist das Einkaufsmodul (purchase.order) vorhanden?
- Vorhandene x_-Felder auf purchase.order und res.partner (Kollisionscheck)
- Existiert das Zielmodell x_lieferantenvertrag schon? (für Re-Runs)
"""
from odoo_client import OdooClient


def main() -> int:
    c = OdooClient.from_env()
    c.connect()
    print("=== Verbindung ===")
    print("Version:", c.version.get("server_version"))
    print("UID:", c.uid)

    print("\n=== Aktive Sprachen (res.lang) ===")
    langs = c.search_read("res.lang", [("active", "=", True)],
                          fields=["code", "name"], order="code")
    for l in langs:
        print(f"  {l['code']:<8} {l['name']}")
    print(f"  → {len(langs)} aktive Sprache(n)")

    print("\n=== Modell-Check ===")
    for model in ("purchase.order", "res.partner", "res.users",
                  "base.automation", "ir.actions.server"):
        m = c.find_one("ir.model", [("model", "=", model)], fields=["id", "name"])
        print(f"  {model:<22} {'vorhanden' if m else 'FEHLT'}")

    # Zielmodell?
    target = c.find_one("ir.model", [("model", "=", "x_lieferantenvertrag")],
                        fields=["id", "name"])
    print(f"  {'x_lieferantenvertrag':<22} "
          f"{'existiert bereits' if target else 'noch nicht angelegt'}")

    print("\n=== Vorhandene x_-Felder (Kollisionscheck) ===")
    for model in ("purchase.order", "res.partner"):
        fields = c.search_read(
            "ir.model.fields",
            [("model", "=", model), ("name", "like", "x_%")],
            fields=["name", "ttype", "field_description"], order="name",
        )
        print(f"  {model}: {len(fields)} x_-Feld(er)")
        for f in fields:
            print(f"      {f['name']:<35} {f['ttype']:<12} {f['field_description']}")

    print("\nDiscovery OK ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
