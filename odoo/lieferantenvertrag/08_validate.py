#!/usr/bin/env python3
"""Schritt 7 — Validierung mit Testdaten.

Legt idempotent an (Marker '[TEST]' / partner_ref '[TEST-LV]'):
- 1 Test-Lieferant
- 1 Vertrag je Vertragstyp, mit mehrsprachigen Notizen (de_DE/en_US)
- 1 Bestellung MIT Vertragsbezug (Rahmenvertrag)  -> testet Automation 1
- 1 Bestellung OHNE Vertragsbezug                 -> testet Optionalitaet

Prueft danach: Automation-Verknuepfung + Rueck-Lesung der Notizen je Sprache.
"""
from datetime import date

from odoo_client import OdooClient

MODEL = "x_lieferantenvertrag"
VENDOR_NAME = "[TEST] Lieferantenvertrag-Lieferant"
PO_MARKER = "[TEST-LV]"

TYPES = [
    ("avv", "[TEST] AVV Musterlieferant"),
    ("nda", "[TEST] NDA Musterlieferant"),
    ("rahmenvertrag", "[TEST] Rahmenvertrag Musterlieferant"),
    ("einzelvereinbarung", "[TEST] Einzelvereinbarung Musterlieferant"),
]
NOTES = {
    "de_DE": "Dies ist eine mehrsprachige Testnotiz (Deutsch).",
    "en_US": "This is a multilingual test note (English).",
}


def main() -> int:
    c = OdooClient.from_env()
    c.connect()

    # 1) Test-Lieferant
    vendor_id, created = c.ensure("res.partner", [("name", "=", VENDOR_NAME)],
                                  {"name": VENDOR_NAME, "supplier_rank": 1,
                                   "is_company": True})
    print(f"Test-Lieferant {'angelegt' if created else 'vorhanden'} (id={vendor_id})")

    # 2) Vertraege je Typ
    print("\n=== Vertraege ===")
    contract_ids = {}
    for vtyp, name in TYPES:
        existing = c.find_one(MODEL, [("x_name", "=", name)], fields=["id"])
        if existing:
            cid = existing["id"]
            print(f"  {vtyp:<18} vorhanden (id={cid})")
        else:
            cid = c.create(MODEL, {
                "x_name": name,
                "x_studio_partner_id": vendor_id,
                "x_studio_vertragstyp": vtyp,
                "x_studio_status": "aktiv",
                "x_studio_vertragsnummer": f"LV-{vtyp.upper()}-2026",
                "x_studio_start_date": date(2026, 1, 1).isoformat(),
                "x_studio_end_date": date(2026, 12, 31).isoformat(),
                "x_studio_responsible_id": c.uid,
                "x_studio_notes": NOTES["de_DE"],
            })
            print(f"  {vtyp:<18} angelegt (id={cid})")
        contract_ids[vtyp] = cid
        # Notizen je Sprache schreiben (immer mit explizitem lang-Context)
        for code, text in NOTES.items():
            c.write(MODEL, [cid], {"x_studio_notes": text}, context={"lang": code})

    # Einzelvereinbarung an Rahmenvertrag haengen
    c.write(MODEL, [contract_ids["einzelvereinbarung"]],
            {"x_studio_parent_contract_id": contract_ids["rahmenvertrag"]})

    # 3) Bestellung MIT Vertragsbezug (Rahmenvertrag) -> Automation 1
    print("\n=== Bestellungen ===")
    po_linked = c.find_one("purchase.order",
                           [("partner_ref", "=", PO_MARKER + " mit Vertrag")],
                           fields=["id"])
    if not po_linked:
        po_linked_id = c.create("purchase.order", {
            "partner_id": vendor_id,
            "partner_ref": PO_MARKER + " mit Vertrag",
            "x_studio_lieferantenvertrag_id": contract_ids["rahmenvertrag"],
        })
        print(f"  PO mit Vertrag angelegt (id={po_linked_id})")
    else:
        po_linked_id = po_linked["id"]
        print(f"  PO mit Vertrag vorhanden (id={po_linked_id})")

    # 4) Bestellung OHNE Vertragsbezug
    po_plain = c.find_one("purchase.order",
                          [("partner_ref", "=", PO_MARKER + " ohne Vertrag")],
                          fields=["id"])
    if not po_plain:
        po_plain_id = c.create("purchase.order", {
            "partner_id": vendor_id,
            "partner_ref": PO_MARKER + " ohne Vertrag",
        })
        print(f"  PO ohne Vertrag angelegt (id={po_plain_id})")
    else:
        po_plain_id = po_plain["id"]
        print(f"  PO ohne Vertrag vorhanden (id={po_plain_id})")

    # ---- Pruefungen ----
    print("\n=== Pruefung: Automation 1 (PO am Rahmenvertrag) ===")
    rv = c.read(MODEL, [contract_ids["rahmenvertrag"]],
                ["x_studio_orders_ids"])[0]
    linked = rv["x_studio_orders_ids"]
    ok_auto = po_linked_id in linked
    print(f"  orders_ids am Rahmenvertrag: {linked}")
    print(f"  PO {po_linked_id} verknuepft: {'JA ✓' if ok_auto else 'NEIN ✗'}")

    print("\n=== Pruefung: Mehrsprachige Notizen ===")
    ok_lang = True
    for code, expected in NOTES.items():
        got = c.read(MODEL, [contract_ids["avv"]], ["x_studio_notes"],
                     context={"lang": code})[0]["x_studio_notes"]
        match = got == expected
        ok_lang = ok_lang and match
        print(f"  [{code}] {got!r} {'✓' if match else '✗'}")

    print("\n=== Pruefung: PO ohne Vertrag erlaubt ===")
    plain = c.read("purchase.order", [po_plain_id],
                   ["x_studio_lieferantenvertrag_id", "state"])[0]
    ok_optional = not plain["x_studio_lieferantenvertrag_id"]
    print(f"  PO ohne Vertrag: link={plain['x_studio_lieferantenvertrag_id']} "
          f"state={plain['state']} {'✓' if ok_optional else '✗'}")

    print("\n" + ("ALLE PRUEFUNGEN BESTANDEN ✓" if (ok_auto and ok_lang and ok_optional)
                  else "ACHTUNG: mindestens eine Pruefung fehlgeschlagen"))
    return 0 if (ok_auto and ok_lang and ok_optional) else 1


if __name__ == "__main__":
    raise SystemExit(main())
