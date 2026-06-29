#!/usr/bin/env python3
"""Entfernt die 100 Demo-Verträge aus 11_seed_contracts.py.

Erkennung über die Vertragsnummer 'LV-2026-%'. Lässt [TEST]-Daten und das
Modell/die Struktur unberührt. Mehrfach ausführbar.
"""
from odoo_client import OdooClient

MODEL = "x_lieferantenvertrag"


def main() -> int:
    c = OdooClient.from_env()
    c.connect()

    # Demo-Bestellungen (je Rahmenvertrag) zuerst
    pos = c.search("purchase.order", [("origin", "like", "LV-DEMO%")])
    if pos:
        c.unlink("purchase.order", pos)
    print(f"Demo-Bestellungen gelöscht: {len(pos)}")

    ids = c.search(MODEL, [("x_studio_vertragsnummer", "like", "LV-2026-%")])
    if ids:
        # Einzelvereinbarungen zuerst lösen (parent-Referenz), dann alle löschen
        c.unlink(MODEL, ids)
    print(f"Demo-Verträge gelöscht: {len(ids)}")
    print(f"Verbleibende Verträge im Modell: {c.search_count(MODEL, [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
