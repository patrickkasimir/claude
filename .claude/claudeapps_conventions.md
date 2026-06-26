---
name: claudeapps-conventions
description: "Konventionen für neue Apps in claudeapps — Back-Button, App-Registry, Deploy-Workflow"
metadata: 
  node_type: memory
  type: project
  originSessionId: 73c36615-91a9-4f39-a175-aec7d0ec84c0
---

# ClaudeApps — Konventionen

## Back-Button

Jede App bindet den einheitlichen Back-Button ein:
```html
<script src="/claudeapps/shared/back-button.js"></script>
```
Rendert automatisch ein SVG-Dreieck (◀) fixed oben links (`top: 16px, left: 16px`).

**Je nach App-Typ unterschiedlicher Umgang mit Überlagerung:**

| Typ | Beispiele | Lösung |
|-----|-----------|--------|
| Einfache Page / Spiel | Snake, Poker, Memory | Nur Script-Tag — Button liegt sauber über dem Content |
| Sidebar-App | Apppp, Taskmanager, Processes | `padding-top: 64px` auf `#sidebar-header`, damit oben links Platz für den Button ist |

## App-Registry

Neue App hinzufügen → einen Eintrag in `/claudeapps/shared/apps.js`:
```js
{ id: "meinapp", title: "MEINAPP", icon: "🎯", path: "/claudeapps/meinapp/", description: "..." }
```
Die Landing-Page rendert die Cards automatisch aus dieser Liste.

## Deploy

Nginx serviert statisch aus `/var/www/html/claudeapps/`. Kein Neustart nötig.

```bash
# Einzelne Datei deployen
cp /home/elija/apps/projects_claude/<app>/index.html /var/www/html/claudeapps/<app>/index.html

# Shared-Dateien deployen
cp /home/elija/apps/projects_claude/claudeapps/shared/* /var/www/html/claudeapps/shared/
```

## Quellpfade

| Was | Quelle | Deploy-Ziel |
|-----|--------|-------------|
| Landing-Page | `projects_claude/claudeapps/index.html` | `/var/www/html/claudeapps/index.html` |
| Back-Button | `projects_claude/claudeapps/shared/back-button.js` | `/var/www/html/claudeapps/shared/back-button.js` |
| App-Registry | `projects_claude/claudeapps/shared/apps.js` | `/var/www/html/claudeapps/shared/apps.js` |
