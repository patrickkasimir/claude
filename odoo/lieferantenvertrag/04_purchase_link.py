#!/usr/bin/env python3
"""Schritt 3 — Verknuepfung zum Einkauf.

Legt auf purchase.order das Feld x_studio_lieferantenvertrag_id an
(many2one -> x_lieferantenvertrag, NICHT required) UND fuegt es per vererbter
View ins Bestellformular ein – mit partnerabhaengigem Domain-Filter
(nur Vertraege des Lieferanten der Bestellung).

Idempotent.
"""
from odoo_client import OdooClient

CONTRACT_MODEL = "x_lieferantenvertrag"
FIELD_NAME = "x_studio_lieferantenvertrag_id"
PO_FORM_VIEW_ID = 3128            # purchase.purchase_order_form
INHERITED_VIEW_NAME = "purchase.order.form.lieferantenvertrag"

FORM_PATCH = """<data>
  <xpath expr="//field[@name='partner_ref']" position="after">
    <field name="x_studio_lieferantenvertrag_id"
           domain="[('x_studio_partner_id', '=', partner_id)]"
           context="{'default_x_studio_partner_id': partner_id}"
           options="{'no_create': True}"/>
  </xpath>
</data>"""


def main() -> int:
    c = OdooClient.from_env()
    c.connect()

    po = c.find_one("ir.model", [("model", "=", "purchase.order")], fields=["id"])
    if not po:
        raise SystemExit("purchase.order nicht gefunden – Einkaufsmodul fehlt?")

    existing = c.find_one(
        "ir.model.fields",
        [("model", "=", "purchase.order"), ("name", "=", FIELD_NAME)],
        fields=["id"],
    )
    if existing:
        print(f"Feld {FIELD_NAME} existiert bereits (id={existing['id']}).")
    else:
        fid = c.create("ir.model.fields", {
            "name": FIELD_NAME,
            "model_id": po["id"],
            "field_description": "Lieferantenvertrag",
            "ttype": "many2one",
            "relation": CONTRACT_MODEL,
            "required": False,
            "on_delete": "set null",
        })
        print(f"Feld {FIELD_NAME} auf purchase.order angelegt (id={fid}).")

    # Feld ins Bestellformular einbauen (sonst in der UI unsichtbar!)
    v = c.find_one("ir.ui.view", [("name", "=", INHERITED_VIEW_NAME)], fields=["id"])
    if v:
        c.write("ir.ui.view", [v["id"]], {"arch": FORM_PATCH})
        print(f"Bestellformular-Patch aktualisiert (id={v['id']}).")
    else:
        vid = c.create("ir.ui.view", {
            "name": INHERITED_VIEW_NAME,
            "model": "purchase.order",
            "type": "form",
            "inherit_id": PO_FORM_VIEW_ID,
            "arch": FORM_PATCH,
        })
        print(f"Bestellformular-Patch angelegt (id={vid}).")

    print("Verknuepfung zum Einkauf abgeschlossen ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
