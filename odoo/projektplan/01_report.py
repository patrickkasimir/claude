#!/usr/bin/env python3
"""Projektplan als Gantt-PDF – Button auf dem Projekt (verfeinert).

Idempotent, alles über XML-RPC (kein eigenes Modul):
- Gespeicherte Hilfsfelder (Geometrie/Achse/Legende) auf project.task / project.project
- Papierformat A4 quer
- QWeb-Vorlage: Gantt mit Monats-Achse + Gitterlinien, Farb-Legende,
  Heute-Linie und Liste der nicht terminierten Top-Level-Aufgaben
- Bericht (qweb-pdf) + Server-Action (rechnet + speichert) + Header-Button

Hilfsfelder statt data-Dict, weil report_action(data=...) beim serverseitigen
PDF-Render verworfen wird; gespeicherte Felder sind in der Vorlage zuverlässig.
"""
from odoo_client import OdooClient

MOD = "x_projektplan"
VIEW_KEY = f"{MOD}.report_projektplan_gantt"
PROJECT_FORM_XMLID = "project.edit_project"   # zur Laufzeit per c.ref
SA_NAME = "Projektplan als PDF (Gantt)"
BUTTON_VIEW_NAME = "project.project.form.projektplan.button"

TASK_FIELDS = [
    ("x_studio_gantt_show", "boolean", "Gantt: anzeigen"),
    ("x_studio_gantt_undated", "boolean", "Gantt: ohne Termin"),
    ("x_studio_gantt_left", "float", "Gantt: Position %"),
    ("x_studio_gantt_width", "float", "Gantt: Breite %"),
    ("x_studio_gantt_color", "char", "Gantt: Farbe"),
    ("x_studio_gantt_period", "char", "Gantt: Zeitraum"),
    ("x_studio_gantt_meta", "char", "Gantt: Meta"),
]
PROJECT_FIELDS = [
    ("x_studio_gantt_subtitle", "char", "Gantt: Untertitel"),
    ("x_studio_gantt_ticks", "char", "Gantt: Monats-Achse"),
    ("x_studio_gantt_legend", "char", "Gantt: Legende"),
    ("x_studio_gantt_today", "float", "Gantt: Heute-Position %"),
]

