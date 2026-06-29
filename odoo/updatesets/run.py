#!/usr/bin/env python3
"""Update-Set-Runner für die Odoo-Anpassungen (Lieferantenvertrag + Projektplan).

Jede Anpassung ist ein CHANGESET mit:
  - apply: die idempotenten Build-Skripte (bestehende NN_*.py)
  - test : technische UND fachliche Prüfung per XML-RPC

Nutzung:
  python3 run.py list                 # Changesets auflisten
  python3 run.py test [ID|all]        # nur prüfen (Default: all)
  python3 run.py apply [ID|all]       # nur (neu) aufbauen
  python3 run.py apply-test [ID|all]  # aufbauen, dann prüfen
  python3 run.py verify               # = test all

Nach einem Odoo-Upgrade:  python3 run.py test all
-> zeigt je Changeset PASS/FAIL (technisch + fachlich). Bei FAIL: betroffenes
   Changeset 'apply' (idempotent) und erneut 'test'.

Zugangsdaten: ./.env (gitignored). Steuert auch die Build-Skripte (Subprozesse
erben die ODOO_*-Variablen), d.h. EINE .env für den ganzen Workflow.
"""
import os
import subprocess
import sys
from pathlib import Path

from odoo_client import OdooClient, load_env

BASE = Path(__file__).resolve().parent.parent          # .../odoo
HERE = Path(__file__).resolve().parent
load_env(HERE / ".env")                                 # ODOO_* -> os.environ (Subprozesse erben)


# --------------------------------------------------------------------------- #
class Check:
    """Sammelt einzelne Prüfpunkte eines Changesets."""
    def __init__(self):
        self.items = []          # (ok, label)

    def expect(self, cond, label):
        self.items.append((bool(cond), label))
        return bool(cond)

    @property
    def ok(self):
        return all(ok for ok, _ in self.items)


def apply_scripts(paths):
    """Führt die Build-Skripte (relativ zu odoo/) aus. Gibt (ok, kurzlog) zurück."""
    ok, logs = True, []
    for rel in paths:
        d, f = BASE / Path(rel).parent, Path(rel).name
        p = subprocess.run([sys.executable, f], cwd=d, env=os.environ,
                           capture_output=True, text=True)
        tail = (p.stdout or "")[-300:] + (p.stderr or "")[-300:]
        logs.append(f"    $ {rel}  ->  {'ok' if p.returncode == 0 else 'FEHLER'}")
        if p.returncode != 0:
            ok = False
            logs.append("      " + tail.strip().replace("\n", "\n      "))
    return ok, "\n".join(logs)


# --------------------------------------------------------------------------- #
# Tests (technisch = Objekte/Konfig vorhanden, fachlich = Verhalten stimmt)
# --------------------------------------------------------------------------- #
LV = "x_lieferantenvertrag"


def test_lv01(c):
    ch = Check()
    m = c.find_one("ir.model", [("model", "=", LV)], fields=["id"])
    ch.expect(m, "Modell x_lieferantenvertrag existiert")
    expected = ["x_studio_partner_id", "x_studio_vertragstyp", "x_studio_parent_contract_id",
                "x_studio_vertragsnummer", "x_studio_status", "x_studio_start_date",
                "x_studio_end_date", "x_studio_auto_renew", "x_studio_notice_days",
                "x_studio_responsible_id", "x_studio_notes", "x_studio_orders_ids",
                "x_studio_vertragsdokument"]
    have = {f["name"] for f in c.search_read("ir.model.fields",
            [("model", "=", LV), ("name", "like", "x_studio_%")], fields=["name"])}
    missing = [f for f in expected if f not in have]
    ch.expect(not missing, f"alle {len(expected)} Felder vorhanden"
              + (f" – fehlt: {missing}" if missing else ""))
    for fname, n in (("x_studio_vertragstyp", 4), ("x_studio_status", 5)):
        fid = c.find_one("ir.model.fields", [("model", "=", LV), ("name", "=", fname)], fields=["id"])
        cnt = c.search_count("ir.model.fields.selection", [("field_id", "=", fid["id"])]) if fid else 0
        ch.expect(cnt == n, f"{fname}: {n} Auswahlwerte (={cnt})")
    if m:
        ch.expect(c.search_count("ir.model.access", [("model_id", "=", m["id"])]) >= 3,
                  "Zugriffsrechte (>=3 Gruppen)")
    return ch


