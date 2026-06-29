# Implementierungsplan: „Upgradefähigkeit" im Odoo-Analyzer

Ziel: den bestehenden Plattform-Analyzer (read-only, Extraktoren → JSON →
`advisor.py` Health-Score → Report-Reiter, Deploy via `update.sh`) um die Dimension
**Upgradefähigkeit** erweitern — proaktiv, datenminimiert, im bestehenden Muster.

Grundprinzip & ehrliche Grenze:
- **Analyzer = statische Upgrade-RISIKO-Analyse** einer laufenden Instanz, **ohne
  Zielversion** → findet tote Referenzen, fragile Anker, Kernfeld-Bezüge. Liefert
  einen Reife-/Risiko-Score, **keine Garantie**.
- **Versionsspezifische Entfernungen** (z. B. `company_type` in 19.3) und **stilles
  Verschwinden** (verworfene Studio-Views) sieht erst der **Vergleich gegen die
  hochgezogene Test-DB** → das ist Stufe 4.
- **DRY:** Prüf-Logik in ein gemeinsames Modul `upgrade_checks.py` (in `odoo/`), das
  sowohl `updatesets/run.py` (Lint) als auch der Analyzer-Extraktor nutzen.

Reihenfolge ist bindend: **eine Stufe fertig + abgenommen, dann die nächste.**

---

## Stufe 1 — Eigenständiger Reiter „Upgradefähigkeit" (ohne Health-Score-Einfluss)

**Ziel:** Ein separater Report-Reiter mit eigenem Teil-Score + Befundliste; der
Gesamt-Health-Score bleibt zunächst **unverändert**.

**Bausteine:**
- `odoo/upgrade_checks.py` — gemeinsame, read-only Prüf-Funktionen (aus `updatesets/run.py`
  `lint` extrahiert): tote Feld-Referenzen (ir.rule/Feld-Domains/ir.filters, präzises
  Domain-Parsing), fragile Studio-Views (Anker an Kern-Containern `div[@name=…]`),
  manuelle Compute-/Related-Felder mit Kernfeld-Bezug. Gibt strukturierte Befunde zurück.
- `odoo/extract_upgrade.py` — Extraktor im Muster der anderen: ruft `upgrade_checks`,
  schreibt `report/upgrade.json` (**nur Zähler + technische Namen**, keine Kundendaten):
  `{score, grade, by_severity, counts:{dead_refs, fragile_views, core_ref_fields},
  findings:[{id, severity, title, detail, rec, ref}]}`.
- `odoo/report/upgrade.html` + `report/upgrade.js` — eigener Reiter analog `advisor.html`
  (Teil-Score-Kachel + filterbare Befundliste nach Schweregrad).
- Navigation: „Upgradefähigkeit"-Link in **allen** `report/*.html` ergänzen.
- `update.sh`: `extract_upgrade.py` in die Extraktor-Schleife; `upgrade.*` mit deployen.
- Webapp (`webapp/app.py`): pro-Instanz-Analyse um den neuen Extraktor erweitern.

**Datenminimierung:** wie bestehende Extraktoren — keine Namen/E-Mails/Werte, nur
technische Bezeichner (model.field, view-Name) + Zähler.

**Verifikation / Abnahme:** Reiter erscheint, lädt `upgrade.json`, zeigt auf der
SOLVVision-Instanz plausible Befunde (die 9 toten Refs etc.); Gesamt-Score unverändert.

---

## Stufe 2 — Prüfen & Verfeinern (kein Score-Einfluss)

**Ziel:** Die Befunde gegen reale Instanz(en) validieren, **Fehlalarme ausschließen**,
Schweregrade/Texte schärfen.

**Inhalt:**
- Lauf gegen SOLVVision (und ggf. die `viaalia`-Analyzer-Instanz) → Befunde sichten.
- Sicherstellen: präzises Domain-Parsing (2. Token = Operator) → keine Werte-Tupel-
  Fehlalarme (die Lektion aus dem ir.rule-Vorfall). Studio-Container-Anker eng halten.
- Schweregrade festlegen: tote Refs = `critical`/`warning`, fragile Anker/Kernbezug = `warning`/`info`.
- Empfehlungstexte je Befund (was tun: bereinigen / re-anchor / Feld ersetzen).
- Doku/Hinweis im Reiter: „statisches Risiko, kein Ersatz für den Test-DB-Vergleich (Stufe 4)".

**Abnahme:** keine offensichtlichen Fehlalarme; Befunde sind handlungsleitend.

---

## Stufe 3 — Integration in den Health-Score

**Ziel:** Upgradefähigkeit fließt in den Gesamt-Score und die Kategorien ein.

**Bausteine:**
- `advisor.py`: neue Kategorie **„Upgradefähigkeit"** in `CAT_WEIGHT` (Gewicht z. B. 1.2);
  `advisor.py` liest `upgrade.json`-Befunde und mappt sie in `findings` (gleiche Struktur:
  id/severity/category/title/detail/rec). Damit erscheinen sie im Gesamt-Score, in
  `by_category` und im Advisor-Reiter automatisch.
- Gewichtung kalibrieren, damit der Gesamt-Score nicht „kippt".

**Abnahme:** Gesamt-Score + Kategorie-Teil-Score „Upgradefähigkeit" plausibel; Advisor-
Reiter zeigt die neue Kategorie.

---

## Stufe 4 (Erweiterung) — Upgrade-DB erstellen, analysieren & vergleichen

**Ziel:** Das **stille Verschwinden** sichtbar machen — Vergleich der Live-Instanz
gegen die hochgezogene Upgrade-Test-DB (verworfene Studio-Views, fehlende Tabs/x_-Felder).
Baut auf `updatesets/run.py snapshot`/`diff` auf, produktiviert im Analyzer/Webapp.

**Bausteine (eigene Unterstufen):**
- 4a. `snapshot` in `upgrade_checks` verallgemeinern (Tabs/Felder/aktive vererbte Views je
  Modell) → als „Baseline-Artefakt" der Live-Instanz speichern (datenminimiert).
- 4b. **Ziel-Instanz-Erfassung** in der Webapp: der Nutzer hinterlegt die von Odoo
  bereitgestellte Upgrade-Test-DB (URL/DB/Key, **transient** wie bisher, nicht gespeichert).
- 4c. **Diff-Lauf**: Baseline (alt) vs. Ziel (neu) → Befundliste „verworfene Studio-Views /
  fehlende Tabs / fehlende x_-Felder", Kern-Rauschen nur gezählt.
- 4d. Eigener Vergleichs-Report/Reiter „Upgrade-Vergleich" + (optional) Einfluss auf den
  Upgradefähigkeit-Score.

**Voraussetzung/Hinweis:** Der Nutzer muss bei Odoo das Test-Upgrade angefordert haben;
der Analyzer verbindet sich read-only mit beiden Instanzen. Das eigentliche „Anlegen" der
Test-DB macht Odoo (Upgrade-Service) — die Webapp führt durch den Prozess und übernimmt
Analyse + Vergleich.

**Abnahme:** Für eine Instanz mit Test-DB werden die verworfenen Studio-Views/Tabs korrekt
gelistet (am SOLVVision-19.3-Fall verifizierbar).

---

## Querschnitt
- Alles **read-only**; Schreibzugriffe bleiben dem Updateset-Workflow (`preupgrade_fixes.py`)
  vorbehalten — der Analyzer **meldet nur**.
- Wiederverwendung: `upgrade_checks.py` ist die einzige Quelle der Prüf-Logik.
- Verifikation jeder Stufe an einer echten Instanz, bevor die nächste beginnt.
