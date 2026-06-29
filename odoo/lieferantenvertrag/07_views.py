#!/usr/bin/env python3
"""Schritt 6 — Views, Menue, Action, Partner-Tab.

- inverse one2many x_studio_contract_ids auf res.partner
- List-/Form-/Search-View fuer x_lieferantenvertrag
  (Statusbar, Chatter, Bestellungen-Tab nur bei Rahmen-/Einzelvereinbarung)
- ir.actions.act_window + Menue unter Einkauf
- Inherited res.partner-Form: Tab 'Lieferantenverträge'

Idempotent (Suche ueber Namen).
"""
from odoo_client import OdooClient

MODEL = "x_lieferantenvertrag"
PARTNER_FORM_VIEW_ID = 126          # base.view_partner_form
PURCHASE_ROOT_MENU_ID = 645         # purchase.menu_purchase_root

LIST_ARCH = """<list>
  <field name="x_name" string="Bezeichnung"/>
  <field name="x_studio_vertragsnummer"/>
  <field name="x_studio_partner_id"/>
  <field name="x_studio_vertragstyp"/>
  <field name="x_studio_status" widget="badge"
         decoration-success="x_studio_status == 'aktiv'"
         decoration-warning="x_studio_status == 'laeuft_aus'"
         decoration-muted="x_studio_status == 'beendet'"/>
  <field name="x_studio_start_date"/>
  <field name="x_studio_end_date"/>
  <field name="x_studio_responsible_id" widget="many2one_avatar_user"/>
</list>"""

FORM_ARCH = """<form>
  <header>
    <field name="x_studio_status" widget="statusbar" options="{'clickable': '1'}"/>
  </header>
  <sheet>
    <div class="oe_title">
      <label for="x_name"/>
      <h1><field name="x_name" placeholder="z. B. AVV Musterlieferant 2026"/></h1>
    </div>
    <group>
      <group>
        <field name="x_studio_partner_id"/>
        <field name="x_studio_vertragstyp"/>
        <field name="x_studio_parent_contract_id"
               invisible="x_studio_vertragstyp != 'einzelvereinbarung'"
               domain="[('x_studio_vertragstyp', '=', 'rahmenvertrag'),
                        ('x_studio_partner_id', '=', x_studio_partner_id)]"/>
        <field name="x_studio_vertragsnummer"/>
        <field name="x_studio_responsible_id"/>
      </group>
      <group>
        <field name="x_studio_start_date"/>
        <field name="x_studio_end_date"/>
        <field name="x_studio_auto_renew"/>
        <field name="x_studio_notice_days"/>
      </group>
    </group>
    <separator string="Vertragsdokument (PDF)"/>
    <field name="x_studio_vertragsdokument" widget="pdf_viewer"
           filename="x_studio_vertragsdokument_filename" nolabel="1"/>
    <field name="x_studio_vertragsdokument_filename" invisible="1"/>
    <notebook>
      <page string="Bestellungen" name="orders"
            invisible="x_studio_vertragstyp not in ('rahmenvertrag', 'einzelvereinbarung')">
        <field name="x_studio_orders_ids">
          <list>
            <field name="name"/>
            <field name="partner_id"/>
            <field name="date_order"/>
            <field name="amount_total" widget="monetary"/>
            <field name="currency_id" column_invisible="1"/>
            <field name="state"/>
          </list>
        </field>
      </page>
      <page string="Notizen" name="notes">
        <field name="x_studio_notes" placeholder="Interne Notizen zum Vertrag ..."/>
      </page>
    </notebook>
  </sheet>
  <chatter/>
</form>"""

SEARCH_ARCH = """<search>
  <field name="x_name"/>
  <field name="x_studio_partner_id"/>
  <field name="x_studio_vertragsnummer"/>
  <filter name="f_aktiv" string="Aktiv" domain="[('x_studio_status', '=', 'aktiv')]"/>
  <filter name="f_laeuft_aus" string="Läuft aus" domain="[('x_studio_status', '=', 'laeuft_aus')]"/>
  <separator/>
  <filter name="f_rahmen" string="Rahmenverträge" domain="[('x_studio_vertragstyp', '=', 'rahmenvertrag')]"/>
  <group>
    <filter name="g_typ" string="Vertragstyp" domain="[]" context="{'group_by': 'x_studio_vertragstyp'}"/>
    <filter name="g_status" string="Status" domain="[]" context="{'group_by': 'x_studio_status'}"/>
    <filter name="g_partner" string="Lieferant" domain="[]" context="{'group_by': 'x_studio_partner_id'}"/>
  </group>
</search>"""

