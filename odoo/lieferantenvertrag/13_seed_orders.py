#!/usr/bin/env python3
"""Legt je Rahmenvertrag zwei Bestellungen an, die darauf verweisen.

- partner_id = Lieferant des Vertrags
- x_studio_lieferantenvertrag_id = der Vertrag  (-> Automation traegt sie ein)
- eine Position mit Produkt/Menge/Preis (sichtbarer Betrag in der Liste)
- Markierung im Feld 'origin' (LV-DEMO ...) -> idempotent + leicht aufraeumbar

Zusaetzlich wird die Verknuepfung am Vertrag explizit gesetzt (falls die
Automation mal nicht greift). Mehrfach ausfuehrbar ohne Duplikate.
"""
import json
from pathlib import Path

from odoo_client import OdooClient

MODEL = "x_lieferantenvertrag"
ORDERS_PER_CONTRACT = 2
PRODUCTS = [166, 33, 235, 123, 182]   # kaufbare Beispielprodukte
PRICES = [250.0, 480.0, 1200.0, 95.0, 640.0]
QTYS = [1, 2, 3, 5, 10]


def main() -> int:
    c = OdooClient.from_env()
    c.connect()

    # uom-Feldname robust ermitteln
    pol = c.fields_get("purchase.order.line")
    uom_field = "product_uom" if "product_uom" in pol else (
        "product_uom_id" if "product_uom_id" in pol else None)

    prod_info = {p["id"]: p for p in c.read(
        "product.product", PRODUCTS, ["name", "uom_id"])}

    contracts = c.search_read(
        MODEL, [("x_studio_vertragstyp", "=", "rahmenvertrag")],
        fields=["id", "x_name", "x_studio_partner_id", "x_studio_vertragsnummer"],
        order="id")
    print(f"Rahmenverträge: {len(contracts)}")

    created, skipped = [], 0
    for ci, ct in enumerate(contracts):
        partner = ct["x_studio_partner_id"]
        if not partner:
            print(f"  WARN: {ct['x_name']} ohne Lieferant – übersprungen")
            continue
        vnr = ct["x_studio_vertragsnummer"] or f"ID{ct['id']}"
        new_ids = []
        for n in range(1, ORDERS_PER_CONTRACT + 1):
            origin = f"LV-DEMO {vnr} #{n}"
            if c.find_one("purchase.order", [("origin", "=", origin)], fields=["id"]):
                skipped += 1
                continue
            pid = PRODUCTS[(ci + n) % len(PRODUCTS)]
            line = {
                "product_id": pid,
                "name": prod_info[pid]["name"],
                "product_qty": QTYS[(ci + n) % len(QTYS)],
                "price_unit": PRICES[(ci + n) % len(PRICES)],
            }
            if uom_field:
                line[uom_field] = prod_info[pid]["uom_id"][0]
            po_id = c.create("purchase.order", {
                "partner_id": partner[0],
                "x_studio_lieferantenvertrag_id": ct["id"],
                "origin": origin,
                "order_line": [(0, 0, line)],
            })
            new_ids.append(po_id)
            created.append(po_id)
        # Verknuepfung am Vertrag sicherstellen (idempotent)
        if new_ids:
            c.write(MODEL, [ct["id"]],
                    {"x_studio_orders_ids": [(4, pid) for pid in new_ids]})
        if (ci + 1) % 5 == 0 or ci == len(contracts) - 1:
            print(f"  [{ci+1:>2}/{len(contracts)}] verarbeitet")

    Path(__file__).parent.joinpath("seed_order_ids.json").write_text(
        json.dumps(created))
    print(f"\nBestellungen angelegt: {len(created)} | übersprungen: {skipped}")

    # Kontrolle
    sample = c.read(MODEL, [contracts[0]["id"]],
                    ["x_name", "x_studio_orders_ids"])[0]
    print(f"Beispiel '{sample['x_name']}': "
          f"{len(sample['x_studio_orders_ids'])} Bestellung(en) im Tab")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
