#!/usr/bin/env python3
"""Advisor – konsolidiert die Analyse zu einem Regelkatalog + Health-Score.

Liest die JSON-Ausgaben der vier Extraktoren (analysis/processes/technical/
security) und wertet sie gegen einen Regelkatalog aus. Jede ausgelöste Regel
wird zu einem Befund mit Schweregrad, Kategorie und Handlungsempfehlung.
Daraus wird ein gewichteter Gesamt-Score (0–100) berechnet.

Portabel: rein dateibasiert (keine API). Muss NACH den Extraktoren laufen.
Ausgabe (gitignored):  odoo/report/advisor.js  (window.ODOO_ADVISOR)
Aufruf:  python3 odoo/advisor.py
"""
import os
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPORT = Path(os.environ.get("ODOO_OUT_DIR") or (HERE / "report"))

SEV_WEIGHT = {"critical": 15, "warning": 6, "info": 1}
SEV_RANK = {"critical": 0, "warning": 1, "info": 2}
# Sicherheit wiegt schwerer, Datenqualität leichter (für den Gesamt-Score)
CAT_WEIGHT = {"Sicherheit": 1.5, "Wartbarkeit": 1.0, "Konfiguration": 1.0,
              "Datenqualität": 0.6, "Upgradefähigkeit": 0.5}