PARTNER_TAB_ARCH = """<data>
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


def ensure_field(c, model, vals):
    existing = c.find_one("ir.model.fields",
                          [("model", "=", model), ("name", "=", vals["name"])],
                          fields=["id"])
    if existing:
        return existing["id"], False
    mid = c.find_one("ir.model", [("model", "=", model)], fields=["id"])["id"]
    vals = dict(vals, model_id=mid)
    return c.create("ir.model.fields", vals), True


def ensure_view(c, name, model, vtype, arch, inherit_id=None):
    existing = c.find_one("ir.ui.view", [("name", "=", name)], fields=["id"])
    vals = {"name": name, "model": model, "type": vtype, "arch": arch}
    if inherit_id:
        vals["inherit_id"] = inherit_id
    if existing:
        c.write("ir.ui.view", [existing["id"]], {"arch": arch})
        return existing["id"], False
    return c.create("ir.ui.view", vals), True


def main() -> int:
    c = OdooClient.from_env()
    c.connect()

    print("=== inverse one2many auf res.partner ===")
    fid, created = ensure_field(c, "res.partner", {
        "name": "x_studio_contract_ids",
        "ttype": "one2many",
        "relation": MODEL,
        "relation_field": "x_studio_partner_id",
        "field_description": "Lieferantenverträge",
    })
    print(f"  x_studio_contract_ids {'angelegt' if created else 'vorhanden'} (id={fid})")

    print("\n=== Views fuer das Modell ===")
    for name, vtype, arch in [
        (f"{MODEL}.list", "list", LIST_ARCH),
        (f"{MODEL}.form", "form", FORM_ARCH),
        (f"{MODEL}.search", "search", SEARCH_ARCH),
    ]:
        vid, created = ensure_view(c, name, MODEL, vtype, arch)
        print(f"  {name:<28} {'angelegt' if created else 'aktualisiert'} (id={vid})")

    print("\n=== Action + Menue ===")
    act = c.find_one("ir.actions.act_window",
                     [("res_model", "=", MODEL), ("name", "=", "Lieferantenverträge")],
                     fields=["id"])
    if act:
        action_id = act["id"]
        print(f"  Action vorhanden (id={action_id}).")
    else:
        action_id = c.create("ir.actions.act_window", {
            "name": "Lieferantenverträge",
            "res_model": MODEL,
            "view_mode": "list,form",
            "help": "<p class='o_view_nocontent_smiling_face'>"
                    "Ersten Lieferantenvertrag anlegen</p>",
        })
        print(f"  Action angelegt (id={action_id}).")

    menu = c.find_one("ir.ui.menu",
                      [("name", "=", "Lieferantenverträge"),
                       ("parent_id", "=", PURCHASE_ROOT_MENU_ID)], fields=["id"])
    if menu:
        print(f"  Menue vorhanden (id={menu['id']}).")
    else:
        menu_id = c.create("ir.ui.menu", {
            "name": "Lieferantenverträge",
            "parent_id": PURCHASE_ROOT_MENU_ID,
            "action": f"ir.actions.act_window,{action_id}",
            "sequence": 20,
        })
        print(f"  Menue angelegt (id={menu_id}).")

    print("\n=== Partner-Tab (inherited) ===")
    vid, created = ensure_view(c, "res.partner.form.lieferantenvertraege",
                               "res.partner", "form", PARTNER_TAB_ARCH,
                               inherit_id=PARTNER_FORM_VIEW_ID)
    print(f"  Partner-Tab {'angelegt' if created else 'aktualisiert'} (id={vid})")

    print("\nViews/Menue abgeschlossen ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
