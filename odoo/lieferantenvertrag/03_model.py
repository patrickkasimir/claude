#!/usr/bin/env python3
"""Schritt 2 — Datenmodell 'Lieferantenvertrag' (x_lieferantenvertrag).

Legt idempotent an:
- das Modell x_lieferantenvertrag
- alle Felder (mit x_studio_-Praefix)
- Selection-Werte (Vertragstyp, Status)
- Default fuer Status = 'entwurf'
- Zugriffsrechte (base.group_user lesen, Einkauf-User RWC, Einkauf-Manager voll)

Mehrfaches Ausfuehren erzeugt KEINE Duplikate.
"""
from odoo_client import OdooClient

MODEL = "x_lieferantenvertrag"
MODEL_LABEL = "Lieferantenvertrag"

# Zugriffsrechte-Gruppen werden zur Laufzeit per xml_id aufgeloest (instanzunabhaengig).

VERTRAGSTYP = [
    ("avv", "AVV"),
    ("nda", "NDA"),
    ("rahmenvertrag", "Rahmenvertrag"),
    ("einzelvereinbarung", "Einzelvereinbarung"),
]
STATUS = [
    ("entwurf", "Entwurf"),
    ("in_pruefung", "In Prüfung"),
    ("aktiv", "Aktiv"),
    ("laeuft_aus", "Läuft aus"),
    ("beendet", "Beendet"),
]

# Reihenfolge wichtig: Selbst-Referenz (parent) braucht das Modell, existiert hier schon.
FIELDS = [
    dict(name="x_studio_partner_id", ttype="many2one", relation="res.partner",
         field_description="Lieferant", required=True, on_delete="restrict"),
    dict(name="x_studio_vertragstyp", ttype="selection",
         field_description="Vertragstyp", required=True, selection=VERTRAGSTYP),
    dict(name="x_studio_parent_contract_id", ttype="many2one", relation=MODEL,
         field_description="Übergeordneter Rahmenvertrag"),
    dict(name="x_studio_vertragsnummer", ttype="char",
         field_description="Vertragsnummer"),
    dict(name="x_studio_status", ttype="selection",
         field_description="Status", selection=STATUS),
    dict(name="x_studio_start_date", ttype="date", field_description="Startdatum"),
    dict(name="x_studio_end_date", ttype="date", field_description="Enddatum"),
    dict(name="x_studio_auto_renew", ttype="boolean",
         field_description="Automatische Verlängerung"),
    dict(name="x_studio_notice_days", ttype="integer",
         field_description="Kündigungsfrist (Tage)"),
    dict(name="x_studio_responsible_id", ttype="many2one", relation="res.users",
         field_description="Verantwortlich"),
    dict(name="x_studio_notes", ttype="text", field_description="Notizen",
         translate="standard"),
    dict(name="x_studio_orders_ids", ttype="many2many", relation="purchase.order",
         field_description="Bestellungen"),
    dict(name="x_studio_vertragsdokument", ttype="binary",
         field_description="Vertragsdokument (PDF)"),
    dict(name="x_studio_vertragsdokument_filename", ttype="char",
         field_description="Dateiname"),
]


def ensure_model(c: OdooClient) -> int:
    m = c.find_one("ir.model", [("model", "=", MODEL)], fields=["id"])
    if m:
        print(f"Modell {MODEL} existiert bereits (id={m['id']}).")
        return m["id"]
    mid = c.create("ir.model", {"name": MODEL_LABEL, "model": MODEL})
    print(f"Modell {MODEL} angelegt (id={mid}).")
    return mid


def relabel_name_field(c: OdooClient, model_id: int) -> None:
    """Das automatisch erzeugte Namensfeld (x_name) als 'Bezeichnung' beschriften."""
    f = c.find_one("ir.model.fields",
                   [("model_id", "=", model_id), ("name", "=", "x_name")],
                   fields=["id", "field_description"])
    if f and f["field_description"] != "Bezeichnung":
        c.write("ir.model.fields", [f["id"]], {"field_description": "Bezeichnung"})
        print("  Namensfeld x_name -> 'Bezeichnung' beschriftet.")


def ensure_field(c: OdooClient, model_id: int, spec: dict):
    existing = c.find_one(
        "ir.model.fields",
        [("model_id", "=", model_id), ("name", "=", spec["name"])],
        fields=["id"],
    )
    if existing:
        return existing["id"], False
    vals = {k: v for k, v in spec.items() if k != "selection"}
    vals["model_id"] = model_id
    if "selection" in spec:
        vals["selection_ids"] = [
            (0, 0, {"value": val, "name": lbl, "sequence": (i + 1) * 10})
            for i, (val, lbl) in enumerate(spec["selection"])
        ]
    return c.create("ir.model.fields", vals), True


def ensure_access(c: OdooClient, model_id: int, group_id: int, perms, suffix: str):
    name = f"access_{MODEL}_{suffix}"
    vals = dict(
        name=name, model_id=model_id, group_id=group_id,
        perm_read=perms[0], perm_write=perms[1],
        perm_create=perms[2], perm_unlink=perms[3],
    )
    existing = c.find_one(
        "ir.model.access",
        [("model_id", "=", model_id), ("group_id", "=", group_id)],
        fields=["id"],
    )
    if existing:
        c.write("ir.model.access", [existing["id"]], vals)
        return existing["id"], False
    return c.create("ir.model.access", vals), True


def main() -> int:
    c = OdooClient.from_env()
    c.connect()

    model_id = ensure_model(c)
    relabel_name_field(c, model_id)

    print("\n=== Felder ===")
    for spec in FIELDS:
        fid, created = ensure_field(c, model_id, spec)
        print(f"  {spec['name']:<32} {'angelegt' if created else 'vorhanden'} (id={fid})")

    print("\n=== Status-Default ===")
    try:
        c.execute("ir.default", "set", MODEL, "x_studio_status", "entwurf")
        print("  Default fuer x_studio_status = 'entwurf' gesetzt.")
    except Exception as e:  # noqa: BLE001
        print("  Hinweis: Default konnte nicht gesetzt werden:", e)

    print("\n=== Zugriffsrechte ===")
    for xmlid, perms, suffix in [
        ("base.group_user", (1, 0, 0, 0), "user"),
        ("purchase.group_purchase_user", (1, 1, 1, 0), "purchase_user"),
        ("purchase.group_purchase_manager", (1, 1, 1, 1), "purchase_manager"),
    ]:
        gid = c.ref(xmlid)
        aid, created = ensure_access(c, model_id, gid, perms, suffix)
        print(f"  group {gid:<4} perms={perms} {'angelegt' if created else 'aktualisiert'} (id={aid})")

    print("\nModell-Aufbau abgeschlossen ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
