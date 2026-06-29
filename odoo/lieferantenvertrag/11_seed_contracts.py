#!/usr/bin/env python3
"""Schritt 7b — 100 Demo-Verträge auf 25 bestehende Firmenkontakte.

Pro Firma 4 Verträge (einer je Vertragsart). Jeder Vertrag bekommt das
generische PDF seiner Art ins Binärfeld x_studio_vertragsdokument
(-> pdf_viewer-Vorschau im Formular). Einzelvereinbarung wird an den
Rahmenvertrag derselben Firma gehängt.

Idempotent über die deterministische Vertragsnummer (LV-2026-<firma>-<typ>).
Erzeugte IDs landen in seed_ids.json (für gezieltes Aufräumen).
"""
import base64
import json
from datetime import date
from pathlib import Path

import pdf_gen
from odoo_client import OdooClient

MODEL = "x_lieferantenvertrag"
N_COMPANIES = 25

TYPES = [  # Reihenfolge wichtig: rahmenvertrag vor einzelvereinbarung
    ("avv", "AVV"),
    ("nda", "NDA"),
    ("rahmenvertrag", "Rahmenvertrag"),
    ("einzelvereinbarung", "Einzelvereinbarung"),
]

# etwas Abwechslung beim Status (gewichtet Richtung 'aktiv')
STATUS_CYCLE = ["aktiv", "aktiv", "aktiv", "laeuft_aus",
                "entwurf", "beendet", "in_pruefung", "aktiv"]


def dates_for(status: str):
    if status == "beendet":
        return date(2024, 1, 1), date(2025, 12, 31)
    if status == "laeuft_aus":
        return date(2025, 7, 16), date(2026, 7, 16)   # nahe 'heute' (2026-06-29)
    if status == "entwurf":
        return date(2026, 9, 1), date(2027, 8, 31)
    return date(2026, 1, 1), date(2026, 12, 31)


def main() -> int:
    c = OdooClient.from_env()
    c.connect()

    # PDFs erzeugen + base64 laden
    paths = pdf_gen.generate_all(Path(__file__).parent / "templates")
    pdf_b64 = {k: base64.b64encode(p.read_bytes()).decode() for k, p in paths.items()}
    print("PDF-Vorlagen bereit:", list(pdf_b64))

    # 25 Firmen suchen: bevorzugt Lieferanten, sonst beliebige Firmen
    companies = c.search_read(
        "res.partner",
        [("is_company", "=", True), ("supplier_rank", ">", 0),
         ("name", "not ilike", "[TEST]")],
        fields=["id", "name"], limit=N_COMPANIES, order="id")
    if len(companies) < N_COMPANIES:
        have = [x["id"] for x in companies]
        companies += c.search_read(
            "res.partner",
            [("is_company", "=", True), ("id", "not in", have),
             ("name", "not ilike", "[TEST]")],
            fields=["id", "name"], limit=N_COMPANIES - len(companies), order="id")
    companies = companies[:N_COMPANIES]
    print(f"Firmen gewählt: {len(companies)}")
    if len(companies) < N_COMPANIES:
        print("WARNUNG: weniger als", N_COMPANIES, "Firmen gefunden.")

    created, skipped = [], 0
    idx = 0
    for ci, comp in enumerate(companies):
        rahmen_id = None
        for vtyp, label in TYPES:
            vnr = f"LV-2026-{comp['id']:05d}-{vtyp[:3].upper()}"
            existing = c.find_one(MODEL, [("x_studio_vertragsnummer", "=", vnr)],
                                  fields=["id"])
            if existing:
                skipped += 1
                if vtyp == "rahmenvertrag":
                    rahmen_id = existing["id"]
                continue
            status = STATUS_CYCLE[idx % len(STATUS_CYCLE)]
            idx += 1
            start, end = dates_for(status)
            vals = {
                "x_name": f"{label} – {comp['name']}",
                "x_studio_partner_id": comp["id"],
                "x_studio_vertragstyp": vtyp,
                "x_studio_status": status,
                "x_studio_vertragsnummer": vnr,
                "x_studio_start_date": start.isoformat(),
                "x_studio_end_date": end.isoformat(),
                "x_studio_responsible_id": c.uid,
                "x_studio_notes": f"Generierter Demo-Vertrag ({label}) für "
                                  f"{comp['name']}.",
                "x_studio_vertragsdokument": pdf_b64[vtyp],
                "x_studio_vertragsdokument_filename": f"{label}-Vorlage.pdf",
            }
            if vtyp == "einzelvereinbarung" and rahmen_id:
                vals["x_studio_parent_contract_id"] = rahmen_id
            cid = c.create(MODEL, vals)
            created.append(cid)
            if vtyp == "rahmenvertrag":
                rahmen_id = cid
        print(f"  [{ci+1:>2}/{len(companies)}] {comp['name'][:40]}")

    Path(__file__).parent.joinpath("seed_ids.json").write_text(
        json.dumps(created))
    print(f"\nAngelegt: {len(created)} | übersprungen (vorhanden): {skipped}")
    print(f"Gesamt Verträge im Modell: {c.search_count(MODEL, [])}")
    print("IDs gespeichert in seed_ids.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
