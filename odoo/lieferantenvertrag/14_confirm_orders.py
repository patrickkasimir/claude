#!/usr/bin/env python3
"""Bestätigt die Demo-Bestellungen (LV-DEMO ...): Entwurf/RFQ -> Bestellung.

Hintergrund: Das Menü 'Einkauf > Bestellungen' zeigt nur state='purchase'.
Entwürfe liegen unter 'Angebotsanfragen'. button_confirm macht echte
Bestellungen daraus. Idempotent (nur draft/sent werden bestätigt).
"""
from collections import Counter

from odoo_client import OdooClient


def main() -> int:
    c = OdooClient.from_env()
    c.connect()
    todo = c.search("purchase.order",
                    [("origin", "like", "LV-DEMO%"),
                     ("state", "in", ["draft", "sent"])])
    print(f"Zu bestätigen: {len(todo)}")
    if todo:
        # in Bloecken bestaetigen (robuster als alle auf einmal)
        for i in range(0, len(todo), 20):
            c.execute("purchase.order", "button_confirm", todo[i:i + 20])
    states = Counter(p["state"] for p in c.search_read(
        "purchase.order", [("origin", "like", "LV-DEMO%")], fields=["state"]))
    print("Status danach:", dict(states))
    print("Fertig ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
