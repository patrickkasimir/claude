#!/usr/bin/env python3
"""Pre-Upgrade-Härtung der SOLVVision-Instanz für Odoo 19.0 -> saas-19.3.

Idempotent. Behebt vorhandene (NICHT von uns stammende) Studio-Anpassungen, die
das Upgrade brechen, weil sie 19.3-entfernte Felder referenzieren bzw. von 19.3
strenger validiert werden:

  1. account.analytic.line.x_studio_error          -> guard so_line.project_id
  2. account.analytic.line.x_studio_invoiced        -> guard timesheet_invoice_id
  3. account.analytic.line.x_studio_provisionrelevant -> guard reinvoiced_sale_order_id
  4. sale.order.line.x_studio_project (related)     -> geschütztes Compute-Feld
  5. x_vi2va_products Default-Views                 -> dangling Feld x_studio_company_id entfernen

Muster für 1-4: '<feld>' in self.env['<model>'].fields_get() vor dem Zugriff
(in 19.0 Verhalten unverändert, in 19.3 übersprungen -> kein Crash).

Zielinstanz = ENV/.env. Für eine Test-/Upgrade-DB Inline-Override nutzen, die
.env der Arbeitsinstanz NICHT überschreiben.
"""
import re

from odoo_client import OdooClient

COMPUTE_FIXES = {
    ("account.analytic.line", "x_studio_error"): (
        "# Sven Müller, 23.08.2025  (upgrade-fest)\n"
        "# Prüft, ob die gewählte Auftragsposition zum Projekt gehört.\n"
        "has_proj = 'project_id' in self.env['sale.order.line'].fields_get()\n"
        "for record in self:\n"
        "    error = ''\n"
        "    if has_proj and record.so_line and record.project_id:\n"
        "        lp = record.so_line.project_id\n"
        "        if not (lp and lp.id == record.project_id.id):\n"
        "            error = '⚠️'\n"
        "    record['x_studio_error'] = error\n"
    ),
    ("account.analytic.line", "x_studio_invoiced"): (
        "# Sven Müller, 21.08.2025  (upgrade-fest)\n"
        "# Setze Feld 'Abgerechnet', sobald Buchung in Rechnung gestellt wurde\n"
        "has_inv = 'timesheet_invoice_id' in self.env['account.analytic.line'].fields_get()\n"
        "for record in self:\n"
        "    flag = False\n"
        "    if has_inv and record.timesheet_invoice_id:\n"
        "        flag = True\n"
        "    record['x_studio_invoiced'] = flag\n"
    ),
    ("account.analytic.line", "x_studio_provisionrelevant"): (
        "# Sven Müller, 26.08./27.08.2025  (upgrade-fest)\n"
        "# Provisionsrelevanz; Reisekosten ausgeschlossen, MPS einbezogen.\n"
        "has_reinv = 'reinvoiced_sale_order_id' in self.env['project.project'].fields_get()\n"
        "for record in self:\n"
        "    if record.so_line and record.so_line.product_id.name:\n"
        "        if record.so_line.product_id.name == 'Reisekosten':\n"
        "            record['x_studio_provisionrelevant'] = False\n"
        "        else:\n"
        "            record['x_studio_provisionrelevant'] = True\n"
        "    elif record.project_id and record.project_id.x_studio_project_type.id == 3:\n"
        "        record['x_studio_provisionrelevant'] = True\n"
        "    elif has_reinv and record.project_id.reinvoiced_sale_order_id.sale_order_template_id.id in (15, 4):\n"
        "        record['x_studio_provisionrelevant'] = True\n"
        "    else:\n"
        "        record['x_studio_provisionrelevant'] = False\n"
    ),
}

PROJECT_COMPUTE = (
    "# 2026-06-29 upgrade-fest: aus related 'order_id.project_id' -> geschütztes Compute\n"
    "has_p = 'project_id' in self.env['sale.order'].fields_get()\n"
    "for record in self:\n"
    "    record['x_studio_project'] = record.order_id.project_id if (has_p and record.order_id) else False\n"
)

VI2VA_MODEL = "x_vi2va_products"
DANGLING_FIELD = "x_studio_company_id"


def strip_field_refs(arch, fname):
    arch = re.sub(r'<field name="%s"[^>]*?/>' % re.escape(fname), "", arch)
    arch = re.sub(r'<field name="%s"[^>]*?>.*?</field>' % re.escape(fname), "", arch, flags=re.DOTALL)
    arch = re.sub(r'<xpath[^>]*%s[^>]*?/>' % re.escape(fname), "", arch)
    return arch


