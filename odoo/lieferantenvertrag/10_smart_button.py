#!/usr/bin/env python3
"""Schritt 6b — Smart-Button 'Verträge' auf dem Lieferanten (res.partner).

Wie in Odoo Studio: ein manuelles Computed-Field (Anzahl) + Stat-Button, der
gefiltert die Verträge dieses Lieferanten öffnet.

- x_studio_contract_count: berechnetes Integer (len der one2many), nicht gespeichert
- gefilterte Action (Domain ueber active_id)
- Stat-Button in der button_box des Partnerformulars (Tab bleibt erhalten)

Idempotent.
"""
from odoo_client import OdooClient

MODEL = "x_lieferantenvertrag"
PARTNER_FORM_XMLID = "base.view_partner_form"   # zur Laufzeit per c.ref
INHERITED_VIEW_NAME = "res.partner.form.lieferantenvertraege"

COMPUTE = (
    "for record in self:\n"
    "    record['x_studio_contract_count'] = len(record.x_studio_contract_ids)\n"
)

COUNT_LABEL = {"de_DE": "Anzahl Verträge", "en_US": "Number of Contracts"}

ARCH_TPL = """<data>
  <xpath expr="//div[@name='button_box']" position="inside">
    <button class="oe_stat_button" type="action" name="__ACTION__"
            icon="fa-file-text-o" context="{'default_x_studio_partner_id': id}">
      <field name="x_studio_contract_count" widget="statinfo" string="Verträge"/>
    </button>
  </xpath>
  <xpath expr="//notebook" position="inside">
    <page string="Lieferantenverträge" name="x_lieferantenvertraege">
      <field name="x_studio_contract_ids" context="{'default_x_studio_partner_id': id}">
        <list>
          <field name="x_name" string="Bezeichnung"/>
          <field name="x_studio_vertragstyp"/>
          <field name="x_studio_status" widget="badge"/>
          <field name="x_studio_start_date"/>
          <field name="x_studio_end_date"/>
        </list>
      </field>
    </page>
  </xpath>
</data>"""


def main() -> int:
    c = OdooClient.from_env()
    c.connect()
    PARTNER_FORM_VIEW_ID = c.ref(PARTNER_FORM_XMLID)
    langs = [l["code"] for l in
             c.search_read("res.lang", [("active", "=", True)], fields=["code"])]

    # 1) Computed-Field
    pm = c.find_one("ir.model", [("model", "=", "res.partner")], fields=["id"])["id"]
    f = c.find_one("ir.model.fields",
                   [("model", "=", "res.partner"),
                    ("name", "=", "x_studio_contract_count")], fields=["id"])
    if f:
        fid = f["id"]
        c.write("ir.model.fields", [fid],
                {"compute": COMPUTE, "depends": "x_studio_contract_ids",
                 "store": False})
        print(f"Computed-Field vorhanden/aktualisiert (id={fid}).")
    else:
        fid = c.create("ir.model.fields", {
            "name": "x_studio_contract_count", "model_id": pm, "ttype": "integer",
            "field_description": COUNT_LABEL["de_DE"], "store": False,
            "depends": "x_studio_contract_ids", "compute": COMPUTE,
        })
        print(f"Computed-Field angelegt (id={fid}).")
    for code in langs:
        c.write("ir.model.fields", [fid],
                {"field_description": COUNT_LABEL.get(code, COUNT_LABEL["de_DE"])},
                context={"lang": code})

    # 2) Gefilterte Action (Verträge dieses Lieferanten)
    act = c.find_one("ir.actions.act_window",
                     [("res_model", "=", MODEL),
                      ("name", "=", "Verträge des Lieferanten")], fields=["id"])
    if act:
        action_id = act["id"]
        c.write("ir.actions.act_window", [action_id], {
            "domain": "[('x_studio_partner_id', '=', active_id)]",
            "context": "{'default_x_studio_partner_id': active_id}",
        })
        print(f"Gefilterte Action vorhanden/aktualisiert (id={action_id}).")
    else:
        action_id = c.create("ir.actions.act_window", {
            "name": "Verträge des Lieferanten",
            "res_model": MODEL,
            "view_mode": "list,form",
            "domain": "[('x_studio_partner_id', '=', active_id)]",
            "context": "{'default_x_studio_partner_id': active_id}",
        })
        print(f"Gefilterte Action angelegt (id={action_id}).")

    # 3) Inherited View aktualisieren (Smart-Button + Tab)
    arch = ARCH_TPL.replace("__ACTION__", str(action_id))
    v = c.find_one("ir.ui.view", [("name", "=", INHERITED_VIEW_NAME)], fields=["id"])
    if v:
        c.write("ir.ui.view", [v["id"]], {"arch": arch})
        print(f"Partner-View aktualisiert (id={v['id']}).")
    else:
        vid = c.create("ir.ui.view", {
            "name": INHERITED_VIEW_NAME, "model": "res.partner", "type": "form",
            "inherit_id": PARTNER_FORM_VIEW_ID, "arch": arch,
        })
        print(f"Partner-View angelegt (id={vid}).")

    # 4) Kontrolle: rendert das Partnerformular + Button-Wert
    c.execute("res.partner", "get_view", view_type="form")
    vendor = c.find_one("res.partner",
                        [("name", "=", "[TEST] Lieferantenvertrag-Lieferant")],
                        fields=["id"])
    if vendor:
        cnt = c.read("res.partner", [vendor["id"]],
                     ["x_studio_contract_count"])[0]["x_studio_contract_count"]
        print(f"Kontrolle: Test-Lieferant zeigt {cnt} Verträge im Button.")
    print("\nSmart-Button abgeschlossen ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