def load(name):
    p = REPORT / name
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def main() -> int:
    A = load("analysis.json")
    P = load("processes.json")
    T = load("technical.json")
    S = load("security.json")
    U = load("upgrade.json")
    if not any([A, P, T, S]):
        print("Keine Analyse-Daten gefunden – zuerst die Extraktoren laufen lassen.")
        return 1

    findings = []

    def add(fid, sev, cat, title, detail, rec):
        findings.append({"id": fid, "severity": sev, "category": cat,
                         "title": title, "detail": detail, "recommendation": rec})

    # ───────────────── Sicherheit ─────────────────
    users = S.get("users", {})
    intN = users.get("internal_active") or 0
    priv = S.get("privileged", {})
    privN = max((v for v in priv.values()), default=0)
    if intN and privN:
        ratio = privN / intN
        if privN == intN and intN > 1:
            add("SEC-ADMIN-ALL", "critical", "Sicherheit", "Alle Benutzer sind Voll-Admins",
                f"{privN} von {intN} internen Benutzern haben volle Administrationsrechte (Einstellungen).",
                "Admin-Rechte auf 1–2 Personen beschränken; übrige auf passende Rollen umstellen.")
        elif ratio >= 0.5:
            add("SEC-ADMIN-MANY", "warning", "Sicherheit", "Viele Voll-Admins",
                f"{privN} von {intN} internen Benutzern haben volle Administrationsrechte.",
                "Voll-Admin-Rechte möglichst wenigen Personen geben; sonst Organisationsrollen nutzen.")
    if privN == 1:
        add("SEC-BUS-FACTOR", "info", "Sicherheit", "Nur ein Voll-Admin",
            "Nur eine Person hat volle Administrationsrechte – Ausfallrisiko.",
            "Eine zweite Person mit Admin-Rechten vorsehen (Ausfallsicherheit / Vier-Augen).")
    twofa = users.get("with_2fa")
    if twofa is not None and intN and twofa < intN:
        add("SEC-2FA", "warning", "Sicherheit", "Benutzer ohne Zwei-Faktor-Authentifizierung",
            f"{intN - twofa} von {intN} internen Benutzern ohne 2FA.",
            "2FA verpflichtend aktivieren – besonders für Admins.")
    broad = S.get("rules", {}).get("broad", [])
    if broad:
        add("SEC-BROAD", "critical", "Sicherheit", "Globale Regeln ohne Einschränkung",
            f"{len(broad)} globale Datensatzregel(n) gewähren Zugriff auf ALLE Datensätze: " +
            ", ".join(b.get("name", "") for b in broad[:4]) + ".",
            "Domains der Regeln einschränken (z. B. auf Unternehmen/Eigentümer).")
    noacc = S.get("models_without_access", [])
    if noacc:
        add("SEC-NOACCESS", "warning", "Sicherheit", "Custom-Modelle ohne Zugriffsregel",
            "Ohne Access-Rule: " + ", ".join(noacc) + ".",
            "Für jedes Custom-Modell explizite Zugriffsrechte (ir.model.access) definieren.")
    if users.get("internal_inactive"):
        add("SEC-INACTIVE", "info", "Sicherheit", "Deaktivierte Benutzer vorhanden",
            f"{users['internal_inactive']} deaktivierte interne Benutzer.",
            "Nicht mehr benötigte Benutzer archivieren/entfernen.")

    # ───────────────── Wartbarkeit ─────────────────
    cf = T.get("custom_fields", [])
    nohelp = [f for f in cf if not f.get("help")]
    if nohelp:
        sev = "warning" if len(nohelp) >= 5 else "info"
        add("MNT-FIELD-HELP", sev, "Wartbarkeit", "Custom-Felder ohne Hilfetext",
            f"{len(nohelp)} von {len(cf)} benutzerdefinierten Feldern ohne Hilfetext.",
            "Hilfetexte in Studio pflegen – erleichtert Wartung und Übergabe.")
    sac = T.get("server_actions", {}).get("custom", [])
    if sac:
        add("MNT-SERVERACTIONS", "info", "Wartbarkeit", "Eigene Server-Aktionen (Code)",
            f"{len(sac)} eigene Server-Aktionen, teils mit Python-Code.",
            "Eigene Logik dokumentieren und bei Odoo-Updates testen.")
    cm = T.get("custom_models", [])
    if cm:
        add("MNT-CUSTOMMODELS", "info", "Wartbarkeit", "Custom-Modelle vorhanden",
            "Eigene Modelle: " + ", ".join(m.get("model", "") for m in cm) + ".",
            "Custom-Modelle dokumentieren; bei Migration zuerst übertragen.")
    studio_total = sum(s.get("count", 0) for s in T.get("studio_footprint", []))
    if studio_total > 25:
        add("MNT-STUDIO-SIZE", "info", "Wartbarkeit", "Umfangreiches Studio-Customizing",
            f"{studio_total} per Studio angepasste Objekte.",
            "Studio-Anpassungen dokumentieren und bei Odoo-Updates gezielt testen.")
    custom_auto = sorted({a.get("model") for a in P.get("automations", []) if (a.get("model") or "").startswith("x_")})
    if custom_auto:
        add("MNT-CUSTOM-AUTO", "info", "Wartbarkeit", "Automatisierungen auf Custom-Modellen",
            "Betroffen: " + ", ".join(custom_auto) + ".",
            "Eigene Automatisierungen dokumentieren; bei Migration mitnehmen.")

    # ───────────────── Konfiguration ─────────────────
    for p in P.get("pipelines", []):
        names = [(s.get("name") or "").lower() for s in p.get("stages", [])]
        dups = sorted(set(n for n in names if names.count(n) > 1))
        if dups:
            add(f"CFG-DUPSTAGE-{p.get('model')}", "warning", "Konfiguration",
                f"Doppelte Stadien in „{p.get('label')}“",
                f"Mehrfach vorhandene Stadien: {', '.join(dups)}.",
                "Stadien zusammenführen oder team-/projektspezifisch trennen.")
        if len(p.get("stages", [])) > 12:
            add(f"CFG-MANYSTAGE-{p.get('model')}", "warning", "Konfiguration",
                f"Sehr viele Stadien in „{p.get('label')}“",
                f"{len(p['stages'])} Stadien.",
                "Prüfen, ob die Stadien getrennt (pro Team/Projekt) geführt werden sollten.")
        if p.get("model") == "crm.stage" and not any(s.get("is_won") for s in p.get("stages", [])):
            add("CFG-CRM-NOWON", "warning", "Konfiguration", "CRM-Pipeline ohne „Gewonnen“-Phase",
                "Keine Phase ist als „is_won“ markiert.",
                "Gewonnen-Phase markieren – sonst sind Gewinnquoten/Reports verfälscht.")
        if len(p.get("stages", [])) > 2 and not any(s.get("fold") for s in p.get("stages", [])):
            add(f"CFG-NOFOLD-{p.get('model')}", "info", "Konfiguration",
                f"Kein eingeklapptes Endstadium in „{p.get('label')}“",
                "Keine Spalte ist als „fold“ (eingeklappt) markiert.",
                "Abschluss-Stadien (Erledigt/Abgebrochen) als „fold“ markieren – hält das Kanban übersichtlich.")
    autos = P.get("automations", [])
    inactive_auto = [a for a in autos if not a.get("active")]
    inactive_cron = [c for c in P.get("crons", []) if not c.get("active")]
    if inactive_auto or inactive_cron:
        add("CFG-INACTIVE-AUTO", "warning", "Konfiguration", "Inaktive Automatisierungen",
            f"{len(inactive_auto)} inaktive Automatisierungsregel(n), {len(inactive_cron)} inaktive Cron-Job(s).",
            "Inaktive Regeln prüfen: bewusst deaktiviert oder Altlast?")
    cfg = P.get("config", {})
    jn = [(j.get("name") or "").lower() for j in cfg.get("journals", [])]
    if jn and len(jn) != len(set(jn)):
        add("CFG-MULTICOMPANY", "info", "Konfiguration", "Mehrfach-Konfiguration (Multi-Company)",
            "Gleichnamige Journale/Steuerpositionen – typisch für mehrere Unternehmen.",
            "Kein Fehler; bei Auswertungen Unternehmen mitfiltern.")
    if len(cfg.get("payment_terms", [])) > 8:
        add("CFG-PAYTERMS", "info", "Konfiguration", "Viele Zahlungsbedingungen",
            f"{len(cfg['payment_terms'])} Zahlungsbedingungen definiert.",
            "Ungenutzte Zahlungsbedingungen ausmisten.")

    # ───────────────── Datenqualität ─────────────────
    empty = [b for b in A.get("business_counts", []) if b.get("count") == 0]
    if empty:
        add("DQ-EMPTY", "info", "Datenqualität", "Ungenutzte Geschäftsobjekte",
            "Ohne Datensätze: " + ", ".join(f"{b['label']}" for b in empty) + ".",
            "Prüfen, ob die zugehörige App/Funktion wirklich gebraucht wird.")
    total_mails = sum(m.get("count", 0) for m in P.get("mail_templates", []))
    if total_mails > 40:
        add("DQ-MAILVOL", "info", "Datenqualität", "Viele Mail-Vorlagen",
            f"{total_mails} aktive Mail-Vorlagen.",
            "Selten genutzte Vorlagen aufräumen, um Übersicht zu behalten.")

    # ───────────────── Upgradefähigkeit (aus upgrade.json) ─────────────────
    # Alle Einzelbefunde direkt einbinden – CAT_WEIGHT 0.2 verhindert,
    # dass statische Risiko-Indikatoren den Gesamt-Score unverhältnismäßig belasten.
    for i, f in enumerate(U.get("findings", [])):
        add(f"UPG-{i}", f["severity"], "Upgradefähigkeit",
            f["title"], f["detail"], f["recommendation"])

    # ───────────────── Score & Aggregation ─────────────────
    def grade_of(sc):
        return ("sehr gut" if sc >= 85 else "gut" if sc >= 70 else
                "verbesserungswürdig" if sc >= 50 else "kritisch")

    # Gesamt-Score: Schweregrad × Kategorie-Gewicht
    penalty = sum(SEV_WEIGHT.get(f["severity"], 0) * CAT_WEIGHT.get(f["category"], 1.0) for f in findings)
    score = max(0, round(100 - penalty))
    grade = grade_of(score)
    by_sev = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV_WEIGHT}

    # Teil-Score je Kategorie (eigenständig, ohne Kategorie-Gewichtung)
    cats = sorted({f["category"] for f in findings})

    def cat_score(c):
        p = sum(20 if f["severity"] == "critical" else 10 if f["severity"] == "warning" else 3
                for f in findings if f["category"] == c)
        return max(0, 100 - p)

    by_cat = {c: {"count": sum(1 for f in findings if f["category"] == c),
                  "score": cat_score(c), "grade": grade_of(cat_score(c))} for c in cats}
    # Upgradefähigkeit-Teil-Score direkt aus upgrade.json übernehmen (eigene Skala)
    if "Upgradefähigkeit" in by_cat and U.get("score") is not None:
        upg_sc = U["score"]
        by_cat["Upgradefähigkeit"]["score"] = upg_sc
        by_cat["Upgradefähigkeit"]["grade"] = grade_of(upg_sc)
    findings.sort(key=lambda f: (SEV_RANK.get(f["severity"], 9), f["category"]))

    data = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "server": (S or T or P or A).get("server", {}),
        "score": score, "grade": grade,
        "by_severity": by_sev, "by_category": by_cat,
        "findings": findings,
    }
    REPORT.mkdir(exist_ok=True)
    (REPORT / "advisor.js").write_text(
        "// Automatisch erzeugt von odoo/advisor.py - nicht manuell editieren.\n"
        "window.ODOO_ADVISOR = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8")
    (REPORT / "advisor.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Advisor geschrieben →", REPORT / "advisor.js")
    print(f"  Health-Score : {score}/100 ({grade})")
    print(f"  Befunde      : {len(findings)}  (kritisch {by_sev['critical']}, "
          f"Warnung {by_sev['warning']}, Info {by_sev['info']})")
    print("  Teil-Scores  : " + ", ".join(f"{c} {by_cat[c]['score']}" for c in cats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
