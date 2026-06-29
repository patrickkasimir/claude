#!/usr/bin/env python3
"""Schritt 5 — Mail/Aktivitaeten aktivieren + Automatisierungen.

A) is_mail_thread + is_mail_activity auf x_lieferantenvertrag aktivieren
   (Chatter + Aktivitaeten; Voraussetzung fuer die Erinnerungs-Activity).
B) Automation 1 (on_create_or_write auf purchase.order): wenn ein
   Lieferantenvertrag gesetzt ist -> Bestellung am Vertrag in
   x_studio_orders_ids eintragen (Server-Action, state='code').
C) Automation 2 (on_time auf x_lieferantenvertrag): 30 Tage vor Enddatum ->
   To-Do-Activity fuer den Verantwortlichen (state='next_activity').

Idempotent (Automationen werden ueber den Namen erkannt).
"""
from odoo_client import OdooClient

CONTRACT_MODEL = "x_lieferantenvertrag"
TODO_ACTIVITY_TYPE_ID = 4           # mail.mail_activity_data_todo
REMINDER_DAYS_BEFORE = 30

AUTO1_NAME = "LV: Bestellung mit Vertrag verknüpfen"
AUTO2_NAME = "LV: Erinnerung Vertragsende"

AUTO1_CODE = """# Bestellung am verknuepften Lieferantenvertrag eintragen
for record in records:
    contract = record.x_studio_lieferantenvertrag_id
    if contract and record.id not in contract.x_studio_orders_ids.ids:
        contract.write({'x_studio_orders_ids': [(4, record.id)]})
"""


def enable_mail(c: OdooClient) -> int:
    m = c.find_one("ir.model", [("model", "=", CONTRACT_MODEL)],
                   fields=["id", "is_mail_thread", "is_mail_activity"])
    vals = {}
    if not m["is_mail_thread"]:
        vals["is_mail_thread"] = True
    if not m["is_mail_activity"]:
        vals["is_mail_activity"] = True
    if vals:
        c.write("ir.model", [m["id"]], vals)
        print("  Chatter/Aktivitaeten aktiviert:", vals)
    else:
        print("  Chatter/Aktivitaeten bereits aktiv.")
    # Verifizieren, dass die Mixin-Felder jetzt existieren
    have = c.search_read("ir.model.fields",
                         [("model", "=", CONTRACT_MODEL),
                          ("name", "in", ["message_ids", "activity_ids"])],
                         fields=["name"])
    print("  Vorhandene Mixin-Felder:", sorted(f["name"] for f in have))
    # Hinweis: message_main_attachment_id (Rechnungs-Vorschau) ist hier NICHT
    # moeglich – es kommt vom Code-Mixin mail.thread.main.attachment, das auf
    # manuellen Modellen via RPC nicht ergaenzbar ist. Stattdessen: pdf_viewer
    # auf einem Binaerfeld (siehe 03_model.py / 07_views.py).
    return m["id"]


def field_id(c, model, name):
    f = c.find_one("ir.model.fields", [("model", "=", model), ("name", "=", name)],
                   fields=["id"])
    return f["id"] if f else None


def ensure_automation(c, name, vals):
    existing = c.find_one("base.automation", [("name", "=", name)], fields=["id"])
    if existing:
        print(f"  '{name}' existiert bereits (id={existing['id']}).")
        return existing["id"], False
    aid = c.create("base.automation", vals)
    print(f"  '{name}' angelegt (id={aid}).")
    return aid, True


def main() -> int:
    c = OdooClient.from_env()
    c.connect()

    print("=== A) Mail/Aktivitaeten ===")
    contract_model_id = enable_mail(c)

    po_model_id = c.find_one("ir.model", [("model", "=", "purchase.order")],
                             fields=["id"])["id"]
    link_field_id = field_id(c, "purchase.order", "x_studio_lieferantenvertrag_id")
    end_date_field_id = field_id(c, CONTRACT_MODEL, "x_studio_end_date")

    print("\n=== B) Automation 1: PO -> Vertrag ===")
    ensure_automation(c, AUTO1_NAME, {
        "name": AUTO1_NAME,
        "model_id": po_model_id,
        "trigger": "on_create_or_write",
        "trigger_field_ids": [(6, 0, [link_field_id])],
        "filter_domain": "[('x_studio_lieferantenvertrag_id', '!=', False)]",
        "action_server_ids": [(0, 0, {
            "name": AUTO1_NAME,
            "model_id": po_model_id,
            "state": "code",
            "usage": "base_automation",
            "code": AUTO1_CODE,
        })],
    })

    print("\n=== C) Automation 2: Erinnerung Vertragsende ===")
    ensure_automation(c, AUTO2_NAME, {
        "name": AUTO2_NAME,
        "model_id": contract_model_id,
        "trigger": "on_time",
        "trg_date_id": end_date_field_id,
        "trg_date_range": REMINDER_DAYS_BEFORE,
        "trg_date_range_mode": "before",
        "trg_date_range_type": "day",
        "filter_domain": "[('x_studio_status', 'in', ['aktiv', 'laeuft_aus']), "
                         "('x_studio_end_date', '!=', False)]",
        "action_server_ids": [(0, 0, {
            "name": AUTO2_NAME,
            "model_id": contract_model_id,
            "state": "next_activity",
            "usage": "base_automation",
            "activity_type_id": TODO_ACTIVITY_TYPE_ID,
            "activity_summary": "Vertrag läuft aus – Verlängerung/Kündigung prüfen",
            "activity_note": "Das Enddatum dieses Lieferantenvertrags rückt näher. "
                             "Bitte Verlängerung oder Kündigung prüfen.",
            "activity_user_type": "generic",
            "activity_user_field_name": "x_studio_responsible_id",
            "activity_date_deadline_range": REMINDER_DAYS_BEFORE,
            "activity_date_deadline_range_type": "days",
        })],
    })

    print("\nAutomatisierungen abgeschlossen ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