def test_lv02(c):
    ch = Check()
    f = c.find_one("ir.model.fields", [("model", "=", "purchase.order"),
                   ("name", "=", "x_studio_lieferantenvertrag_id")],
                   fields=["ttype", "relation", "required"])
    ch.expect(f, "Feld x_studio_lieferantenvertrag_id auf purchase.order")
    if f:
        ch.expect(f["ttype"] == "many2one" and f["relation"] == LV, "Typ many2one -> Vertrag")
        ch.expect(not f["required"], "nicht required (Bestellung ohne Vertrag erlaubt)")
    arch = c.execute("purchase.order", "get_view", view_type="form")["arch"]
    ch.expect("x_studio_lieferantenvertrag_id" in arch, "Feld im Bestellformular sichtbar")
    return ch


def test_lv03(c):
    ch = Check()
    fid = c.find_one("ir.model.fields", [("model", "=", LV), ("name", "=", "x_studio_partner_id")], fields=["id"])
    if fid:
        de = c.search_read("ir.model.fields", [("id", "=", fid["id"])], fields=["field_description"], context={"lang": "de_DE"})[0]["field_description"]
        en = c.search_read("ir.model.fields", [("id", "=", fid["id"])], fields=["field_description"], context={"lang": "en_US"})[0]["field_description"]
        ch.expect(de == "Lieferant" and en == "Vendor", f"Label de/en = {de}/{en}")
    vt = c.find_one("ir.model.fields", [("model", "=", LV), ("name", "=", "x_studio_vertragstyp")], fields=["id"])
    if vt:
        sel = c.find_one("ir.model.fields.selection", [("field_id", "=", vt["id"]), ("value", "=", "avv")], fields=["id"])
        de = c.search_read("ir.model.fields.selection", [("id", "=", sel["id"])], fields=["name"], context={"lang": "de_DE"})[0]["name"]
        en = c.search_read("ir.model.fields.selection", [("id", "=", sel["id"])], fields=["name"], context={"lang": "en_US"})[0]["name"]
        ch.expect(de == "AVV" and en == "DPA", f"AVV-Übersetzung de/en = {de}/{en}")
    return ch


def test_lv04(c):
    ch = Check()
    ch.expect(c.search_count("base.automation", [("name", "like", "LV:%")]) >= 2, "2 Automationen vorhanden")
    # fachlich: Wegwerf-Vertrag + Wegwerf-Bestellung -> Automation muss verknüpfen
    # eventuelle Altlasten aus früheren Läufen wegräumen
    _cleanup_healthcheck(c)
    comp = (c.find_one("res.partner", [("is_company", "=", True), ("supplier_rank", ">", 0)], fields=["id"])
            or c.find_one("res.partner", [("is_company", "=", True)], fields=["id"]))
    cid = poid = None
    try:
        if comp:
            cid = c.create(LV, {"x_name": "[HEALTHCHECK]", "x_studio_partner_id": comp["id"],
                                "x_studio_vertragstyp": "rahmenvertrag", "x_studio_status": "aktiv"})
            poid = c.create("purchase.order", {"partner_id": comp["id"], "partner_ref": "[HEALTHCHECK]",
                                               "x_studio_lieferantenvertrag_id": cid})
            orders = c.read(LV, [cid], ["x_studio_orders_ids"])[0]["x_studio_orders_ids"]
            ch.expect(poid in orders, "Automation verknüpft Bestellung mit Vertrag (fachlich)")
        else:
            ch.expect(False, "kein Firmenkontakt für Funktionstest gefunden")
    finally:
        _cleanup_healthcheck(c)
    return ch


def _cleanup_healthcheck(c):
    """Entfernt Wegwerf-Daten des Funktionstests (Bestellung erst stornieren)."""
    pos = c.search("purchase.order", [("partner_ref", "=", "[HEALTHCHECK]")])
    for po in pos:
        try:
            c.execute("purchase.order", "button_cancel", [po])
        except Exception:
            pass
        try:
            c.unlink("purchase.order", [po])
        except Exception:
            pass
    cs = c.search(LV, [("x_name", "=", "[HEALTHCHECK]")])
    if cs:
        try:
            c.unlink(LV, cs)
        except Exception:
            pass


