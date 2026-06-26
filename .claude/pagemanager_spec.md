---
name: pagemanager-spec
description: "Lebende Spezifikation des generischen PageManager-Systems — was generisch ist, was app-spezifisch bleibt, aktueller Baustand"
metadata: 
  node_type: memory
  type: project
  originSessionId: db608e83-4a01-49d5-9e23-582b0c27bdad
---

# PageManager — Generische CRUD-Page-Architektur

**Ziel:** Jede neue CRUD-Seite (Tasks, Benutzer, Incidents, …) wird durch eine PageManager-Instanz mit Konfigurations-Objekt erzeugt. Kein duplizierter Code.

**Why:** Tasks und Benutzer haben ~800 Zeilen identische JS-Logik zweimal. Incident Management wird der erste sauber generische Aufbau, danach werden Tasks und Benutzer migriert.

**How to apply:** Vor jeder neuen CRUD-Seite diese Spec lesen. Alles unter "Generisch" kommt aus PageManager. Alles unter "App-spezifisch" wird als Konfigurations-Objekt übergeben.

---

## Status

| Seite | Stand |
|-------|-------|
| Task Management | Vollständig implementiert, NOCH NICHT migriert |
| Benutzer | Vollständig implementiert, NOCH NICHT migriert |
| Incident Management | **NÄCHSTER SCHRITT** — erster generischer Aufbau |

---

## Was ist GENERISCH (kommt aus PageManager)

### Toolbar
- `+ Neu` Button (Label konfigurierbar, Default: "+ Neu")
- Odoo-Suchfeld mit Chips (Feld → Wert → Chip, Enter filtert sofort, ✕ entfernt)
- Kanban-Toggle (⊞) + Gruppierungs-▾ Dropdown
- Listen-Toggle (☰) + Spalten-▾ Dropdown
- ▾ erscheint/verschwindet je nach aktiver Ansicht
- Button-Gruppe: vollrund wenn inaktiv, links-rund wenn aktiv (verbindet mit ▾)

### Kanban
- Spalten dynamisch nach konfiguriertem Gruppierungsfeld
- Spalte "Ohne [Feld]" für NULL-Werte
- Drag & Drop zwischen Spalten (reines JS, Ghost-Karte, Ziel-Highlight, PUT auf Drop)
- Klick auf Karte → Detail öffnen
- Karten-Inhalt: **app-spezifisch** (Render-Funktion)

### Listenansicht
- `table-layout: fixed; width: max-content`
- Checkbox (Einzelzeile + Alle auswählen)
- Spalten ein-/ausblenden (localStorage, Key: `apppp_[entity]_col_settings`)
- Spaltenbreite per Drag-Resize (mousedown/move/up, gespeichert)
- Spalten-Reihenfolge per Drag & Drop (HTML5 dragstart/drop, gespeichert)
- Sortierung per Header-Klick: asc → desc → keine, aktive Spalte grün + Pfeil
- Inline-Editing: Klick auf Zelle → input oder select, Enter/Blur speichert
- Massenbearbeitung bei Mehrfachauswahl: Bestätigungs-Dialog
- Zeilen-Highlight bei Selektion
- Zeilen-Klick → Detail öffnen (nicht wenn auf editierbare Zelle geklickt)

### Detailformular
- Breadcrumb-Navigation (zurück zur Liste)
- 2-Spalten-Grid (`.detail-grid 1fr 1fr`), Sections (`.detail-section`)
- Felder: **app-spezifisch**
- Speichern / Löschen (roter Bestätigungs-Dialog) / Abbrechen
- Neu + Bearbeiten über dasselbe Formular
- Formular-Validierung (Pflichtfelder)

### Chatter-Panel
- 640px, sticky rechts neben Formular
- Neueste Einträge oben, Timestamp + Text + Dateilink
- Eintrag löschen per Hover-✕
- "+ Notiz" Button → Compose-Bereich (standardmäßig verborgen)
- Datei-Upload pro Notiz (multipart, max 20MB)
- Strg+Enter zum Senden
- Endpoints: `GET/POST/DELETE /[entity]/:id/notes`

### Allgemein
- Toast-Nachrichten (Erfolg grün, Fehler rot, 3s)
- Bestätigungs-Modal: Titel + Text + Button-Label + Farbe konfigurierbar
- `showPage()` schaltet zwischen Seiten um

---

## Was ist APP-SPEZIFISCH (als Konfigurations-Objekt)

```javascript
PageManager({
  // Identifikation
  entity: 'incidents',          // URL-Schlüssel, localStorage-Prefix
  apiPath: '/incidents',        // relativ zur API-Basis

  // Toolbar
  newLabel: '+ Neu',            // Button-Text

  // Spalten (für Listenansicht + Suchfeld)
  columns: [
    { key: 'title',    label: 'Titel',      defaultOn: true,  width: 200, searchable: true },
    { key: 'severity', label: 'Schweregrad', defaultOn: true, width: 120 },
    // ...
  ],

  // Gruppierungsoptionen für Kanban
  groupByOptions: [
    { key: 'status',   label: 'Status' },
    { key: 'severity', label: 'Schweregrad' },
  ],
  defaultGroup: 'status',

  // Kanban-Karten-Render-Funktion
  renderCard: (item, users) => `<div>...</div>`,

  // Detailformular-HTML (wird in den Formular-Bereich eingefügt)
  renderForm: (item, users) => `<div class="detail-section">...</div>`,

  // Felder für Odoo-Suchfeld
  searchFields: [
    { key: 'title',    label: 'Titel',  type: 'text' },
    { key: 'status',   label: 'Status', type: 'enum', values: ['offen','gelöst'] },
  ],

  // Welche Felder sind inline-editierbar (Liste)
  inlineEditFields: ['status', 'severity', 'user_id'],

  // Hooks (optional)
  onSave:   (data) => data,     // Daten vor POST/PUT transformieren (z.B. Priorität berechnen)
  onOpen:   (item) => {},       // beim Öffnen des Detailformulars
})
```

---

## Geplante Dateistruktur

```
apppp/
  index.html          — Shell: Sidebar, PageManager-Klasse, App-Instanzen
  pages/
    tasks.js           — Tasks-Konfiguration
    incidents.js       — Incidents-Konfiguration
    users.js           — Benutzer-Konfiguration
```

Oder alles in einer Datei (Single-HTML) — Entscheidung offen.

---

## Offene Entscheidungen

- [ ] Single-HTML oder aufgeteilte Dateien?
- [ ] PageManager als ES6-Klasse oder Factory-Funktion?
- [ ] Incident-Felder festlegen (mit Patrick)
