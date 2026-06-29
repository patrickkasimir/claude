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
import json
import os
import re
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


AUDIT_COMPUTE_CODE = """
res = []
for f in env['ir.model.fields'].search([('state','=','manual'),('compute','!=',False)]):
    if f.model not in env:
        continue
    Model = env[f.model]
    field = Model._fields.get(f.name)
    if field is None:
        continue
    recs = Model.search([], limit=300)
    if not recs:
        res.append(f.model + '.' + f.name + ' :LEER')
        continue
    try:
        if field.store:
            env.add_to_compute(field, recs)   # gespeichert: Recompute erzwingen
            env.flush_all()
        else:
            recs.invalidate_recordset([f.name])   # nicht gespeichert: bei Lesen neu berechnen
            recs.mapped(f.name)
        res.append(f.model + '.' + f.name + ' :OK (%d)' % len(recs))
    except Exception as e:
        res.append(f.model + '.' + f.name + ' :FEHLER ' + str(e)[:160])
env['ir.config_parameter'].sudo().set_param('x_audit_compute', chr(10).join(res))
"""


def cmd_audit():
    """Instanzweiter Upgrade-Check: Recompute aller manuellen Rechenfelder +
    Rendern aller (angepassten) Formulare. Genau die Klassen, die Upgrades brechen."""
    c = OdooClient.from_env(); c.connect()
    fails = 0

    print("=== AUDIT 1/3: manuelle Rechenfelder – erzwungener Recompute ===")
    pm = c.find_one("ir.model", [("model", "=", "res.partner")], fields=["id"])["id"]
    sa = c.create("ir.actions.server", {"name": "TMP audit compute", "model_id": pm,
                                        "state": "code", "code": AUDIT_COMPUTE_CODE})
    try:
        try:
            c.execute("ir.actions.server", "run", [sa])
        except Exception:
            pass
        out = c.execute("ir.config_parameter", "get_param", "x_audit_compute") or ""
    finally:
        c.unlink("ir.actions.server", [sa])
    for line in (out.splitlines() or ["(keine manuellen Rechenfelder)"]):
        bad = ":FEHLER" in line
        fails += 1 if bad else 0
        print(f"  [{'✗' if bad else '✓'}] {line}")

    print("\n=== AUDIT 2/3: Formulare rendern (XPath/Arch) ===")
    models = {f["model"] for f in c.search_read("ir.model.fields",
              [("state", "=", "manual"), ("name", "like", "x_studio_%")], fields=["model"])}
    models |= {"x_lieferantenvertrag", "res.partner", "purchase.order", "project.project",
               "account.analytic.line", "sale.order", "crm.lead"}
    for model in sorted(models):
        try:
            c.execute(model, "get_view", view_type="form")
            print(f"  [✓] {model} (form)")
        except Exception as e:
            fails += 1
            print(f"  [✗] {model} (form) -> {str(e).splitlines()[-1][:90]}")
    for vt in ("list", "search"):
        try:
            c.execute("x_lieferantenvertrag", "get_view", view_type=vt)
            print(f"  [✓] x_lieferantenvertrag ({vt})")
        except Exception as e:
            fails += 1
            print(f"  [✗] x_lieferantenvertrag ({vt}) -> {str(e).splitlines()[-1][:90]}")

    print("\n=== AUDIT 3/3: Übersicht (informativ) ===")
    print("  Aktive Automationen          :", c.search_count("base.automation", [("active", "=", True)]))
    print("  Server-Aktionen (state=code) :", c.search_count("ir.actions.server", [("state", "=", "code")]))
    print("  Custom-Berichte (x_*)        :", c.search_count("ir.actions.report", [("report_name", "like", "x_%")]))

    print(f"\n==================== AUDIT: {('%d PROBLEM(E) ✗' % fails) if fails else 'alles grün ✓'} ====================")
    return 1 if fails else 0


# --------------------------------------------------------------------------- #
# Pre-Upgrade-Lint + Snapshot/Diff (plattformweites Vor-Upgrade-Audit)
# --------------------------------------------------------------------------- #
DOMAIN_OPS = {"=", "!=", ">", ">=", "<", "<=", "=?", "like", "not like", "=like",
              "ilike", "not ilike", "=ilike", "in", "not in", "child_of",
              "parent_of", "any", "not any"}
_DOM_RE = re.compile(r"""\(\s*['"]([\w.]+)['"]\s*,\s*['"]([^'"]+)['"]\s*,""")
SNAPSHOT_DEFAULT = HERE / "snapshot.json"


