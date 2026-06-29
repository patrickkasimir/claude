#!/usr/bin/env python3
"""Entfernt NUR die Testdaten aus Schritt 7 (Modell/Felder/Views bleiben!).

Loescht in sicherer Reihenfolge: Test-Bestellungen -> Test-Vertraege ->
Test-Lieferant. Mehrfach ausfuehrbar.
"""
from odoo_client import OdooClient

MODEL = "x_lieferantenvertrag"
VENDOR_NAME = "[TEST] Lieferantenvertrag-Lieferant"
PO_MARKER = "[TEST-LV]"


def main() -> int:
    c = OdooClient.from_env()
    c.connect()

    pos = c.search("purchase.order", [("partner_ref", "like", PO_MARKER + "%")])
    if pos:
        c.unlink("purchase.order", pos)
    print(f"Test-Bestellungen geloescht: {len(pos)}")

    contracts = c.search(MODEL, [("x_name", "like", "[TEST]%")])
    if contracts:
        c.unlink(MODEL, contracts)
    print(f"Test-Vertraege geloescht: {len(contracts)}")

    vendor = c.search("res.partner", [("name", "=", VENDOR_NAME)])
    if vendor:
        try:
            c.unlink("res.partner", vendor)
            print(f"Test-Lieferant geloescht: {len(vendor)}")
        except Exception as e:  # noqa: BLE001
            print("Test-Lieferant NICHT geloescht (noch referenziert):",
                  str(e).splitlines()[0][:120])
    else:
        print("Test-Lieferant: nichts zu loeschen")

    print("\nCleanup abgeschlossen ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
