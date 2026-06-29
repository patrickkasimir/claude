#!/usr/bin/env python3
"""Schritt 1b — Verifikation des `translate`-Verhaltens (kritischer Plan-Punkt).

Legt ein Wegwerf-Modell + Textfeld mit translate='standard' an, liest es
zurueck und raeumt danach restlos wieder auf. Schreibt NICHTS Bleibendes.
"""
from odoo_client import OdooClient

PROBE_MODEL = "x_lv_translate_probe"


def cleanup(c: OdooClient) -> None:
    m = c.find_one("ir.model", [("model", "=", PROBE_MODEL)], fields=["id"])
    if m:
        # Felder werden mit dem Modell entfernt; Modell loeschen genuegt.
        c.unlink("ir.model", [m["id"]])
        print("  Aufgeraeumt: Probe-Modell geloescht.")


def main() -> int:
    c = OdooClient.from_env()
    c.connect()

    # Falls ein frueherer Lauf abgebrochen ist: erst sauber machen.
    cleanup(c)

    print("Lege Wegwerf-Modell an:", PROBE_MODEL)
    model_id = c.create("ir.model", {
        "name": "LV Translate Probe",
        "model": PROBE_MODEL,
    })

    print("Lege uebersetzbares Textfeld an (translate='standard') ...")
    field_id = c.create("ir.model.fields", {
        "name": "x_studio_probe_note",
        "model_id": model_id,
        "field_description": "Probe Note",
        "ttype": "text",
        "translate": "standard",
    })

    back = c.read("ir.model.fields", [field_id],
                  ["name", "ttype", "translate"])[0]
    print("Zurueckgelesen:", back)

    ok = back.get("translate") == "standard"
    print("\n→ translate='standard' akzeptiert und gespeichert:",
          "JA ✓" if ok else "NEIN ✗")

    cleanup(c)
    print("\nTranslate-Probe abgeschlossen.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