def _domain_fields(s):
    """Top-Level-Felder aus einer Domain (nur echte Leaves: 2. Token ist Operator)."""
    return {m.group(1).split(".")[0] for m in _DOM_RE.finditer(s or "")
            if m.group(2) in DOMAIN_OPS}


def _fields_cache(c):
    cache = {}
    def get(model):
        if model not in cache:
            try:
                cache[model] = set(c.fields_get(model).keys())
            except Exception:
                cache[model] = None
        return cache[model]
    return get


def _audit_models(c):
    """Modelle mit eigenen Anpassungen (manuelle x_-Felder oder Studio-Views)."""
    m = {f["model"] for f in c.search_read(
        "ir.model.fields", [("state", "=", "manual"), ("name", "like", "x_%")],
        fields=["model"])}
    m |= {v["model"] for v in c.search_read(
        "ir.ui.view", [("inherit_id", "!=", False), ("name", "like", "%Studio%")],
        fields=["model"])}
    return sorted(m)


def _form_metrics(c, model):
    arch = c.execute(model, "get_view", view_type="form")["arch"]
    tabs = re.findall(r'<page[^>]*\bstring="([^"]*)"', arch)
    fields = sorted(set(re.findall(r'<field name="([\w]+)"', arch)))
    views = sorted(v["name"] for v in c.search_read(
        "ir.ui.view", [("model", "=", model), ("inherit_id", "!=", False),
                       ("active", "=", True)], fields=["name"]))
    return {"tabs": tabs, "fields": fields, "views": views}


def cmd_lint():
    c = OdooClient.from_env(); c.connect()
    print("Ziel:", c.url, "| Version:", c.version.get("server_version"))
    flds = _fields_cache(c)
    hard, review = 0, 0

    print("\n=== LINT 1: Tote Feld-Referenzen in Domains (sicher problematisch) ===")
    # ir.rule
    rules = c.search_read("ir.rule", [("domain_force", "!=", False)],
                          fields=["name", "model_id", "domain_force"])
    rule_models = {m["id"]: m["model"] for m in c.read(
        "ir.model", list({r["model_id"][0] for r in rules if r["model_id"]}), ["model"])}
    for r in rules:
        tech = rule_models.get(r["model_id"][0]) if r["model_id"] else None
        f = flds(tech) if tech else None
        if not f:
            continue
        miss = sorted(x for x in _domain_fields(r["domain_force"]) if x not in f)
        if miss:
            hard += 1
            print(f"  [ir.rule] {r['name']} ({tech}): fehlt {miss}")
    # ir.model.fields.domain
    for fr in c.search_read("ir.model.fields", [("domain", "!=", False), ("domain", "!=", "[]")],
                            fields=["model", "name", "domain"]):
        f = flds(fr["model"])
        if not f:
            continue
        miss = sorted(x for x in _domain_fields(fr["domain"]) if x not in f)
        if miss:
            hard += 1
            print(f"  [field.domain] {fr['model']}.{fr['name']}: fehlt {miss}")
    # ir.filters
    for fl in c.search_read("ir.filters", [("domain", "!=", False), ("domain", "!=", "[]")],
                            fields=["name", "model_id", "domain"]):
        tech = fl["model_id"] if isinstance(fl["model_id"], str) else None
        f = flds(tech) if tech else None
        if not f:
            continue
        miss = sorted(x for x in _domain_fields(fl["domain"]) if x not in f)
        if miss:
            hard += 1
            print(f"  [ir.filters] {fl['name']} ({tech}): fehlt {miss}")
    if hard == 0:
        print("  keine toten Referenzen gefunden")

    # Echtes Risiko: Anker an Kern-LAYOUT-Containern div[@name='X'] (X kein studio_/x_).
    # Genau das (z.B. vat_vies_container) hat die Partner-View beim Upgrade zerlegt.
    # Feldnamen-Anker (partner_id …) und eigene studio_group_* sind robust -> ignoriert.
    print("\n=== LINT 2: Studio-Views mit Anker an Kern-Layout-Containern (Review) ===")
    n2 = 0
    for v in c.search_read("ir.ui.view", [("inherit_id", "!=", False), ("name", "like", "%Studio%")],
                           fields=["name", "model", "arch"]):
        containers = set(re.findall(r"div\[@name='([^']+)'\]", v["arch"] or ""))
        risky = sorted(x for x in containers if not (x.startswith("studio_") or x.startswith("x_")))
        if risky:
            n2 += 1
            review += 1
            print(f"  {v['name']} ({v['model']}): Container-Anker {risky}")
    if n2 == 0:
        print("  keine riskanten Container-Anker")

    print("\n=== LINT 3: Manuelle Compute-/Related-Felder mit Kernfeld-Bezug (Review) ===")
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
            review += 1
            print(f"  {fr['model']}.{fr['name']}: Kernfeld-Bezug {core}")

    print(f"\n==================== LINT: {hard} sichere Probleme, {review} Review-Punkte ====================")
    print("Hinweis: versionsspezifische Feld-Entfernungen (z.B. company_type in 19.3) sieht erst")
    print("der Test-DB-Schritt (audit + diff). Lint findet tote Refs sicher, Fragiles als Review.")
    return 1 if hard else 0


