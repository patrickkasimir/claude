#!/usr/bin/env python3
"""Gemeinsame, READ-ONLY Upgrade-Risiko-Prüfungen (statisch, ohne Zielversion).

Wird genutzt von:
- odoo/extract_upgrade.py  (Analyzer-Reiter „Upgradefähigkeit")
- odoo/updatesets/run.py    (lint)  -> DRY

Client-Interface (duck-typed; OdooClient erfüllt es bereits):
  c.search_read(model, domain, fields=None, **kw) -> list[dict]
  c.read(model, ids, fields=None)                 -> list[dict]
  c.fields_get(model)                             -> dict

Findet (statisches Risiko, KEINE Garantie):
- tote Feld-Referenzen in ir.rule / Feld-Domains / ir.filters  (sicher)
- fragile Studio-Views mit Anker an Kern-Layout-Containern div[@name=…]
- manuelle Compute-/Related-Felder mit Kernfeld-Bezug

Versionsspezifische Entfernungen (z. B. company_type) sieht erst der
Vergleich gegen die hochgezogene Test-DB (Snapshot/Diff) – nicht hier.
"""
import re

CATEGORY = "Upgradefähigkeit"
DOMAIN_OPS = {"=", "!=", ">", ">=", "<", "<=", "=?", "like", "not like", "=like",
              "ilike", "not ilike", "=ilike", "in", "not in", "child_of",
              "parent_of", "any", "not any"}
# Echte Domain-Leaves: ('feld','operator',wert) – 2. Token MUSS Operator sein
# (verhindert Fehlalarme bei Werte-Tupeln wie ('out_invoice','out_refund')).
_DOM_RE = re.compile(r"""\(\s*['"]([\w.]+)['"]\s*,\s*['"]([^'"]+)['"]\s*,""")


def _domain_fields(s):
    return {m.group(1).split(".")[0] for m in _DOM_RE.finditer(s or "")
            if m.group(2) in DOMAIN_OPS}


def run(c):
    """Gibt eine Liste von Befunden zurück (Dicts: severity/category/kind/title/
    detail/recommendation/ref)."""
    cache = {}

    def flds(model):
        if model not in cache:
            try:
                cache[model] = set(c.fields_get(model).keys())
            except Exception:
                cache[model] = None
        return cache[model]

    findings = []

    def add(sev, kind, title, detail, rec, ref=""):
        findings.append({"severity": sev, "category": CATEGORY, "kind": kind,
                         "title": title, "detail": detail,
                         "recommendation": rec, "ref": ref})

    # --- 1) Tote Feld-Referenzen (sicher problematisch) ---
    rules = c.search_read("ir.rule", [("domain_force", "!=", False)],
                          fields=["name", "model_id", "domain_force"])
    rmods = {m["id"]: m["model"] for m in c.read(
        "ir.model", list({r["model_id"][0] for r in rules if r["model_id"]}), ["model"])}
    for r in rules:
        tech = rmods.get(r["model_id"][0]) if r["model_id"] else None
        f = flds(tech) if tech else None
        if not f:
            continue
        miss = sorted(x for x in _domain_fields(r["domain_force"]) if x not in f)
        if miss:
            add("critical", "dead_ref", "Datensatzregel referenziert fehlende Felder",
                f"Regel '{r['name']}' ({tech}) nutzt {miss} – existiert nicht auf dem Modell.",
                "Domain bereinigen oder Regel deaktivieren (bricht beim Upgrade/Zugriff).",
                f"ir.rule:{tech}")

    for fr in c.search_read("ir.model.fields", [("domain", "!=", False), ("domain", "!=", "[]")],
                            fields=["model", "name", "domain"]):
        f = flds(fr["model"])
        if not f:
            continue
        miss = sorted(x for x in _domain_fields(fr["domain"]) if x not in f)
        if miss:
            add("critical", "dead_ref", "Feld-Domain referenziert fehlende Felder",
                f"{fr['model']}.{fr['name']}: {miss}",
                "Domain des Feldes anpassen.", f"{fr['model']}.{fr['name']}")

    for fl in c.search_read("ir.filters", [("domain", "!=", False), ("domain", "!=", "[]")],
                            fields=["name", "model_id", "domain"]):
        tech = fl["model_id"] if isinstance(fl["model_id"], str) else None
        f = flds(tech) if tech else None
        if not f:
            continue
        miss = sorted(x for x in _domain_fields(fl["domain"]) if x not in f)
        if miss:
            add("warning", "dead_ref", "Gespeicherter Filter referenziert fehlende Felder",
                f"Filter '{fl['name']}' ({tech}): {miss}",
                "Filter korrigieren oder entfernen.", f"ir.filters:{tech}")

    # --- 2) Fragile Studio-Views (Anker an Kern-Layout-Containern) ---
    for v in c.search_read("ir.ui.view", [("inherit_id", "!=", False), ("name", "like", "%Studio%")],
                           fields=["name", "model", "arch"]):
        containers = set(re.findall(r"div\[@name='([^']+)'\]", v["arch"] or ""))
        risky = sorted(x for x in containers if not (x.startswith("studio_") or x.startswith("x_")))
        if risky:
            add("warning", "fragile_view", "Studio-View hängt an Kern-Layout-Container",
                f"{v['name']} ({v['model']}) ankert an {risky}.",
                "Standardfelder nicht verschieben/verstecken; nur eigene Tabs/Felder "
                "HINZUFÜGEN. Solche Anker entfallen bei Kern-Umbauten → ganze View wird verworfen.",
                v["model"])

    # --- 3) Manuelle Compute-/Related-Felder mit Kernfeld-Bezug ---
    for fr in c.search_read("ir.model.fields",
                            ["&", ("state", "=", "manual"), "|", ("compute", "!=", False), ("related", "!=", False)],
                            fields=["model", "name", "compute", "related"]):
        refs = set()
        if fr["related"]:
            refs.add(fr["related"].split(".")[0])
        if fr["compute"]:
            refs |= set(re.findall(r"record\.([a-z]\w+)", fr["compute"]))
        core = sorted(r for r in refs if not r.startswith("x_") and r != "id")
        if core:
            add("info", "core_ref", "Eigenes Rechenfeld nutzt Kernfelder",
                f"{fr['model']}.{fr['name']} referenziert {core}.",
                "Bricht, falls ein Kernfeld in der Zielversion entfällt; defensiv absichern "
                "(z. B. Existenz des Kernfelds via fields_get prüfen, bevor zugegriffen wird).",
                f"{fr['model']}.{fr['name']}")

    return findings


def summarize(findings):
    """Zähler + statischer Risiko-/Reife-Score (gentle gewichtet, 0..100)."""
    by_sev = {s: sum(1 for f in findings if f["severity"] == s)
              for s in ("critical", "warning", "info")}
    counts = {k: sum(1 for f in findings if f["kind"] == k)
              for k in ("dead_ref", "fragile_view", "core_ref")}
    penalty = 8 * by_sev["critical"] + 3 * by_sev["warning"] + 1 * by_sev["info"]
    score = max(0, 100 - penalty)
    grade = ("A – sehr gut" if score >= 85 else "B – gut" if score >= 70 else
             "C – mittel" if score >= 50 else "D – schwach" if score >= 30 else "E – kritisch")
    return {"by_severity": by_sev, "counts": counts, "score": score, "grade": grade}