QWEB_ARCH = """<t t-name="x_projektplan.report_projektplan_gantt">
  <t t-call="web.basic_layout">
    <style>
      .ppl-title { font-size:18px; font-weight:bold; margin:0 0 2px; }
      .ppl-sub { color:#666; font-size:11px; margin:0 0 8px; }
      .ppl-legend { font-size:9px; color:#444; margin:0 0 8px; }
      .ppl-legend .sw { display:inline-block; width:9px; height:9px; border-radius:2px; margin:0 4px 0 12px; vertical-align:middle; }
      table.gantt { width:100%; border-collapse:collapse; font-size:10px; table-layout:fixed; }
      table.gantt th { background:#f3f4f6; text-align:left; padding:4px 6px; border-bottom:1px solid #cbd5e1; font-size:9px; color:#374151; }
      table.gantt td { padding:3px 6px; border-bottom:1px solid #eef0f3; vertical-align:middle; }
      .c-name { width:26%; } .c-name .nm { font-weight:bold; } .c-name .st { color:#6b7280; font-size:8px; }
      .c-when { width:16%; color:#555; white-space:nowrap; }
      .c-track { width:58%; }
      .axis { position:relative; height:11px; }
      .axis .tk { position:absolute; top:0; font-size:8px; color:#9aa3af; }
      .track { position:relative; height:13px; background:#f7f8fa; border-radius:3px; }
      .track .grid { position:absolute; top:0; height:13px; border-left:1px solid #e9ebef; }
      .track .today { position:absolute; top:-1px; height:15px; border-left:1px dashed #ef4444; }
      .bar { position:absolute; top:1px; height:11px; border-radius:3px; }
      .undated { margin-top:10px; font-size:9px; color:#444; }
      .undated .h { font-weight:bold; margin-bottom:3px; }
      .undated ul { margin:0; padding-left:14px; } .undated li { margin-bottom:1px; }
    </style>
    <t t-foreach="docs" t-as="o">
      <div class="page">
        <p class="ppl-title">Projektplan: <t t-esc="o.name"/></p>
        <p class="ppl-sub"><t t-esc="o.x_studio_gantt_subtitle"/></p>

        <t t-if="o.x_studio_gantt_legend">
          <div class="ppl-legend">Legende:<t t-foreach="o.x_studio_gantt_legend.split('||')" t-as="lg"><t t-set="lp" t-value="lg.split('::')"/><span class="sw" t-attf-style="background:#{lp[1]};"/><t t-esc="lp[0]"/></t></div>
        </t>

        <t t-set="rows" t-value="o.task_ids.filtered('x_studio_gantt_show').sorted('x_studio_gantt_left')"/>
        <t t-if="not rows"><p>Keine terminierten Aufgaben oberster Ebene (Start- und Enddatum) in diesem Projekt.</p></t>
        <t t-if="rows">
          <table class="gantt">
            <thead><tr>
              <th class="c-name">Aufgabe</th>
              <th class="c-when">Zeitraum</th>
              <th class="c-track"><div class="axis"><t t-if="o.x_studio_gantt_ticks"><t t-foreach="o.x_studio_gantt_ticks.split('|')" t-as="tk"><t t-set="tp" t-value="tk.split(':')"/><span class="tk" t-attf-style="left:#{tp[1]}%;"><t t-esc="tp[0]"/></span></t></t></div></th>
            </tr></thead>
            <tbody>
              <t t-foreach="rows" t-as="task">
                <tr>
                  <td class="c-name"><span class="nm"><t t-esc="task.name"/></span><br/><span class="st"><t t-esc="task.x_studio_gantt_meta"/></span></td>
                  <td class="c-when"><t t-esc="task.x_studio_gantt_period"/></td>
                  <td class="c-track"><div class="track"><t t-if="o.x_studio_gantt_ticks"><t t-foreach="o.x_studio_gantt_ticks.split('|')" t-as="tk"><t t-set="tp" t-value="tk.split(':')"/><span class="grid" t-attf-style="left:#{tp[1]}%;"/></t></t><t t-if="o.x_studio_gantt_today &gt;= 0"><span class="today" t-attf-style="left:#{o.x_studio_gantt_today}%;"/></t><div class="bar" t-attf-style="left:#{task.x_studio_gantt_left}%; width:#{task.x_studio_gantt_width}%; background:#{task.x_studio_gantt_color};"/></div></td>
                </tr>
              </t>
            </tbody>
          </table>
        </t>

        <t t-set="undated" t-value="o.task_ids.filtered('x_studio_gantt_undated')"/>
        <t t-if="undated">
          <div class="undated">
            <div class="h">Ohne Termin – nicht im Diagramm (<t t-esc="len(undated)"/>):</div>
            <ul><t t-foreach="undated" t-as="u"><li><t t-esc="u.name"/><t t-if="u.x_studio_gantt_meta"> — <t t-esc="u.x_studio_gantt_meta"/></t></li></t></ul>
          </div>
        </t>
      </div>
    </t>
  </t>
</t>"""

