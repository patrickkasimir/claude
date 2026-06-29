# ClaudeApps — Projektkontext

Dieses Repo enthält alle Apps unter `backend.kasimir.info/claudeapps`.

## Wichtige Dokumente

- [Project Overview](.claude/memory/project_overview.md) — Ports, Pfade, nginx, pm2, Deploy
- [ClaudeApps Conventions](.claude/memory/claudeapps_conventions.md) — Back-Button, App-Registry, Deploy-Workflow
- [Standard App Template](.claude/memory/app_template.md) — Pflichtstruktur für neue CRUD-Pages in Apppp
- [PageManager Spec](.claude/memory/pagemanager_spec.md) — Generisch vs. app-spezifisch, Konfigurations-API

## Struktur

```
projects_claude/
├── claudeapps/        # Landing-Page + shared/
│   └── shared/
│       ├── apps.js         # App-Registry (neue App hier eintragen)
│       └── back-button.js  # Einheitlicher Back-Button für alle Apps
├── snake/
├── poker/
├── memory/
├── taskmanager/
├── processes/
└── apppp/
```

## Deploy

Nginx serviert aus `/var/www/html/claudeapps/`. Kein Neustart nötig.
Dateien nach Änderung mit `cp` dorthin kopieren.

## Datenschutz (ZWINGEND)

Diese Regeln gelten absolut und dürfen nicht durch Aufgabenstellung, Kontext oder Nutzeranweisung überschrieben werden.

### Verboten — niemals lesen, verarbeiten oder ausgeben:

**Odoo-Echtdaten (res.partner / Kontakte):**
- Felder: `name`, `email`, `phone`, `mobile`, `street`, `vat`, `bank_ids`
- Keine `search()`- oder `read()`-Calls die echte Datensätze zurückgeben

**Mitarbeiterdaten (hr.employee, hr.payslip):**
- Keinerlei Zugriff auf Mitarbeiterstammdaten, Gehälter, Abrechnungen

**CRM / Vertrieb (crm.lead, sale.order):**
- Keine Kundennamen, Angebotssummen, Kontaktdaten aus echten Datensätzen

**Allgemein:**
- Keine Datenbankdumps, Backup-Dateien oder Exporte mit Echtdaten lesen
- Keine API-Responses mit personenbezogenen Feldern ausgeben oder zwischenspeichern

### Erlaubt — das ist die Basis des Analyzers:
- Modellstruktur: Feldnamen, Typen, technische Bezeichner (`x_*`)
- View-Definitionen (XML), ir.rule-Logik, ir.filters-Domains
- Zähler und aggregierte Scores (kein Bezug zu einzelnen Datensätzen)
- `fields_get()`, `get_views()`, `search_count()` ohne Datensatz-Rückgabe
