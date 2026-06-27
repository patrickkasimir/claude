---
name: project-overview
description: "Apppp-Architektur — Backend Port/Pfade, nginx, pm2, Design-System, Deploy-Workflow"
metadata: 
  node_type: memory
  type: project
  originSessionId: db608e83-4a01-49d5-9e23-582b0c27bdad
---

# Apppp — Projekt-Übersicht

**Why:** Immer wieder gleiche Fragen zu Ports, Pfaden, Deploy vermeiden.
**How to apply:** Vor jedem Backend/nginx/Deploy-Task hier nachschlagen.

## Pfade

| Was | Pfad |
|-----|------|
| Frontend (Quell) | `/home/elija/apps/projects_claude/apppp/index.html` |
| Frontend (Deploy) | `/var/www/html/claudeapps/apppp/index.html` |
| Backend | `/home/elija/apps/apppp-backend/server.js` |
| DB | `/home/elija/apps/apppp-backend/tasks.db` |
| Uploads | `/home/elija/apps/apppp-backend/uploads/` |

**Deploy-Befehl:** `cp /home/elija/apps/projects_claude/apppp/index.html /var/www/html/claudeapps/apppp/index.html`
→ Nginx serviert statisch aus `/var/www/html/claudeapps/`, kein Neustart nötig

## Backend

- Port: **3003**
- pm2-Name: **apppp**
- API-Prefix live: `/claudeapps/apppp/api/`
- Neustart: `pm2 restart apppp`

## nginx (`/etc/nginx/sites-available/codetalk`)

```nginx
location /claudeapps/apppp/api/ {
    proxy_pass http://127.0.0.1:3003/;
    ...
}
location /claudeapps/ {
    alias /var/www/html/claudeapps/;
}
```

## Andere Apps

| App | pm2 | Port | Frontend |
|-----|-----|------|----------|
| taskmanager | taskmanager | 3002 | `/var/www/html/claudeapps/taskmanager/` |
| apppp | apppp | 3003 | `/var/www/html/claudeapps/apppp/` |
| sharehandling | sharehandling | 3004 | `/var/www/html/claudeapps/sharehandling/` |

**sharehandling** (Aktienregister): Backend `/home/elija/apps/sharehandling-backend/server.js`, DB `sharehandling.db`, API-Prefix `/claudeapps/sharehandling/api/`. nginx-Block siehe `sharehandling-backend/nginx-snippet.conf`. Frontend-Quelle `projects_claude/sharehandling/index.html`. Eigene Landing-Sektion „Finanzen".

## Landingpage

`/var/www/html/claudeapps/index.html` — Karten für alle Apps