SERVER_CODE = """# Projektplan-Gantt: Geometrie + Achse + Legende berechnen und speichern
project = record
old = env['project.task'].search(['&', ('project_id','=',project.id),
    '|', ('x_studio_gantt_show','=',True), ('x_studio_gantt_undated','=',True)])
if old:
    old.write({'x_studio_gantt_show': False, 'x_studio_gantt_undated': False})

dated = env['project.task'].search([
    ('project_id','=',project.id), ('parent_id','=',False),
    ('planned_date_begin','!=',False), ('date_deadline','!=',False),
], order='planned_date_begin, date_deadline')
undated = env['project.task'].search(['&', ('project_id','=',project.id),
    ('parent_id','=',False),
    '|', ('planned_date_begin','=',False), ('date_deadline','=',False)])
count_total = len(dated) + len(undated)

palette = ['#3b82f6','#10b981','#f59e0b','#8b5cf6','#ef4444','#14b8a6','#ec4899','#64748b']
stage_colors = {}
ticks_parts = []
legend_parts = []
today_pos = -1.0
if dated:
    t0 = dated[0].planned_date_begin
    t1 = dated[0].date_deadline
    for t in dated:
        if t.planned_date_begin < t0:
            t0 = t.planned_date_begin
        if t.date_deadline > t1:
            t1 = t.date_deadline
    span = (t1 - t0).total_seconds() or 1.0
    for t in dated:
        sname = t.stage_id.name or ''
        if sname not in stage_colors:
            stage_colors[sname] = palette[len(stage_colors) % len(palette)]
        left = (t.planned_date_begin - t0).total_seconds() / span * 100.0
        width = (t.date_deadline - t.planned_date_begin).total_seconds() / span * 100.0
        if width < 0.6:
            width = 0.6
        if left + width > 100.0:
            width = 100.0 - left
        names = t.user_ids.mapped('name')[:2]
        if names:
            meta = (sname + ' · ' if sname else '') + ', '.join(names)
        else:
            meta = sname
        t.write({
            'x_studio_gantt_show': True,
            'x_studio_gantt_left': round(left, 3),
            'x_studio_gantt_width': round(width, 3),
            'x_studio_gantt_color': stage_colors[sname],
            'x_studio_gantt_period': t.planned_date_begin.strftime('%d.%m.%Y') + ' – ' + t.date_deadline.strftime('%d.%m.%Y'),
            'x_studio_gantt_meta': meta,
        })
    cur = t0.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    guard = 0
    while cur <= t1 and guard < 120:
        leftp = (cur - t0).total_seconds() / span * 100.0
        if 0.0 <= leftp <= 100.0:
            ticks_parts.append(cur.strftime('%m.%y') + ':' + str(round(leftp, 2)))
        ny = cur.year + (1 if cur.month == 12 else 0)
        nm = 1 if cur.month == 12 else cur.month + 1
        cur = cur.replace(year=ny, month=nm)
        guard += 1
    now = datetime.datetime.now()
    tp = (now - t0).total_seconds() / span * 100.0
    if 0.0 <= tp <= 100.0:
        today_pos = round(tp, 2)
    for k, v in stage_colors.items():
        label = (k or '—').replace('||', ' ').replace('::', ' ')
        legend_parts.append(label + '::' + v)

for u in undated:
    sname = u.stage_id.name or ''
    names = u.user_ids.mapped('name')[:2]
    if names:
        meta = (sname + ' · ' if sname else '') + ', '.join(names)
    else:
        meta = sname
    u.write({'x_studio_gantt_undated': True, 'x_studio_gantt_meta': meta})

if dated:
    subtitle = '%d von %d Aufgaben oberster Ebene terminiert · %s – %s' % (
        len(dated), count_total, t0.strftime('%d.%m.%Y'), t1.strftime('%d.%m.%Y'))
else:
    subtitle = '0 von %d Aufgaben oberster Ebene terminiert' % count_total

project.write({
    'x_studio_gantt_subtitle': subtitle,
    'x_studio_gantt_ticks': '|'.join(ticks_parts),
    'x_studio_gantt_legend': '||'.join(legend_parts),
    'x_studio_gantt_today': today_pos,
})
action = env.ref('x_projektplan.action_report_projektplan_gantt').report_action(project)
"""

BUTTON_ARCH_TPL = """<data>
  <xpath expr="//header" position="inside">
    <button name="{sa_id}" type="action" string="Ausgabe als PDF" class="btn-secondary"/>
  </xpath>
</data>"""


