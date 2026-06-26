---
name: app-template
description: "Pflichtstruktur für jede neue CRUD-Page in Apppp — Kanban, Liste, Detail, Chatter, Suche, Drag & Drop, alle Toolbar-Elemente"
metadata: 
  node_type: memory
  type: reference
  originSessionId: db608e83-4a01-49d5-9e23-582b0c27bdad
---

# Standard App-Page Template (Apppp)

Jede neue CRUD-Seite (Tasks, Benutzer, zukünftige Entitäten) bekommt **dieselbe Vollstruktur**. Nichts weglassen.

## 1. Toolbar (immer vollständig)

```html
<div id="[entity]-toolbar">
  <div id="[entity]-toolbar-left">
    <button class="btn btn-primary" id="btn-new-[entity]">+ Neu</button>
  </div>
  <div id="[entity]-toolbar-center">
    <!-- Odoo-style Suchfeld mit Chips -->
    <div id="[entity]-search-wrap">
      <div id="[entity]-search-chips"></div>
      <input id="[entity]-search-input" type="text" placeholder="Suchen…" autocomplete="off" />
      <div id="[entity]-search-dropdown"></div>
    </div>
  </div>
  <div id="[entity]-toolbar-right">
    <!-- Kanban/Listen-Toggle: CSS über ID-Selektoren, KEIN inline-style!
         #[entity]-view-kanban { border-radius: 6px 0 0 6px; }
         #[entity]-view-list   { border-radius: 0 6px 6px 0; margin-left: -1px; }
         Aktiver Button: .active Klasse hinzufügen/entfernen beim Toggle -->
    <!-- Kanban-View mit Gruppierungs-Dropdown -->
    <div id="[entity]-kanban-view-wrap">
      <button class="btn btn-ghost btn-icon active" id="[entity]-view-kanban">⊞</button>
      <button id="[entity]-sort-toggle">▾</button>
      <div id="[entity]-sort-menu">
        <div class="sort-label">GRUPPIERUNG</div>
        <!-- Optionen je nach Entität -->
      </div>
    </div>
    <!-- Listen-View mit Spalten-Selektor -->
    <div id="[entity]-list-view-wrap">
      <button class="btn btn-ghost btn-icon" id="[entity]-view-list">☰</button>
      <button id="[entity]-col-vis-toggle">▾</button>
      <!-- Spalten-Dropdown (Column-Visibility-Popup) -->
    </div>
  </div>
</div>
```

## 2. Kanban

- **Drag & Drop** zwischen Spalten (mousedown/mousemove/mouseup — kein externes Library)
- Karten zeigen: Avatar/Icon, Hauptfeld, Schlüsselfelder, Status-Badge
- Spalten nach Gruppierungsfeld; Spalte "Ohne [Feld]" für NULL-Werte
- Klick auf Karte → Detail öffnen

## 3. Listenansicht

- `<table>` mit `<thead>` / `<tbody>`
- Erste Spalte: Checkbox (`sel-all` / Zeilen-Checkboxen) für Bulk-Actions
- Spalten ein-/ausblenden via Column-Visibility-Popup (localStorage-gespeichert, Key: `apppp_[entity]_col_settings`)
- **Tabellen-CSS:** `table-layout: fixed; width: max-content` — Spalten behalten ihre Breite unabhängig voneinander, kein automatisches Stauchen
- **Spaltenbreite änderbar:** jedes `<th>` hat `<span class="th-label">` + `<div class="col-resizer">`, mousedown/move/up Listener, Breite in `colSettings.widths[key]` gespeichert
- **Spalten-Reihenfolge per Drag:** `th.draggable=true`, dragstart/dragover/drop Events, Reihenfolge in `colSettings.order` gespeichert
- **Sortierung** per Klick auf `.th-label`: State `[entity]SortCol` / `[entity]SortDir`, CSS-Klassen `sort-asc` / `sort-desc` auf `<th>`, dreistufig: asc → desc → keine
- Klick auf Zeile → Detail öffnen

## 4. Odoo-Style Suchfeld