def test_lv05(c):
    ch = Check()
    for vt in ("list", "form", "search"):
        try:
            c.execute(LV, "get_view", view_type=vt)
            ch.expect(True, f"View {vt} rendert")
        except Exception as e:
            ch.expect(False, f"View {vt} rendert ({str(e).splitlines()[-1][:50]})")
    ch.expect(c.find_one("ir.ui.menu", [("name", "=", "Lieferantenverträge")], fields=["id"]), "Menü Lieferantenverträge")
    parch = c.execute("res.partner", "get_view", view_type="form")["arch"]
    ch.expect("x_studio_contract_ids" in parch, "Partner-Tab im Formular")
    ch.expect("x_studio_contract_count" in parch, "Smart-Button im Formular")
    ch.expect("pdf_viewer" in c.execute(LV, "get_view", view_type="form")["arch"], "pdf_viewer im Vertragsformular")
    ct = c.find_one(LV, [("x_studio_partner_id", "!=", False)], fields=["x_studio_partner_id"])
    if ct:
        pid = ct["x_studio_partner_id"][0]
        cnt = c.read("res.partner", [pid], ["x_studio_contract_count"])[0]["x_studio_contract_count"]
        real = c.search_count(LV, [("x_studio_partner_id", "=", pid)])
        ch.expect(cnt == real, f"Smart-Button-Zähler korrekt ({cnt}={real}) (fachlich)")
    return ch


def test_pp01(c):
    ch = Check()
    tf = ["x_studio_gantt_show", "x_studio_gantt_undated", "x_studio_gantt_left",
          "x_studio_gantt_width", "x_studio_gantt_color", "x_studio_gantt_period", "x_studio_gantt_meta"]
    have = {f["name"] for f in c.search_read("ir.model.fields",
            [("model", "=", "project.task"), ("name", "like", "x_studio_gantt_%")], fields=["name"])}
    ch.expect(all(f in have for f in tf), "Hilfsfelder auf project.task")
    ch.expect(c.find_one("ir.actions.report", [("report_name", "like", "x_projektplan%")], fields=["id"]), "Bericht vorhanden")
    sa = c.find_one("ir.actions.server", [("name", "=", "Projektplan als PDF (Gantt)")], fields=["id"])
    ch.expect(sa, "Server-Action vorhanden")
    ch.expect("Ausgabe als PDF" in c.execute("project.project", "get_view", view_type="form")["arch"], "Button im Projektformular")
    # fachlich: SA auf Projekt mit datierten Aufgaben laufen lassen + Bericht-HTML rendern
    t = c.find_one("project.task", [("parent_id", "=", False), ("planned_date_begin", "!=", False),
                   ("date_deadline", "!=", False)], fields=["project_id"])
    if t and sa:
        pid = t["project_id"][0]
        try:
            c.execute("ir.actions.server", "run", [sa["id"]],
                      context={"active_model": "project.project", "active_id": pid, "active_ids": [pid]})
        except Exception:
            pass  # Marshalling des Rückgabe-Action wirft None-Fehler; Writes persistieren
        nshow = c.search_count("project.task", [("project_id", "=", pid), ("x_studio_gantt_show", "=", True)])
        ch.expect(nshow > 0, f"SA berechnet Gantt-Geometrie ({nshow} Aufgaben) (fachlich)")
        ok, info = _render_report(c, pid)
        ch.expect(ok, f"QWeb-PDF-Bericht rendert + article-Div [{info}] (fachlich)")
    return ch


