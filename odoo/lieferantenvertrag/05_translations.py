#!/usr/bin/env python3
"""Schritt 4 — Mehrsprachigkeit (de_DE + en_US).

Setzt fuer alle neuen Felder/Selection-Werte/Modellnamen die Beschriftung
je Sprache, IMMER mit explizitem context={'lang': code}. Liest danach beide
Sprachen zur Kontrolle zurueck.

Quelle der Sprachen ist dynamisch (res.lang); fuer Sprachen ohne hinterlegte
Uebersetzung wird der deutsche Text als Fallback geschrieben.
"""
from odoo_client import OdooClient

MODEL = "x_lieferantenvertrag"

# Modellname je Sprache
MODEL_NAME = {"de_DE": "Lieferantenvertrag", "en_US": "Supplier Contract"}

# Feldbeschriftungen (model -> field -> {lang: label})
FIELD_LABELS = {
    MODEL: {
        "x_name": {"de_DE": "Bezeichnung", "en_US": "Name"},
        "x_studio_partner_id": {"de_DE": "Lieferant", "en_US": "Vendor"},
        "x_studio_vertragstyp": {"de_DE": "Vertragstyp", "en_US": "Contract Type"},
        "x_studio_parent_contract_id": {"de_DE": "Übergeordneter Rahmenvertrag",
                                        "en_US": "Parent Framework Agreement"},
        "x_studio_vertragsnummer": {"de_DE": "Vertragsnummer", "en_US": "Contract Number"},
        "x_studio_status": {"de_DE": "Status", "en_US": "Status"},
        "x_studio_start_date": {"de_DE": "Startdatum", "en_US": "Start Date"},
        "x_studio_end_date": {"de_DE": "Enddatum", "en_US": "End Date"},
        "x_studio_auto_renew": {"de_DE": "Automatische Verlängerung", "en_US": "Auto Renewal"},
        "x_studio_notice_days": {"de_DE": "Kündigungsfrist (Tage)", "en_US": "Notice Period (days)"},
        "x_studio_responsible_id": {"de_DE": "Verantwortlich", "en_US": "Responsible"},
        "x_studio_notes": {"de_DE": "Notizen", "en_US": "Notes"},
        "x_studio_orders_ids": {"de_DE": "Bestellungen", "en_US": "Purchase Orders"},
    },
    "purchase.order": {
        "x_studio_lieferantenvertrag_id": {"de_DE": "Lieferantenvertrag",
                                           "en_US": "Supplier Contract"},
    },
}

# Selection-Werte (field -> value -> {lang: label})
SELECTION_LABELS = {
    "x_studio_vertragstyp": {
        "avv": {"de_DE": "AVV", "en_US": "DPA"},
        "nda": {"de_DE": "NDA", "en_US": "NDA"},
        "rahmenvertrag": {"de_DE": "Rahmenvertrag", "en_US": "Framework Agreement"},
        "einzelvereinbarung": {"de_DE": "Einzelvereinbarung", "en_US": "Individual Agreement"},
    },
    "x_studio_status": {
        "entwurf": {"de_DE": "Entwurf", "en_US": "Draft"},
        "in_pruefung": {"de_DE": "In Prüfung", "en_US": "Under Review"},
        "aktiv": {"de_DE": "Aktiv", "en_US": "Active"},
        "laeuft_aus": {"de_DE": "Läuft aus", "en_US": "Expiring"},
        "beendet": {"de_DE": "Beendet", "en_US": "Ended"},
    },
}


def pick(labels: dict, code: str) -> str:
    """Uebersetzung fuer code, sonst de_DE-Fallback, sonst erster Wert."""
    return labels.get(code) or labels.get("de_DE") or next(iter(labels.values()))


def main() -> int:
    c = OdooClient.from_env()
    c.connect()
    langs = [l["code"] for l in
             c.search_read("res.lang", [("active", "=", True)], fields=["code"])]
    print("Aktive Sprachen:", langs)

    # --- Modellname ---
    m = c.find_one("ir.model", [("model", "=", MODEL)], fields=["id"])
    for code in langs:
        c.write("ir.model", [m["id"]], {"name": pick(MODEL_NAME, code)},
                context={"lang": code})
    print("Modellname uebersetzt.")

    # --- Feldbeschriftungen ---
    print("\n=== Feldbeschriftungen ===")
    for model, fields in FIELD_LABELS.items():
        for fname, labels in fields.items():
            f = c.find_one("ir.model.fields",
                           [("model", "=", model), ("name", "=", fname)],
                           fields=["id"])
            if not f:
                print(f"  WARN: {model}.{fname} nicht gefunden")
                continue
            for code in langs:
                c.write("ir.model.fields", [f["id"]],
                        {"field_description": pick(labels, code)},
                        context={"lang": code})
            print(f"  {model}.{fname}: {[pick(labels, c2) for c2 in langs]}")

    # --- Selection-Werte ---
    print("\n=== Selection-Werte ===")
    for fname, values in SELECTION_LABELS.items():
        f = c.find_one("ir.model.fields",
                       [("model", "=", MODEL), ("name", "=", fname)], fields=["id"])
        for value, labels in values.items():
            sel = c.find_one("ir.model.fields.selection",
                             [("field_id", "=", f["id"]), ("value", "=", value)],
                             fields=["id"])
            if not sel:
                print(f"  WARN: {fname}={value} nicht gefunden")
                continue
            for code in langs:
                c.write("ir.model.fields.selection", [sel["id"]],
                        {"name": pick(labels, code)}, context={"lang": code})
        print(f"  {fname}: {len(values)} Werte uebersetzt")

    # --- Kontroll-Lesung ---
    print("\n=== Kontrolle (Rueck-Lesung je Sprache) ===")
    for fname in ("x_studio_partner_id", "x_studio_vertragstyp"):
        line = [fname]
        for code in langs:
            f = c.search_read("ir.model.fields",
                              [("model", "=", MODEL), ("name", "=", fname)],
                              fields=["field_description"], context={"lang": code})
            line.append(f"{code}={f[0]['field_description']!r}")
        print("  " + "  ".join(line))
    # Selection-Stichprobe
    f = c.find_one("ir.model.fields", [("model", "=", MODEL),
                   ("name", "=", "x_studio_vertragstyp")], fields=["id"])
    for code in langs:
        sels = c.search_read("ir.model.fields.selection",
                             [("field_id", "=", f["id"])],
                             fields=["value", "name"], context={"lang": code},
                             order="sequence")
        print(f"  vertragstyp [{code}]:", {s["value"]: s["name"] for s in sels})

    print("\nMehrsprachigkeit abgeschlossen ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
