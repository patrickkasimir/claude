# Update-Sets – Anpassungen mit Apply + Test (Odoo, via XML-RPC)

„Update-Set-Mechanismus" für die Odoo-Anpassungen: jede Anpassung ist ein
**Changeset** mit **apply** (idempotenter Aufbau) und **test** (technische *und*
fachliche Prüfung). Einzeln oder gesammelt ausführbar — ideal, um nach einem
Odoo-Upgrade **Changeset für Changeset** zu prüfen.

## Einrichtung
`.env` (gitignored) mit Zugangsdaten anlegen (Vorlage `.env.example`). Diese **eine**
`.env` steuert auch die Build-Skripte (Subprozesse erben die `ODOO_*`-Variablen).
Bei neuer Trial-Instanz nur hier URL/DB/Key umstellen.

## Nutzung
```bash
python3 run.py list                 # Changesets auflisten
python3 run.py test [ID|all]        # nur prüfen (Default: all)
python3 run.py apply [ID|all]       # nur (neu) aufbauen (idempotent)
python3 run.py apply-test [ID|all]  # aufbauen, dann prüfen
python3 run.py verify               # = test all
```

## Changesets
| ID | Inhalt | apply ruft |
|----|--------|-----------|
| LV-01 | Datenmodell Lieferantenvertrag (Modell, Felder, Rechte) | `03_model.py` |
| LV-02 | Einkaufs-Verknüpfung (Feld auf Bestellung + Formular) | `04_purchase_link.py` |
| LV-03 | Mehrsprachigkeit (de/en Labels + Auswahlwerte) | `05_translations.py` |
| LV-04 | Automationen (Bestellung↔Vertrag, Erinnerung) | `06_mail_and_automations.py` |
| LV-05 | Oberfläche (Views, Menü, Partner-Tab, Smart-Button) | `07_views.py`, `10_smart_button.py` |
| PP-01 | Projektplan als Gantt-PDF (Bericht + Button) | `projektplan/01_report.py` |

## Was die Tests prüfen (technisch + fachlich)
- **technisch:** Existenz von Modell/Feldern/Auswahlwerten/Views/Menü/Bericht/
  Automationen, korrekte Typen, Sichtbarkeit in den (gerenderten) Formularen.
- **fachlich (Verhalten):**
  - LV-03: Labels/Auswahlwerte kommen je Sprache korrekt zurück
  - LV-04: legt Wegwerf-Vertrag + -Bestellung an → Automation muss verknüpfen → räumt auf
  - LV-05: Smart-Button-Zähler stimmt mit echter Vertragsanzahl überein
  - PP-01: Server-Action berechnet Geometrie; **Bericht wird serverseitig zu HTML
    gerendert** und auf `article`-Div + Charset geprüft (fängt das Umlaut-/Layout-Regressionsrisiko)

## Nach einem Odoo-Upgrade
```bash
python3 run.py test all
```
Zeigt je Changeset PASS/FAIL. Bei FAIL: betroffenes Changeset `apply` (idempotent),
ggf. einen XPath/Code anpassen, dann erneut `test`. Da die Skripte die Quelle der
Wahrheit sind, ist alles reproduzier- und reparierbar.

## Neues Changeset hinzufügen
1. Build-Skript schreiben (idempotent), wie die bestehenden `NN_*.py`.
2. In `run.py` eine `test_xxx(c)`-Funktion ergänzen (nutzt `Check.expect(...)`).
3. Eintrag in `CHANGESETS` mit `id`, `title`, `apply`, `test`.
