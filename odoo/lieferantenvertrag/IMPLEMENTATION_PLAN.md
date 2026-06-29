# Implementierungsplan: Lieferantenvertragsmanagement in Odoo 19 (Online) via XML-RPC

## Ziel

Aufbau eines Studio-kompatiblen Datenmodells für Lieferantenverträge (AVV, NDA,
Rahmenvertrag, Einzelvereinbarung) in einer Odoo-19-Online-Sandbox, per XML-RPC,
inklusive Mehrsprachigkeit für alle aktiven Sprachen und Verknüpfung zum
Einkaufsmodul (Purchase Orders / Purchase Agreements).

Hintergrund / Geschäftslogik: Rahmenverträge und Einzelvereinbarungen können mit
operativen Bestellungen (`purchase.order`) verknüpft sein (Mischform). Diese
Verknüpfung ist **optional** — Bestellungen ohne Vertragsbezug müssen weiterhin
möglich sein.

---

## Rahmenbedingungen (zwingend zu beachten)

- **Odoo Online (SaaS)**: kein Server-Dateisystem-Zugriff, kein eigenes
  Python-Modul deploybar. Alles muss über Standard-RPC-Modelle laufen:
  `ir.model`, `ir.model.fields`, `ir.model.fields.selection`, `ir.ui.view`,
  `base.automation`.
- **Odoo 19 — `translate`-Attribut**: Seit Odoo 19 ist `translate` an
  `ir.model.fields` ein **String-Wert** (z. B. `'standard'`, `'html_translate'`),
  **nicht mehr Boolean** (`True`/`False`). Vor dem ersten produktiven Schreiben
  unbedingt an einem unkritischen Testfeld gegen die Sandbox verifizieren, da
  viele Tutorials/Blogposts noch die alte Boolean-Syntax zeigen.
- **Übersetzungsspeicherung**: Übersetzte Werte liegen seit der JSONB-Umstellung
  direkt als JSON-Objekt in der jeweiligen Tabellenspalte (kein `ir.translation`
  mehr). Beim Lesen/Schreiben übersetzbarer Felder **immer**
  `context={'lang': '<code>'}` explizit mitgeben — sonst greift automatisch die
  Sprache des aufrufenden API-Users, und andere Sprachwerte können versehentlich
  überschrieben werden.
- **Namenskonvention**: Alle neuen Feldnamen mit Präfix `x_studio_` anlegen,
  damit das Ergebnis später nahtlos in Odoo Studio weiterbearbeitet werden kann.
  Kein anderes Präfix verwenden.
- **Kein Server-seitiges `_compute`**: Live berechnete Felder (z. B. ein
  "Smart Button" mit dynamischer Berechnung) sind per RPC nicht möglich.
  Verknüpfungen, die so wirken sollen, müssen über `base.automation` +
  Server-Action nachgebildet werden (UI-Konfiguration, kein eigenes Modul).

---

## Schritt 1 — Vorbereitung & Discovery

- Verbindung zu `/xmlrpc/2/common` (Auth) und `/xmlrpc/2/object` (Execute)
  aufbauen, Login testen.
- Aktive Sprachen abfragen: `res.lang.search_read([('active','=',True)],
  ['code','name'])`. Dies ist die einzige Quelle für "alle installierten
  Sprachen" — nicht hartkodieren.
- Vorhandene Felder auf `purchase.order` und `res.partner` sichten
  (`ir.model.fields.search_read`), um Namenskollisionen zu vermeiden.

## Schritt 2 — Datenmodell "Lieferantenvertrag"