def ensure_xmlid(c, module, name, model, res_id):
    d = c.find_one("ir.model.data", [("module", "=", module), ("name", "=", name)],
                   fields=["id"])
    return d["id"] if d else c.create("ir.model.data",
        {"module": module, "name": name, "model": model, "res_id": res_id})


def ensure_field(c, model, name, ttype, label):
    f = c.find_one("ir.model.fields", [("model", "=", model), ("name", "=", name)],
                   fields=["id"])
    if f:
        return False
    mid = c.find_one("ir.model", [("model", "=", model)], fields=["id"])["id"]
    c.create("ir.model.fields", {"name": name, "model_id": mid, "ttype": ttype,
                                 "field_description": label})
    return True


def main() -> int:
    c = OdooClient.from_env()
    c.connect()
    PROJECT_FORM_VIEW_ID = c.ref(PROJECT_FORM_XMLID)

    print("=== Hilfsfelder ===")
    for name, ttype, label in TASK_FIELDS:
        print(f"  task.{name:<24}", "angelegt" if ensure_field(c, "project.task", name, ttype, label) else "vorhanden")
    for name, ttype, label in PROJECT_FIELDS:
        print(f"  project.{name:<21}", "angelegt" if ensure_field(c, "project.project", name, ttype, label) else "vorhanden")

    pf = c.find_one("report.paperformat", [("name", "=", "Projektplan A4 quer")], fields=["id"])
    pf_id = pf["id"] if pf else c.create("report.paperformat", {
        "name": "Projektplan A4 quer", "format": "A4", "orientation": "Landscape",
        "margin_top": 8, "margin_bottom": 8, "margin_left": 6, "margin_right": 6,
        "header_spacing": 5, "dpi": 90})

    v = c.find_one("ir.ui.view", [("key", "=", VIEW_KEY)], fields=["id"])
    if v:
        view_id = v["id"]; c.write("ir.ui.view", [view_id], {"arch": QWEB_ARCH})
    else:
        view_id = c.create("ir.ui.view", {"name": "Projektplan Gantt (QWeb)",
            "type": "qweb", "key": VIEW_KEY, "arch": QWEB_ARCH})
    ensure_xmlid(c, MOD, "report_projektplan_gantt", "ir.ui.view", view_id)

    rep = c.find_one("ir.actions.report", [("report_name", "=", VIEW_KEY)], fields=["id"])
    rep_vals = {"name": "Projektplan (Gantt)", "model": "project.project",
        "report_type": "qweb-pdf", "report_name": VIEW_KEY, "paperformat_id": pf_id,
        "print_report_name": "'Projektplan - %s' % (object.name or '')"}
    if rep:
        report_id = rep["id"]; c.write("ir.actions.report", [report_id], rep_vals)
    else:
        report_id = c.create("ir.actions.report", rep_vals)
    ensure_xmlid(c, MOD, "action_report_projektplan_gantt", "ir.actions.report", report_id)

    proj_model_id = c.find_one("ir.model", [("model", "=", "project.project")], fields=["id"])["id"]
    sa = c.find_one("ir.actions.server", [("name", "=", SA_NAME)], fields=["id"])
    sa_vals = {"name": SA_NAME, "model_id": proj_model_id, "state": "code", "code": SERVER_CODE}
    if sa:
        sa_id = sa["id"]; c.write("ir.actions.server", [sa_id], sa_vals)
    else:
        sa_id = c.create("ir.actions.server", sa_vals)

    arch = BUTTON_ARCH_TPL.format(sa_id=sa_id)
    bv = c.find_one("ir.ui.view", [("name", "=", BUTTON_VIEW_NAME)], fields=["id"])
    if bv:
        c.write("ir.ui.view", [bv["id"]], {"arch": arch})
    else:
        c.create("ir.ui.view", {"name": BUTTON_VIEW_NAME, "model": "project.project",
            "type": "form", "inherit_id": PROJECT_FORM_VIEW_ID, "arch": arch})

    print(f"\nView {view_id} · Report {report_id} · Server-Action {sa_id} – aktualisiert ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