def main() -> int:
    c = OdooClient.from_env(); c.connect()
    print("Ziel:", c.url, "| Version:", c.version.get("server_version"))

    print("\n=== 1-3) Compute-Felder absichern ===")
    for (model, name), code in COMPUTE_FIXES.items():
        f = c.find_one("ir.model.fields", [("model", "=", model), ("name", "=", name)],
                       fields=["id", "compute"])
        if not f:
            print(f"  {model}.{name}: NICHT vorhanden (übersprungen)")
            continue
        if (f["compute"] or "").strip() == code.strip():
            print(f"  {model}.{name}: bereits abgehärtet")
        else:
            c.write("ir.model.fields", [f["id"]], {"compute": code})
            print(f"  {model}.{name}: abgehärtet ✓")

    print("\n=== 4) sale.order.line.x_studio_project (related -> Compute) ===")
    f = c.find_one("ir.model.fields", [("model", "=", "sale.order.line"), ("name", "=", "x_studio_project")],
                   fields=["id", "related", "compute"])
    if not f:
        print("  nicht vorhanden (übersprungen)")
    elif f["related"]:
        c.write("ir.model.fields", [f["id"]], {"related": False, "compute": PROJECT_COMPUTE,
                                               "depends": "order_id", "store": False, "readonly": True})
        print("  von related auf geschütztes Compute umgestellt ✓")
    elif (f["compute"] or "").strip() != PROJECT_COMPUTE.strip():
        c.write("ir.model.fields", [f["id"]], {"compute": PROJECT_COMPUTE, "depends": "order_id"})
        print("  Compute aktualisiert ✓")
    else:
        print("  bereits geschütztes Compute")

    print("\n=== 5) x_vi2va_products: dangling Feld %s aus Views entfernen ===" % DANGLING_FIELD)
    vs = c.search_read("ir.ui.view", [("model", "=", VI2VA_MODEL), ("arch_db", "like", DANGLING_FIELD)],
                       fields=["id", "name", "arch"])
    if not vs:
        print("  keine View referenziert das Feld mehr")
    for v in vs:
        new = strip_field_refs(v["arch"], DANGLING_FIELD)
        if new != v["arch"]:
            c.write("ir.ui.view", [v["id"]], {"arch": new})
            print(f"  bereinigt: {v['name']}")
        else:
            print(f"  WARN: konnte Referenz in {v['name']} nicht entfernen (manuell prüfen)")

    # Eng begrenzt auf die bekannte Studio-Multi-Company-Falle: NUR Regeln, die
    # x_studio_company_id referenzieren UND deren Modell dieses Feld nicht (mehr)
    # hat. KEIN generischer Domain-Parser (der löste Werte-Tupel wie
    # ('out_invoice','out_refund') fälschlich als Felder aus -> deaktivierte
    # versehentlich Standard-Regeln).
    print("\n=== 6) Verwaiste Multi-Company-Regeln (x_studio_company_id auf Modell ohne Feld) ===")
    F = "x_studio_company_id"
    rules = c.search_read("ir.rule", [("domain_force", "like", F), ("active", "=", True)],
                          fields=["name", "model_id"])
    fixed = 0
    for r in rules:
        if not r["model_id"]:
            continue
        tech = c.read("ir.model", [r["model_id"][0]], ["model"])[0]["model"]
        has = bool(c.find_one("ir.model.fields", [("model", "=", tech), ("name", "=", F)], fields=["id"]))
        if has:
            print(f"  ok (Feld vorhanden, unverändert): {r['name']} ({tech})")
        else:
            c.write("ir.rule", [r["id"]], {"active": False})
            fixed += 1
            print(f"  deaktiviert: {r['name']} ({tech}) – referenziert fehlendes {F}")
    if not fixed:
        print("  keine verwaiste Regel")

    print("\n=== 7) Kontakt-Tabs: Studio res.partner-View upgrade-fest machen ===")
    sv = c.find_one("ir.ui.view", [("model", "=", "res.partner"),
                    ("name", "=", "Odoo Studio: res.partner.form customization")],
                    fields=["id", "arch"])
    if not sv:
        print("  Studio-res.partner-View nicht vorhanden (übersprungen)")
    else:
        a = orig = sv["arch"]
        # brüchige Manipulationen am Kern-Element vat_vies_container raus (move/hide)
        a = re.sub(r"<xpath\b[^>]*?vat_vies_container[^>]*?>.*?</xpath>", "", a, flags=re.DOTALL)
        a = re.sub(r"<xpath\b[^>]*?vat_vies_container[^>]*?/>", "", a)

        # 19.3-entferntes Kernfeld company_type -> is_company in Modifikatoren
        def _ct(m):
            op, val = m.group(1), m.group(3)
            if op == "==":
                return "is_company" if val == "company" else "not is_company"
            return "not is_company" if val == "company" else "is_company"
        a = re.sub(r"""company_type\s*(==|!=)\s*(&quot;|['"])(company|person)\2""", _ct, a)

        if a != orig:
            c.write("ir.ui.view", [sv["id"]], {"arch": a})
            print("  bereinigt: vat_vies_container-XPaths entfernt, company_type->is_company ✓")
        else:
            print("  bereits upgrade-fest")

    print("\nPre-Upgrade-Härtung abgeschlossen ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