- Neues Modell anlegen, technischer Name z. B. `x_lieferantenvertrag`.
- Felder (alle mit `x_studio_`-Präfix):
  - `x_studio_partner_id` — Many2one → `res.partner`
  - `x_studio_vertragstyp` — Selection: AVV / NDA / Rahmenvertrag /
    Einzelvereinbarung
  - `x_studio_parent_contract_id` — Many2one auf sich selbst (Einzelvereinbarung
    → Rahmenvertrag)
  - `x_studio_vertragsnummer` — Char
  - `x_studio_status` — Selection als Statusbar-Workflow: Entwurf / In Prüfung /
    Aktiv / Läuft aus / Beendet
  - `x_studio_start_date`, `x_studio_end_date` — Date
  - `x_studio_auto_renew` — Boolean
  - `x_studio_notice_days` — Integer (Kündigungsfrist)
  - `x_studio_responsible_id` — Many2one → `res.users`
  - `x_studio_notes` — Text, übersetzbar (`translate` korrekt als String setzen,
    siehe Rahmenbedingungen)
  - `x_studio_orders_ids` — Many2many → `purchase.order` (Befüllung über
    Automation, siehe Schritt 5 — kein manuelles Pflichtfeld für den User)

## Schritt 3 — Verknüpfung zum Einkauf

- Neues Feld auf `purchase.order`: `x_studio_lieferantenvertrag_id`
  (Many2one → `x_lieferantenvertrag`), **nicht required** — Bestellungen ohne
  Vertragsbezug müssen weiterhin möglich sein.
- Domain auf diesem Feld: nur Verträge anzeigen, deren `x_studio_partner_id`
  mit dem Lieferanten der Bestellung übereinstimmt
  (`[('x_studio_partner_id','=',partner_id)]`).

## Schritt 4 — Mehrsprachigkeit

Für **jede** aktive Sprache aus Schritt 1:

1. Feldbezeichnungen (`field_description`) der neuen Felder übersetzen.
2. Selection-Werte (Vertragstyp, Status) über `ir.model.fields.selection`
   pro Sprache übersetzen.
3. Bei Testdatensätzen: `x_studio_notes` pro Sprache befüllen — jeweils mit
   explizitem `context={'lang': code}` schreiben, nie ohne Sprachkontext.
4. Stichprobe: Sprache des Testnutzers wechseln, Datensatz erneut lesen,
   prüfen ob die sprachabhängigen Werte korrekt zurückgegeben werden.

## Schritt 5 — Automatisierungen (Ersatz für Server-Code)

- **Automation 1**: Trigger bei Erstellung/Änderung einer `purchase.order`,
  wenn `x_studio_lieferantenvertrag_id` gesetzt ist → zugehörige Bestellung in
  `x_studio_orders_ids` am verknüpften Vertrag ergänzen (Server-Action im
  Automation-Editor, keine externe Code-Datei).
- **Automation 2**: X Tage vor `x_studio_end_date` → Activity für den in
  `x_studio_responsible_id` hinterlegten Nutzer erzeugen (Erinnerung
  Vertragsende/-verlängerung).

## Schritt 6 — Views

- Formularansicht für `x_lieferantenvertrag` mit Statusbar (`x_studio_status`).
- Tab oder Smart Button auf dem Partnerformular (`res.partner`), der
  verknüpfte Verträge des jeweiligen Lieferanten anzeigt.
- Sichtbarkeit des Feldes `x_studio_orders_ids` ("Bestellungen") nur bei
  Vertragstyp Rahmenvertrag oder Einzelvereinbarung (Conditional/Invisible-
  Bedingung in der View).

## Schritt 7 — Validierung

- Je einen Testdatensatz pro Vertragstyp anlegen, inkl. mehrsprachiger Notizen.
- Bestellungen mit und ohne Vertragsbezug anlegen; Domain-Filter und
  Automation-Verhalten (Schritt 5) prüfen.
- Stichprobenhaft prüfen, dass alle Modelle/Felder/Views fehlerfrei in Odoo
  Studio (UI) sichtbar und weiter editierbar sind.

---

## Offene Verifikationspunkte für Claude Code

- Akzeptiert `ir.model.fields.create()` per RPC in dieser Odoo-19-Instanz den
  String-Wert für `translate` zuverlässig, oder gibt es noch Altverhalten
  (Boolean-Konvertierung)? → Erst an einem Testfeld prüfen, dann den Rest des
  Plans ausführen.
- Reihenfolge beachten: Modell muss existieren und ggf. ein kurzer
  Registry-Reload abgewartet werden, bevor Felder/Views darauf aufgebaut werden.
</content>
</invoke>