Zwei-Stufen-System:
1. Nutzer tippt Begriff
2. Dropdown zeigt verfügbare **Felder** (z.B. Name, Status, Abteilung)
3. Klick auf Feld (oder Enter) → Chip `Feld: Begriff` wird erstellt, Ansicht filtert sofort
4. Chips können per ✕ entfernt werden
5. Wenn kein Feld gewählt + Enter → sucht im ersten/Standard-Feld (Name/Titel)

## 5. Detail-Formular

```
┌─────────────────────────────────┬──────────────────────────────┐
│  Breadcrumb: [Entity] › Name    │                              │
│  Formular-Felder (2-Spalten-    │  Chatter-Panel (640px)       │
│  Grid, .detail-grid 1fr 1fr)    │  - "+ Notiz"-Button oben     │
│  .detail-section > h3 + Grid    │  - Feed: neueste oben        │
│                                 │  - Compose: auf Knopfdruck   │
│  Buttons: Speichern, Löschen,   │  - Datei-Upload pro Eintrag  │
│           Abbrechen             │                              │
└─────────────────────────────────┴──────────────────────────────┘
```

- Chatter-Feed nutzt `GET/POST/DELETE /[entity]/:id/notes` Endpoints
- Chatter-Panel width: 640px (= 2× eine Feldspalte im 1fr 1fr Grid)
- Compose standardmäßig ausgeblendet, erscheint per "+ Notiz"-Button

## 6. Avatar / Bild

- `avatarHtml(entity, size)` — zeigt `<img>` wenn Bild vorhanden, sonst farbigen Initialen-Kreis
- Upload via `POST /[entity]/:id/avatar` (multipart)
- Im Detail-Formular rechts oben großes Avatar + Upload-Button
- In Kanban-Karten: kleines Avatar links
- In Listenansicht: Avatar-Spalte (erste Spalte nach Checkbox)

## 7. Backend-Struktur (immer gleich)

```
GET    /[entity]              → alle
GET    /[entity]/:id          → einzeln
POST   /[entity]              → neu
PUT    /[entity]/:id          → aktualisieren
DELETE /[entity]/:id          → löschen
POST   /[entity]/:id/avatar   → Bild-Upload (multer)
GET    /[entity]/:id/notes    → Chatter-Einträge (chronologisch ASC)
POST   /[entity]/:id/notes    → Chatter-Eintrag + optionaler File-Upload
DELETE /[entity]/:id/notes/:noteId → löschen
```

## 8. localStorage-Keys (immer mit `apppp_`-Prefix)

- `apppp_[entity]_col_settings` — Spalten-Sichtbarkeit
- `apppp_[entity]_view` — aktive Ansicht (kanban/list)
- `apppp_[entity]_group` — aktive Gruppierung
- `apppp_settings` — globale App-Einstellungen

## 9. Design-System (nie abweichen)

```css
--bg: #1a1a2e
--surface: #16213e
--surface2: #0f3460
--accent: #4ade80
--border: #4ade8022
--text: #eee
--muted: #888
--danger: #f87171
--warn: #fbbf24
```

Klassen: `.btn`, `.btn-primary`, `.btn-ghost`, `.btn-sm`, `.btn-danger`, `.btn-icon`,
`.field`, `.detail-section`, `.detail-grid`, `.badge`, `.chip`

## 10. Drag & Drop (Kanban)

Rein in JS ohne Library:
- `mousedown` auf Karte → Ghost-Element erstellen, Original ausblenden
- `mousemove` → Ghost folgt Maus, Spalte unter Cursor highlighten
- `mouseup` → API-Call um Gruppierungsfeld zu updaten, neu rendern
- Ghost wird nach `mouseup` entfernt

**Why:** Der Nutzer (Patrick) erwartet konsistente Funktionalität in allen Pages. Fehlende Elemente werden explizit nachgefordert. Einmal richtig, immer richtig.

**How to apply:** Vor jeder neuen CRUD-Page diese Checkliste durchgehen. Keine Elemente weglassen "weil vielleicht nicht gebraucht" — alles rein.
