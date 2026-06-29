# Lieferantenvertragsmanagement (Odoo 19, via XML-RPC)

Baut ein Studio-kompatibles Datenmodell für Lieferantenverträge (AVV/NDA/
Rahmenvertrag/Einzelvereinbarung) in der Odoo-Instanz auf — komplett über die
External API (XML-RPC), ohne eigenes Modul.

Vollständige Spezifikation: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Einrichtung

1. `.env.example` → `.env` kopieren und API-Key eintragen (`.env` ist gitignored).
2. Verbindung testen: `python3 odoo_client.py`

## Aufbau (ein Kommando)

```bash
bash run_all.sh
```

Führt die idempotenten Schritte 1–6 aus. Mehrfach ausführbar, ohne Duplikate.

## Skripte einzeln

| Datei | Zweck |
|-------|-------|
| `odoo_client.py`        | Wiederverwendbarer XML-RPC-Client (mit lang-Context) + Verbindungstest |
| `01_discovery.py`       | Sprachen, Modul-Check, Kollisionscheck |
| `02_translate_probe.py` | Verifiziert `translate='standard'` (Odoo 19) an einem Wegwerf-Feld |
| `03_model.py`           | Modell `x_lieferantenvertrag` + Felder + Selektionen + Rechte |
| `04_purchase_link.py`   | Feld `x_studio_lieferantenvertrag_id` auf `purchase.order` |
| `05_translations.py`    | Beschriftungen + Selection-Werte de_DE/en_US |
| `06_mail_and_automations.py` | Chatter/Aktivitäten + Automation 1 (PO→Vertrag) + Automation 2 (Erinnerung) |
| `07_views.py`           | List/Form/Search-View, Menü+Action, Partner-Tab |
| `10_smart_button.py`    | Smart-Button „Verträge" (Anzahl) auf dem Lieferanten + gefilterte Action |
| `pdf_gen.py`            | Dependency-freier PDF-Generator + 4 generische Vorlagen je Vertragsart |
| `11_seed_contracts.py`  | 100 Demo-Verträge auf 25 Firmen, je mit PDF (pdf_viewer-Vorschau) |
| `13_seed_orders.py`     | 2 Bestellungen je Rahmenvertrag (mit Position), verknüpft im Tab |
| `14_confirm_orders.py`  | Demo-Bestellungen bestätigen (Entwurf/RFQ → echte Bestellung) |
| `08_validate.py`        | Testdaten anlegen + Prüfungen |
| `09_cleanup_testdata.py`| Nur die `[TEST]`-Daten wieder entfernen |
| `12_cleanup_seed.py`    | Nur die 100 Demo-Verträge (`LV-2026-…`) wieder entfernen |

## Wichtige Odoo-19-Besonderheiten (verifiziert)

- `ir.model.fields.translate` ist **Selection** (`standard`/`html_translate`/`xml_translate`), kein Boolean.
- Übersetzbare Werte immer mit `context={'lang': <code>}` lesen/schreiben.
- Pflicht-`many2one` braucht `on_delete='restrict'` (nicht `set null`); Feld heißt `on_delete`.
- Server-Action-Code (Sandbox) erlaubt **kein** Attribut-Setzen → `record.write({...})` statt `record.x = ...`.
- Zeit-Automation: `trg_date_range` positiv + `trg_date_range_mode='before'`.
- Listen-Views nutzen `<list>` (nicht `<tree>`); Chatter via `<chatter/>`.
- Search-View „Gruppieren nach": `<group>` ohne `string`/`expand`, Filter mit `domain="[]"` **und** `context`.
- **PDF-Vorschau:** Die *rechtsseitige* Rechnungs-Vorschau (`o_attachment_preview`)
  braucht das Feld `message_main_attachment_id` — das kommt vom **Code-Mixin
  `mail.thread.main.attachment`** (nur 14 eingebaute Modelle), NICHT von `mail.thread`,
  und ist auf manuellen Modellen via RPC/Studio nicht nachrüstbar (Custom-Felder
  müssen mit `x_` beginnen). Lösung hier: Binärfeld `x_studio_vertragsdokument` +
  Widget **`pdf_viewer`** → PDF wird direkt im Formular eingebettet angezeigt.
- **Smart-Button / Zähler:** geht per RPC über ein *manuelles* Computed-Field
  (`ir.model.fields` mit `compute`-Code) — genau wie Studio es intern macht. Im
  Compute-Code Item-Zuweisung `record['x_feld'] = ...` nutzen (Attribut-Zuweisung
  ist im Sandbox-`safe_eval` verboten, gleiche Regel wie bei Server-Actions).
  Die Plan-Notiz „kein `_compute`" betraf nur Modul-Code, nicht manuelle Felder.
