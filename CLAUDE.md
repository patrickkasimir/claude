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
