# Projektplan als Gantt-PDF (Odoo 19, via XML-RPC)

Fügt einen Button **„Ausgabe als PDF"** in das Projekt-Formular ein, der die
**Aufgaben oberster Ebene** (ohne Unteraufgaben) als **Gantt-Chart** in ein
A4-Querformat-PDF rendert — komplett über die External API, ohne eigenes Modul.

Datenbasis je Aufgabe: Start `planned_date_begin` → Ende `date_deadline`.

## Einrichtung

1. `.env` mit Zugangsdaten anlegen (gleiche Instanz wie `../lieferantenvertrag/`).
   Vorlage: `../lieferantenvertrag/.env.example`. `.env` ist gitignored.
2. Aufbau: `python3 01_report.py` (idempotent, mehrfach ausführbar).

## Benutzung

Projekt öffnen → Header-Button **„Ausgabe als PDF"**. Erzeugt das Gantt-PDF mit
Monats-Achse + Gitterlinien, Heute-Linie, Farb-Legende (je Stage) und einer Liste
der nicht terminierten Aufgaben.

## Wie es funktioniert (alles UI-Konfiguration, kein Modul)

1. **Server-Action** (`state=code`) am Button berechnet je Top-Level-Aufgabe die
   Balken-Geometrie (Position/Breite in %), Monats-Ticks, Heute-Position und Legende
   und **speichert sie in Hilfsfeldern**.
2. Sie gibt `report.report_action(project)` zurück → der **QWeb-PDF-Bericht** liest
   die Hilfsfelder aus den Datensätzen und zeichnet das Chart (HTML/CSS-Balken).

Angelegte Hilfsfelder:
- `project.task`: `x_studio_gantt_show`, `…_undated`, `…_left`, `…_width`, `…_color`,
  `…_period`, `…_meta`
- `project.project`: `x_studio_gantt_subtitle`, `…_ticks`, `…_legend`, `…_today`

## Wichtige Odoo-19-/wkhtmltopdf-Lehren (im Code dokumentiert)

- **`report_action(data=…)` verpufft** beim serverseitigen PDF-Render → Geometrie
  muss in **gespeicherten Feldern** liegen, die die Vorlage aus `docs` liest.
- **Umlaute-Mojibake** (UTF-8 als Latin-1): Vorlage muss **`web.basic_layout`**
  verwenden (liefert `html_container` **und** `<div class="article">`, das Odoos
  PDF-Pipeline zum Extrahieren braucht). Nur `web.html_container` → kaputtes Charset.
- Server-Action-Code (safe_eval) erlaubt **kein** `def`/`lambda`/`import`; `datetime`
  ist verfügbar, Monatsschritt via `.replace(year=…, month=…)`.
- Listen-Views = `<list>`, Pflicht-m2o = `on_delete`, Custom-Felder mit `x_`-Präfix.

## Portierbarkeit

Instanzunabhängig: feste IDs sind durch `c.ref('modul.name')` ersetzt
(`project.edit_project`). Bei neuer Trial-Instanz nur `.env` umstellen und
`01_report.py` erneut ausführen.