def cmd_snapshot(path):
    path = Path(path or SNAPSHOT_DEFAULT)
    c = OdooClient.from_env(); c.connect()
    models = _audit_models(c)
    print(f"Snapshot @ {c.url} ({c.version.get('server_version')}) – {len(models)} Modelle")
    snap = {"_url": c.url, "_version": c.version.get("server_version"), "models": {}}
    for m in models:
        try:
            snap["models"][m] = _form_metrics(c, m)
        except Exception as e:
            snap["models"][m] = {"error": str(e).splitlines()[-1][:80]}
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    print(f"Gespeichert: {path}  ({len(snap['models'])} Modelle)")
    return 0


def cmd_diff(path):
    path = Path(path or SNAPSHOT_DEFAULT)
    if not path.exists():
        raise SystemExit(f"Keine Baseline: {path} – zuerst 'snapshot' auf der alten Version.")
    base = json.loads(path.read_text())
    c = OdooClient.from_env(); c.connect()
    print(f"Diff: Baseline {base.get('_version')} ({base.get('_url')})")
    print(f"      gegen   {c.version.get('server_version')} ({c.url})\n")
    problems, studio_lost, core_suppressed = 0, 0, 0
    for m, b in sorted(base.get("models", {}).items()):
        if "error" in b:
            continue
        try:
            cur = _form_metrics(c, m)
        except Exception as e:
            problems += 1
            print(f"  [{m}] Formular rendert NICHT mehr: {str(e).splitlines()[-1][:70]}")
            continue
        lost_tabs = [t for t in b["tabs"] if t not in cur["tabs"]]
        lost_studio = [v for v in b["views"] if v not in cur["views"] and "Studio" in v]
        lost_xf = [f for f in b["fields"] if f not in cur["fields"] and f.startswith("x_")]
        # Kern-Rauschen (umbenannte/verschobene Standardfelder & Modul-Views) nur zählen
        core_suppressed += len([v for v in b["views"] if v not in cur["views"] and "Studio" not in v])
        core_suppressed += len([f for f in b["fields"] if f not in cur["fields"] and not f.startswith("x_")])
        if lost_tabs or lost_studio or lost_xf:
            problems += 1
            studio_lost += len(lost_studio)
            print(f"  [{m}]")
            if lost_studio:
                print(f"      verworfene Studio-Anpassung: {lost_studio}")
            if lost_tabs:
                print(f"      fehlende Tabs:   {lost_tabs}")
            if lost_xf:
                print(f"      fehlende Custom-Felder (x_): {lost_xf[:12]}"
                      + (" …" if len(lost_xf) > 12 else ""))
    print(f"\n==================== DIFF: {problems} Modell(e) mit Custom-Verlusten, "
          f"{studio_lost} verworfene Studio-Views | {core_suppressed} Kern-Änderungen unterdrückt ====================")
    return 1 if problems else 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    target = sys.argv[2] if len(sys.argv) > 2 else "all"
    if cmd == "list":
        cmd_list(); return 0
    if cmd == "apply":
        cmd_apply(target); return 0
    if cmd in ("test", "verify"):
        return cmd_test(None if cmd == "verify" else target)
    if cmd == "audit":
        return cmd_audit()
    if cmd == "lint":
        return cmd_lint()
    if cmd == "snapshot":
        return cmd_snapshot(sys.argv[2] if len(sys.argv) > 2 else None)
    if cmd == "diff":
        return cmd_diff(sys.argv[2] if len(sys.argv) > 2 else None)
    if cmd == "apply-test":
        cmd_apply(target)
        return cmd_test(target)
    raise SystemExit(f"Unbekanntes Kommando: {cmd}. "
                     "Nutze: list|apply|test|apply-test|verify|audit|lint|snapshot|diff")


if __name__ == "__main__":
    raise SystemExit(main())