def _render_report(c, pid):
    """Rendert den Bericht serverseitig zu HTML (per Wegwerf-Server-Action) und
    prüft article-Div + Charset. Ergebnis kommt über ir.config_parameter zurück."""
    code = (
        "report = env.ref('x_projektplan.action_report_projektplan_gantt')\n"
        "try:\n"
        "    res = report._render_qweb_html(report.report_name, [%d])\n"
        "    html = res[0]\n"
        "    if not isinstance(html, bytes):\n"
        "        html = html.encode('utf-8')\n"
        "    finding = 'len=%%d article=%%s charset=%%s' %% (len(html), b'class=\"article\"' in html, b'charset' in html[:2500])\n"
        "except Exception as e:\n"
        "    finding = 'ERR ' + str(e)[:150]\n"
        "env['ir.config_parameter'].sudo().set_param('x_healthcheck_render', finding)\n"
    ) % pid
    pm = c.find_one("ir.model", [("model", "=", "project.project")], fields=["id"])["id"]
    sa_id = c.create("ir.actions.server", {"name": "TMP healthcheck render", "model_id": pm,
                                           "state": "code", "code": code})
    try:
        try:
            c.execute("ir.actions.server", "run", [sa_id],
                      context={"active_model": "project.project", "active_id": pid, "active_ids": [pid]})
        except Exception:
            pass
        finding = c.execute("ir.config_parameter", "get_param", "x_healthcheck_render") or ""
    finally:
        c.unlink("ir.actions.server", [sa_id])
    ok = finding.startswith("len=") and "article=True" in finding
    return ok, finding


# --------------------------------------------------------------------------- #
CHANGESETS = [
    {"id": "LV-01", "title": "Datenmodell Lieferantenvertrag (Modell, Felder, Rechte)",
     "apply": ["lieferantenvertrag/03_model.py"], "test": test_lv01},
    {"id": "LV-02", "title": "Einkaufs-Verknüpfung (Feld auf Bestellung + Formular)",
     "apply": ["lieferantenvertrag/04_purchase_link.py"], "test": test_lv02},
    {"id": "LV-03", "title": "Mehrsprachigkeit (de/en Labels + Auswahlwerte)",
     "apply": ["lieferantenvertrag/05_translations.py"], "test": test_lv03},
    {"id": "LV-04", "title": "Automationen (Bestellung↔Vertrag, Erinnerung)",
     "apply": ["lieferantenvertrag/06_mail_and_automations.py"], "test": test_lv04},
    {"id": "LV-05", "title": "Oberfläche (Views, Menü, Partner-Tab, Smart-Button)",
     "apply": ["lieferantenvertrag/07_views.py", "lieferantenvertrag/10_smart_button.py"], "test": test_lv05},
    {"id": "PP-01", "title": "Projektplan als Gantt-PDF (Bericht + Button)",
     "apply": ["projektplan/01_report.py"], "test": test_pp01},
]
BY_ID = {cs["id"]: cs for cs in CHANGESETS}


def select(target):
    if target in (None, "all"):
        return CHANGESETS
    if target.upper() in BY_ID:
        return [BY_ID[target.upper()]]
    raise SystemExit(f"Unbekanntes Changeset: {target}. Bekannt: {', '.join(BY_ID)} oder 'all'.")


def cmd_list():
    print("Changesets:")
    for cs in CHANGESETS:
        print(f"  {cs['id']}  {cs['title']}")


def cmd_apply(target):
    for cs in select(target):
        print(f"\n=== APPLY {cs['id']} – {cs['title']} ===")
        ok, log = apply_scripts(cs["apply"])
        print(log)
        print(f"  -> {'OK ✓' if ok else 'FEHLER ✗'}")


def cmd_test(target):
    c = OdooClient.from_env(); c.connect()
    sets = select(target)
    passed = 0
    for cs in sets:
        print(f"\n=== TEST {cs['id']} – {cs['title']} ===")
        try:
            ch = cs["test"](c)
            for ok, label in ch.items:
                print(f"  [{'✓' if ok else '✗'}] {label}")
            if ch.ok:
                passed += 1
            print(f"  -> {'PASS ✓' if ch.ok else 'FAIL ✗'}")
        except Exception as e:
            print(f"  [✗] Test-Ausnahme: {type(e).__name__}: {str(e).splitlines()[-1][:120]}")
            print("  -> FAIL ✗")
    print(f"\n==================== {passed}/{len(sets)} Changesets PASS ====================")
    return 0 if passed == len(sets) else 1


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    target = sys.argv[2] if len(sys.argv) > 2 else "all"
    if cmd == "list":
        cmd_list(); return 0
    if cmd == "apply":
        cmd_apply(target); return 0
    if cmd in ("test", "verify"):
        return cmd_test(None if cmd == "verify" else target)
    if cmd == "apply-test":
        cmd_apply(target)
        return cmd_test(target)
    raise SystemExit(f"Unbekanntes Kommando: {cmd}. Nutze: list|apply|test|apply-test|verify")


if __name__ == "__main__":
    raise SystemExit(main())
