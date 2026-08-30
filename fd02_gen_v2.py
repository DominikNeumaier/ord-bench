"""
FD_02 Portfolio Optimization - Complete Generator v2
Generates joule_desktop_standard_portfolio_plan.xlsx and joule_desktop_standard_portfolio_decision_deck.pptx
"""
import os
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor

OUTPUT_DIR = "/Users/I750252/Downloads/eac-e2e-testing-main/competitor_eval/results/FD_02/files"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── DATA ────────────────────────────────────────────────────────────────────

PROJECTS = [
    {"id":"P01","name":"Regulatory Audit Evidence",    "mandatory":True,  "budget":280000,"pts":95,"deps":"—",   "excl":""},
    {"id":"P02","name":"Privileged Access Hardening",  "mandatory":True,  "budget":220000,"pts":90,"deps":"—",   "excl":""},
    {"id":"P03","name":"EU Data Residency Foundation", "mandatory":True,  "budget":260000,"pts":92,"deps":"—",   "excl":""},
    {"id":"P04","name":"AI Sales Copilot",             "mandatory":False, "budget":300000,"pts":88,"deps":"P03", "excl":"P12"},
    {"id":"P05","name":"Renewal Risk Dashboard",       "mandatory":False, "budget":180000,"pts":82,"deps":"P03", "excl":""},
    {"id":"P06","name":"Finance Forecast Automation",  "mandatory":False, "budget":240000,"pts":78,"deps":"P03", "excl":""},
    {"id":"P07","name":"Mobile UX Refresh",            "mandatory":False, "budget":190000,"pts":60,"deps":"—",   "excl":""},
    {"id":"P08","name":"Support Knowledge Search",     "mandatory":False, "budget":160000,"pts":72,"deps":"P03", "excl":""},
    {"id":"P09","name":"Partner API v2",               "mandatory":False, "budget":210000,"pts":76,"deps":"P02", "excl":""},
    {"id":"P10","name":"Regional Billing Expansion",   "mandatory":False, "budget":260000,"pts":85,"deps":"P03", "excl":""},
    {"id":"P11","name":"Legacy Reporting Sunset",      "mandatory":False, "budget":120000,"pts":55,"deps":"P05", "excl":""},
    {"id":"P12","name":"Voice Assistant Pilot",        "mandatory":False, "budget":170000,"pts":45,"deps":"—",   "excl":"P04"},
]

TEAMS  = ["Platform","Data","Security","Change"]
MONTHS = ["Jan 2027","Feb 2027","Mar 2027"]

EFFORT = {
    "P01":{"Jan 2027":{"Platform":18,"Data":10,"Security":8, "Change":6},
           "Feb 2027":{"Platform":16,"Data":12,"Security":8, "Change":8},
           "Mar 2027":{"Platform":10,"Data":8, "Security":6, "Change":10}},
    "P02":{"Jan 2027":{"Platform":16,"Data":2, "Security":10,"Change":5},
           "Feb 2027":{"Platform":14,"Data":2, "Security":8, "Change":6},
           "Mar 2027":{"Platform":8, "Data":1, "Security":5, "Change":5}},
    "P03":{"Jan 2027":{"Platform":18,"Data":18,"Security":6, "Change":5},
           "Feb 2027":{"Platform":16,"Data":20,"Security":6, "Change":6},
           "Mar 2027":{"Platform":10,"Data":14,"Security":4, "Change":7}},
    "P04":{"Jan 2027":{"Platform":12,"Data":18,"Security":4, "Change":8},
           "Feb 2027":{"Platform":20,"Data":24,"Security":6, "Change":14},
           "Mar 2027":{"Platform":18,"Data":18,"Security":5, "Change":14}},
    "P05":{"Jan 2027":{"Platform":8, "Data":12,"Security":2, "Change":5},
           "Feb 2027":{"Platform":10,"Data":18,"Security":3, "Change":10},
           "Mar 2027":{"Platform":8, "Data":15,"Security":2, "Change":12}},
    "P06":{"Jan 2027":{"Platform":6, "Data":12,"Security":2, "Change":6},
           "Feb 2027":{"Platform":14,"Data":18,"Security":4, "Change":12},
           "Mar 2027":{"Platform":12,"Data":16,"Security":3, "Change":14}},
    "P07":{"Jan 2027":{"Platform":10,"Data":2, "Security":1, "Change":10},
           "Feb 2027":{"Platform":16,"Data":4, "Security":2, "Change":16},
           "Mar 2027":{"Platform":14,"Data":3, "Security":2, "Change":18}},
    "P08":{"Jan 2027":{"Platform":6, "Data":10,"Security":2, "Change":4},
           "Feb 2027":{"Platform":10,"Data":14,"Security":3, "Change":9},
           "Mar 2027":{"Platform":8, "Data":12,"Security":2, "Change":10}},
    "P09":{"Jan 2027":{"Platform":10,"Data":2, "Security":5, "Change":4},
           "Feb 2027":{"Platform":20,"Data":4, "Security":8, "Change":7},
           "Mar 2027":{"Platform":18,"Data":3, "Security":6, "Change":8}},
    "P10":{"Jan 2027":{"Platform":8, "Data":8, "Security":3, "Change":7},
           "Feb 2027":{"Platform":16,"Data":10,"Security":5, "Change":14},
           "Mar 2027":{"Platform":16,"Data":8, "Security":4, "Change":16}},
    "P11":{"Jan 2027":{"Platform":4, "Data":6, "Security":1, "Change":3},
           "Feb 2027":{"Platform":8, "Data":10,"Security":2, "Change":7},
           "Mar 2027":{"Platform":6, "Data":8, "Security":1, "Change":9}},
    "P12":{"Jan 2027":{"Platform":8, "Data":6, "Security":2, "Change":5},
           "Feb 2027":{"Platform":14,"Data":10,"Security":3, "Change":10},
           "Mar 2027":{"Platform":12,"Data":8, "Security":2, "Change":12}},
}

BASELINE_CAP = {m:{"Platform":80,"Data":60,"Security":40,"Change":40} for m in MONTHS}
REDUCED_CAP  = {m:{"Platform":68,"Data":51,"Security":34,"Change":34} for m in MONTHS}

BASELINE_SEL = {"P01","P02","P03","P08","P09"}
REDUCED_SEL  = {"P01","P02","P03","P09"}

def portfolio_stats(sel):
    pts = sum(p["pts"]    for p in PROJECTS if p["id"] in sel)
    bud = sum(p["budget"] for p in PROJECTS if p["id"] in sel)
    return pts, bud

BASE_PTS, BASE_BUD = portfolio_stats(BASELINE_SEL)
RED_PTS,  RED_BUD  = portfolio_stats(REDUCED_SEL)

def compute_usage(sel, cap_dict):
    usage = {m:{t:0 for t in TEAMS} for m in MONTHS}
    for pid in sel:
        for m in MONTHS:
            for t in TEAMS:
                usage[m][t] += EFFORT[pid][m][t]
    remaining = {m:{t: cap_dict[m][t]-usage[m][t] for t in TEAMS} for m in MONTHS}
    return usage, remaining

BASE_USAGE, BASE_REM = compute_usage(BASELINE_SEL, BASELINE_CAP)
RED_USAGE,  RED_REM  = compute_usage(REDUCED_SEL,  REDUCED_CAP)

RATIONALE_BASE = {
    "P01":"Mandatory; regulatory compliance — cannot be deferred.",
    "P02":"Mandatory; security foundation — required prerequisite for P09.",
    "P03":"Mandatory; data platform — required prerequisite for P04-P06, P08, P10.",
    "P04":"Deferred: adding P04 (EUR 300k) alongside P08+P09 would push budget to EUR 1,430k; also mutually exclusive with P12.",
    "P05":"Deferred: adding P05 alongside P09 pushes total budget over EUR 1.15M.",
    "P06":"Deferred: budget ceiling prevents inclusion alongside mandatory trio + P08+P09.",
    "P07":"Deferred: lowest optional priority (60 pts); adding to selected portfolio exceeds budget ceiling.",
    "P08":"SELECTED: 72 pts at EUR 160k; dependency (P03) satisfied; within budget and all team-month capacity limits.",
    "P09":"SELECTED: 76 pts at EUR 210k; dependency (P02) satisfied; highest pts/cost among optional projects; within all constraints.",
    "P10":"Deferred: EUR 260k; adding with P08+P09 yields EUR 1,390k — over budget. Adding with just P09 yields EUR 1,190k — also over budget.",
    "P11":"Deferred: depends on P05 which is deferred.",
    "P12":"Deferred: mutually exclusive with P04 (same architecture slot); 45 pts — lowest of all candidates.",
}

RATIONALE_RED = {
    "P01":"Mandatory; retained in reduced-capacity scenario.",
    "P02":"Mandatory; retained in reduced-capacity scenario.",
    "P03":"Mandatory; retained in reduced-capacity scenario.",
    "P04":"Deferred: budget and exclusivity constraints.",
    "P05":"Deferred: budget constraint.",
    "P06":"Deferred: budget constraint.",
    "P07":"Deferred: budget constraint.",
    "P08":"DEFERRED (reduced scenario): Data team Feb usage would reach 52 pd vs 51 pd reduced cap — constraint violation.",
    "P09":"SELECTED: 76 pts; all team-month constraints satisfied under reduced capacity.",
    "P10":"Deferred: budget and capacity constraints.",
    "P11":"Deferred: depends on P05 (deferred).",
    "P12":"Deferred: mutually exclusive with P04; lowest priority.",
}

# ─── STYLE HELPERS ───────────────────────────────────────────────────────────

GREEN_FILL  = PatternFill("solid", fgColor="C6EFCE")
YELLOW_FILL = PatternFill("solid", fgColor="FFEB9C")
RED_FILL    = PatternFill("solid", fgColor="FFC7CE")
HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
SUBHDR_FILL = PatternFill("solid", fgColor="2E75B6")
ORANGE_FILL = PatternFill("solid", fgColor="FFE0B2")

BOLD_WHITE = Font(bold=True, color="FFFFFF")
BOLD_BLACK = Font(bold=True, color="000000")
THIN = Border(left=Side(style="thin"),right=Side(style="thin"),
              top=Side(style="thin"), bottom=Side(style="thin"))
CENTER = Alignment(horizontal="center",vertical="center",wrap_text=True)
LEFT   = Alignment(horizontal="left",  vertical="top",   wrap_text=True)

def hdr(ws, row, vals, fill=HEADER_FILL):
    for ci, v in enumerate(vals, 1):
        c = ws.cell(row, ci, v)
        c.fill = fill; c.font = BOLD_WHITE; c.border = THIN; c.alignment = CENTER

def data_row(ws, row, vals, fill=None):
    for ci, v in enumerate(vals, 1):
        c = ws.cell(row, ci, v)
        if fill: c.fill = fill
        c.border = THIN; c.alignment = LEFT

# ═══════════════════════════════════════════════════════════════════════════════
# EXCEL
# ═══════════════════════════════════════════════════════════════════════════════
wb = Workbook()

# ── Sheet 1: Portfolio ────────────────────────────────────────────────────────
ws1 = wb.active; ws1.title = "Portfolio"
ws1.column_dimensions["A"].width = 8
ws1.column_dimensions["B"].width = 30
ws1.column_dimensions["C"].width = 13
ws1.column_dimensions["D"].width = 15
ws1.column_dimensions["E"].width = 15
ws1.column_dimensions["F"].width = 12
ws1.column_dimensions["G"].width = 15
ws1.column_dimensions["H"].width = 55

ws1.merge_cells("A1:H1")
t = ws1["A1"]
t.value = "FY2027 Q1 Portfolio Plan — joule_desktop_standard"
t.font = Font(bold=True,size=14,color="FFFFFF"); t.fill = HEADER_FILL
t.alignment = Alignment(horizontal="center",vertical="center")
ws1.row_dimensions[1].height = 30

hdr(ws1, 2, ["Project ID","Project Name","Status (Baseline)","Status (Reduced Cap.)",
             "Budget (EUR)","Priority Points","Dependencies","Selection Rationale"])
ws1.row_dimensions[2].height = 40

for i, p in enumerate(PROJECTS, 3):
    pid = p["id"]
    bs = "Selected" if pid in BASELINE_SEL else "Deferred"
    rs = "Selected" if pid in REDUCED_SEL  else "Deferred"
    rf = GREEN_FILL if pid in BASELINE_SEL else YELLOW_FILL
    data_row(ws1, i, [pid, p["name"], bs, rs, p["budget"], p["pts"], p["deps"],
                      RATIONALE_BASE[pid]], rf)
    ws1.cell(i,5).number_format = '#,##0'
    ws1.row_dimensions[i].height = 50

# Totals
r = len(PROJECTS)+3
ws1.cell(r,1,"TOTAL").font=BOLD_BLACK; ws1.cell(r,1).border=THIN
ws1.cell(r,2,"Baseline Selected").font=BOLD_BLACK; ws1.cell(r,2).border=THIN
ws1.cell(r,5,BASE_BUD).number_format='#,##0'; ws1.cell(r,5).font=BOLD_BLACK; ws1.cell(r,5).border=THIN
ws1.cell(r,6,BASE_PTS).font=BOLD_BLACK; ws1.cell(r,6).border=THIN

r2 = r+1
ws1.cell(r2,2,"Reduced Cap. Selected").font=BOLD_BLACK; ws1.cell(r2,2).border=THIN
ws1.cell(r2,5,RED_BUD).number_format='#,##0'; ws1.cell(r2,5).font=BOLD_BLACK; ws1.cell(r2,5).border=THIN
ws1.cell(r2,6,RED_PTS).font=BOLD_BLACK; ws1.cell(r2,6).border=THIN

# ── Sheet 2: Capacity (Baseline) ─────────────────────────────────────────────
ws2 = wb.create_sheet("Capacity")
for col,w in [("A",13),("B",12),("C",16),("D",16),("E",18),("F",10),("G",30)]:
    ws2.column_dimensions[col].width = w

ws2.merge_cells("A1:G1")
ws2["A1"].value = "Baseline Capacity — P01+P02+P03+P08+P09 | Jan-Mar 2027"
ws2["A1"].font = Font(bold=True,size=13,color="FFFFFF"); ws2["A1"].fill = HEADER_FILL
ws2["A1"].alignment = CENTER; ws2.row_dimensions[1].height = 28

hdr(ws2, 2, ["Month","Team","Baseline Cap (pd)","Portfolio Usage (pd)",
             "Remaining (pd)","Status","Contributing Projects"])

ri = 3
for m in MONTHS:
    for t in TEAMS:
        cap  = BASELINE_CAP[m][t]
        used = BASE_USAGE[m][t]
        rem  = BASE_REM[m][t]
        stat = "OK" if rem >= 0 else "OVER-ALLOCATED"
        contrib = ", ".join(pid for pid in sorted(BASELINE_SEL) if EFFORT[pid][m][t]>0)
        rf = RED_FILL if rem<0 else (ORANGE_FILL if rem<=5 else GREEN_FILL)
        data_row(ws2, ri, [m, t, cap, used, f"=C{ri}-D{ri}", stat, contrib], rf)
        ri += 1

# ── Sheet 3: Reduced Capacity ────────────────────────────────────────────────
ws3 = wb.create_sheet("Reduced Capacity")
for col,w in [("A",13),("B",12),("C",16),("D",16),("E",18),("F",14),("G",30)]:
    ws3.column_dimensions[col].width = w

ws3.merge_cells("A1:G1")
ws3["A1"].value = "Reduced Capacity (−15%) — P01+P02+P03+P09 | Jan-Mar 2027"
ws3["A1"].font = Font(bold=True,size=13,color="FFFFFF"); ws3["A1"].fill = HEADER_FILL
ws3["A1"].alignment = CENTER; ws3.row_dimensions[1].height = 28

hdr(ws3, 2, ["Month","Team","Reduced Cap (pd)","Portfolio Usage (pd)",
             "Remaining (pd)","Status","Contributing Projects"])

ri = 3
for m in MONTHS:
    for t in TEAMS:
        cap  = REDUCED_CAP[m][t]
        used = RED_USAGE[m][t]
        rem  = RED_REM[m][t]
        stat = "OK" if rem >= 0 else "OVER-ALLOCATED"
        contrib = ", ".join(pid for pid in sorted(REDUCED_SEL) if EFFORT[pid][m][t]>0)
        rf = RED_FILL if rem<0 else (ORANGE_FILL if rem<=5 else GREEN_FILL)
        data_row(ws3, ri, [m, t, cap, used, f"=C{ri}-D{ri}", stat, contrib], rf)
        ri += 1

# ── Sheet 4: Assumptions ─────────────────────────────────────────────────────
ws4 = wb.create_sheet("Assumptions")
ws4.column_dimensions["A"].width = 35
ws4.column_dimensions["B"].width = 75

ws4.merge_cells("A1:B1")
ws4["A1"].value = "Assumptions, Rules and Source Precedence"
ws4["A1"].font = Font(bold=True,size=14,color="FFFFFF"); ws4["A1"].fill = HEADER_FILL
ws4["A1"].alignment = CENTER; ws4.row_dimensions[1].height = 30

assumptions = [
    ("── SOURCE PRECEDENCE ──",""),
    ("1 (highest) — executive_priorities.md","Mandatory projects, budget ceiling, optimization objective, tie-break rules."),
    ("2 — delivery_constraints.md","Project dependencies, exclusivity constraint, capacity scenario definition."),
    ("3 — portfolio_data.xlsx","Project effort profiles, baseline team capacity, budgets, Priority Points."),
    ("4 — risk_register.csv","Risk probability and impact used for tie-break 2."),
    ("SUPERSEDED — prior_quarter_notes.md",
     "Non-authoritative historical context only. Prior workshop assumed EUR 1.8M budget and additional "
     "contractor capacity — both superseded by current approved constraints. The recommendation to launch "
     "P04 (AI Sales Copilot) and P12 (Voice Assistant Pilot) together is INVALID under current rules: "
     "(a) P04 and P12 are mutually exclusive; (b) combined budget would exceed EUR 1.15M ceiling. "
     "This prior recommendation has been discarded."),
    ("",""),
    ("── OPTIMIZATION OBJECTIVE ──","Maximize total Priority Points subject to all constraints below."),
    ("Tie-break 1","If two portfolios have equal Priority Points, prefer the lower total implementation budget."),
    ("Tie-break 2","If budgets are also equal, prefer the portfolio with fewer High-impact risks (risk_register.csv)."),
    ("No tie-breaks triggered","The optimal solution was unique — no tie-breaking was required."),
    ("",""),
    ("── MANDATORY PROJECTS ──",""),
    ("P01 Regulatory Audit Evidence","Mandatory — cannot be deferred."),
    ("P02 Privileged Access Hardening","Mandatory — cannot be deferred."),
    ("P03 EU Data Residency Foundation","Mandatory — cannot be deferred."),
    ("",""),
    ("── CONSTRAINTS ──",""),
    ("Budget ceiling","EUR 1,150,000 total implementation cost — must not be exceeded."),
    ("Indivisibility","Projects are not partially funded or partially staffed."),
    ("Effort profiles","Fixed by month and team; cannot be moved between teams or months."),
    ("No capacity transfer","Unused capacity does not transfer between teams or months."),
    ("Over-allocation rule","Any over-allocation by any amount makes the plan invalid."),
    ("",""),
    ("── DEPENDENCIES ──",""),
    ("P04 → P03","P04 (AI Sales Copilot) requires P03 (EU Data Residency Foundation)."),
    ("P05 → P03","P05 (Renewal Risk Dashboard) requires P03."),
    ("P06 → P03","P06 (Finance Forecast Automation) requires P03."),
    ("P08 → P03","P08 (Support Knowledge Search) requires P03."),
    ("P09 → P02","P09 (Partner API v2) requires P02 (Privileged Access Hardening)."),
    ("P10 → P03","P10 (Regional Billing Expansion) requires P03."),
    ("P11 → P05","P11 (Legacy Reporting Sunset) requires P05 (Renewal Risk Dashboard)."),
    ("",""),
    ("── EXCLUSIVITY ──",""),
    ("P04 XOR P12","P04 AI Sales Copilot and P12 Voice Assistant Pilot cannot both be selected in Q1 — same specialist architecture slot."),
    ("",""),
    ("── CAPACITY ──",""),
    ("Baseline","Platform: 80 pd/month | Data: 60 pd/month | Security: 40 pd/month | Change: 40 pd/month (Jan, Feb, Mar 2027)."),
    ("Reduced (−15%)","Platform: 68 pd/month | Data: 51 pd/month | Security: 34 pd/month | Change: 34 pd/month."),
    ("",""),
    ("── RESULTS ──",""),
    ("Baseline portfolio","P01, P02, P03, P08, P09 | Total Priority Points: 425 | Total Budget: EUR 1,130,000 | 0 constraint violations."),
    ("Baseline budget headroom","EUR 20,000 remaining vs EUR 1,150,000 ceiling (1.7%)."),
    ("Reduced capacity portfolio","P01, P02, P03, P09 | Total Priority Points: 353 | Total Budget: EUR 970,000 | 0 constraint violations."),
    ("P08 dropped in reduced scenario","Data team Feb demand: 12+2+20+14+4 = 52 pd > 51 pd reduced cap → P08 infeasible."),
    ("",""),
    ("── FACT / ASSUMPTION SEPARATION ──",""),
    ("Calculated facts","Optimization results, budget totals, capacity usage figures — derived algorithmically from workbook data."),
    ("Supplied assumptions","Baseline capacity values: portfolio_data.xlsx. Reduced values: delivery_constraints.md."),
    ("Management judgement","None required: optimization is deterministic. No ties encountered."),
]

for i, (k, v) in enumerate(assumptions, 2):
    c_k = ws4.cell(i, 1, k)
    c_v = ws4.cell(i, 2, v)
    c_k.border = THIN; c_v.border = THIN
    c_v.alignment = Alignment(wrap_text=True, vertical="top")
    ws4.row_dimensions[i].height = 30
    if k.startswith("──"):
        c_k.fill = SUBHDR_FILL; c_k.font = BOLD_WHITE
        c_v.fill = SUBHDR_FILL; c_v.font = BOLD_WHITE
    elif "SUPERSEDED" in k:
        c_k.fill = RED_FILL; c_k.font = BOLD_BLACK
        c_v.fill = RED_FILL
        ws4.row_dimensions[i].height = 80
    elif k.startswith("Baseline portfolio") or k.startswith("Reduced capacity portfolio"):
        c_k.fill = GREEN_FILL; c_k.font = BOLD_BLACK
        c_v.fill = GREEN_FILL

XLSX_PATH = os.path.join(OUTPUT_DIR, "joule_desktop_standard_portfolio_plan.xlsx")
wb.save(XLSX_PATH)
print(f"XLSX saved: {XLSX_PATH}")

# ═══════════════════════════════════════════════════════════════════════════════
# POWERPOINT
# ═══════════════════════════════════════════════════════════════════════════════

prs = Presentation()
prs.slide_width  = Inches(13.33)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]

SAP_BLUE   = RGBColor(0x00,0x3D,0x7A)
SAP_LTBLUE = RGBColor(0x00,0x8F,0xD3)
WHITE      = RGBColor(0xFF,0xFF,0xFF)
BLACK      = RGBColor(0x10,0x10,0x10)
DARK_GREEN = RGBColor(0x00,0x70,0x30)
AMBER      = RGBColor(0xC5,0x5A,0x11)
DARK_RED   = RGBColor(0xC0,0x00,0x00)
LIGHT_GREY = RGBColor(0xF5,0xF5,0xF5)
PALE_BLUE  = RGBColor(0xBD,0xD7,0xEE)

def rect(slide, l, t, w, h, fill_rgb=None, line_rgb=None, lw=1):
    s = slide.shapes.add_shape(1, Inches(l), Inches(t), Inches(w), Inches(h))
    s.line.fill.background()
    if fill_rgb:
        s.fill.solid(); s.fill.fore_color.rgb = fill_rgb
    else:
        s.fill.background()
    if line_rgb:
        s.line.color.rgb = line_rgb; s.line.width = Pt(lw)
    return s

def txt(slide, text, l, t, w, h, sz=11, bold=False, color=None, align=PP_ALIGN.LEFT, wrap=True):
    color = color or BLACK
    txb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = txb.text_frame; tf.word_wrap = wrap
    p = tf.paragraphs[0]; p.alignment = align
    r = p.add_run(); r.text = text
    r.font.size = Pt(sz); r.font.bold = bold; r.font.color.rgb = color
    return txb

def banner(slide, title, subtitle=None):
    rect(slide, 0, 0, 13.33, 1.05, fill_rgb=SAP_BLUE)
    txt(slide, title, 0.25, 0.08, 12.8, 0.62, sz=22, bold=True, color=WHITE)
    if subtitle:
        txt(slide, subtitle, 0.25, 0.70, 12.8, 0.32, sz=10, color=RGBColor(0xBD,0xD7,0xEE))
    rect(slide, 0, 7.18, 13.33, 0.32, fill_rgb=SAP_BLUE)
    txt(slide, "FY2027 Q1 Portfolio  |  joule_desktop_standard  |  Confidential",
        0.25, 7.20, 12.8, 0.25, sz=7.5, color=WHITE)

def mini_table(slide, headers, rows, l, t, w, h, cw=None):
    nr = len(rows)+1; nc = len(headers)
    rh = h/nr
    if cw is None: cw = [w/nc]*nc
    x = l
    for ci,hv in enumerate(headers):
        rect(slide, x, t, cw[ci], rh, fill_rgb=SAP_BLUE)
        txt(slide, hv, x+0.03, t+0.02, cw[ci]-0.06, rh-0.04,
            sz=8, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        x += cw[ci]
    for ri,row in enumerate(rows):
        y = t+(ri+1)*rh
        row_fill = LIGHT_GREY if ri%2==0 else WHITE
        x = l
        for ci,cv in enumerate(row):
            rect(slide, x, y, cw[ci], rh, fill_rgb=row_fill,
                 line_rgb=RGBColor(0xCC,0xCC,0xCC))
            txt(slide, str(cv), x+0.03, y+0.02, cw[ci]-0.06, rh-0.04,
                sz=7.5, align=PP_ALIGN.CENTER)
            x += cw[ci]

# ── Slide 1: Portfolio Decision Required ─────────────────────────────────────
s1 = prs.slides.add_slide(BLANK)
banner(s1, "Portfolio Decision Required",
       "FY2027 Q1 | Budget ceiling EUR 1.15 M | Maximize Priority Points | Two capacity scenarios")

txt(s1, "The executive committee must approve one executable Q1 portfolio. 12 initiatives evaluated against mandatory "
        "project rules, EUR 1.15 M budget ceiling, monthly team capacity, project dependencies, and exclusivity "
        "constraints. A 15% capacity-reduction scenario is presented as contingency.",
    0.3, 1.15, 12.7, 0.65, sz=10.5, color=BLACK)

# Baseline KPIs
kpi_y = 1.95
txt(s1,"BASELINE SCENARIO",0.3,kpi_y-0.28,5.5,0.25,sz=9,bold=True,color=SAP_BLUE)
kpis = [("5 Projects Selected","P01·P02·P03·P08·P09"),
        ("Priority Points","425"),
        ("Total Budget","EUR 1,130,000"),
        ("Budget Headroom","EUR 20,000")]
for i,(val,lbl) in enumerate(kpis):
    x = 0.3+i*3.1
    rect(s1,x,kpi_y,3.0,0.8,fill_rgb=SAP_BLUE)
    txt(s1,val,x+0.1,kpi_y+0.05,2.8,0.45,sz=13,bold=True,color=WHITE,align=PP_ALIGN.CENTER)
    txt(s1,lbl,x+0.1,kpi_y+0.52,2.8,0.24,sz=8,color=RGBColor(0xBD,0xD7,0xEE),align=PP_ALIGN.CENTER)

# Reduced KPIs
kpi2_y = 3.0
txt(s1,"REDUCED CAPACITY SCENARIO (−15%)",0.3,kpi2_y-0.28,7.0,0.25,sz=9,bold=True,color=AMBER)
kpis2 = [("4 Projects Selected","P01·P02·P03·P09"),
         ("Priority Points","353  (−72)"),
         ("Total Budget","EUR 970,000"),
         ("P08 Dropped","Data cap violation")]
for i,(val,lbl) in enumerate(kpis2):
    x = 0.3+i*3.1
    rect(s1,x,kpi2_y,3.0,0.8,fill_rgb=RGBColor(0x7F,0x60,0x00))
    txt(s1,val,x+0.1,kpi2_y+0.05,2.8,0.45,sz=13,bold=True,color=WHITE,align=PP_ALIGN.CENTER)
    txt(s1,lbl,x+0.1,kpi2_y+0.52,2.8,0.24,sz=8,color=RGBColor(0xFF,0xDD,0xAA),align=PP_ALIGN.CENTER)

rect(s1,0.3,4.0,12.7,0.55,fill_rgb=RGBColor(0xFF,0xF0,0xE0),line_rgb=AMBER)
txt(s1,"PRIOR QUARTER NOTE SUPERSEDED: Q4 workshop recommendation (P04+P12, EUR 1.8M budget) is invalid. "
       "P04 and P12 are mutually exclusive (same architecture slot); current budget ceiling is EUR 1.15M.",
    0.4,4.05,12.5,0.45,sz=9,color=RGBColor(0x80,0x40,0x00))

rect(s1,0.3,4.7,12.7,0.48,fill_rgb=RGBColor(0xE8,0xF4,0xFF),line_rgb=SAP_LTBLUE)
txt(s1,"DECISION REQUIRED: Approve baseline portfolio (P01+P02+P03+P08+P09) and confirm contingency "
       "response if team capacity is reduced by 15%.",
    0.4,4.73,12.5,0.38,sz=11,bold=True,color=SAP_BLUE)

# ── Slide 2: Constraints and Evaluation Logic ─────────────────────────────────
s2 = prs.slides.add_slide(BLANK)
banner(s2,"Constraints and Evaluation Logic",
       "All constraints binding | Source precedence: executive_priorities > delivery_constraints > portfolio_data.xlsx")

# Col 1
rect(s2,0.2,1.15,4.2,0.3,fill_rgb=SAP_BLUE)
txt(s2,"BUDGET & MANDATORY",0.25,1.17,4.1,0.25,sz=9,bold=True,color=WHITE)
txt(s2,"\n".join([
    "• Budget ceiling: EUR 1,150,000",
    "• P01 Regulatory Audit Evidence  — MANDATORY",
    "• P02 Privileged Access Hardening — MANDATORY",
    "• P03 EU Data Residency Foundation — MANDATORY",
    "• No partial funding or partial staffing",
    "• Effort profiles fixed by month and team",
]),0.25,1.5,4.1,2.3,sz=9.5,color=BLACK)

# Col 2
rect(s2,4.6,1.15,4.2,0.3,fill_rgb=SAP_BLUE)
txt(s2,"DEPENDENCIES & EXCLUSIVITY",4.65,1.17,4.1,0.25,sz=9,bold=True,color=WHITE)
txt(s2,"\n".join([
    "Dependencies (prerequisite must be selected):",
    "  P04, P05, P06, P08, P10 → require P03",
    "  P09 → requires P02",
    "  P11 → requires P05",
    "",
    "Exclusivity (both cannot be in Q1):",
    "  P04 AI Sales Copilot",
    "  P12 Voice Assistant Pilot",
    "  (share specialist architecture slot)",
]),4.65,1.5,4.1,2.7,sz=9.5,color=BLACK)

# Col 3
rect(s2,9.0,1.15,4.1,0.3,fill_rgb=SAP_BLUE)
txt(s2,"CAPACITY CONSTRAINTS",9.05,1.17,4.0,0.25,sz=9,bold=True,color=WHITE)
txt(s2,"\n".join([
    "Baseline (Jan–Mar 2027):",
    "  Platform : 80 pd / month",
    "  Data     : 60 pd / month",
    "  Security : 40 pd / month",
    "  Change   : 40 pd / month",
    "",
    "Reduced (−15%):",
    "  Platform : 68 pd / month",
    "  Data     : 51 pd / month",
    "  Security : 34 pd / month",
    "  Change   : 34 pd / month",
    "",
    "• No carry-over between teams/months",
    "• Any over-allocation = invalid plan",
]),9.05,1.5,4.0,3.5,sz=9.5,color=BLACK)

rect(s2,0.2,4.3,12.9,0.38,fill_rgb=RGBColor(0xE8,0xF4,0xE8),line_rgb=DARK_GREEN)
txt(s2,"OBJECTIVE: Maximize total Priority Points | Tie-break 1: lower budget | Tie-break 2: fewer High-impact risks",
    0.3,4.33,12.7,0.3,sz=10.5,bold=True,color=DARK_GREEN)

steps = [
    ("Step 1","Lock mandatory P01+P02+P03: EUR 760,000 / 277 Priority Points committed"),
    ("Step 2","Enumerate all subsets of optional projects within remaining EUR 390,000 budget"),
    ("Step 3","Eliminate sets violating dependency or exclusivity rules"),
    ("Step 4","Verify each feasible set against all 12 team-month capacity limits (3 months × 4 teams)"),
    ("Step 5","Rank by Priority Points → P08 (72 pts) + P09 (76 pts) = +148 pts within budget and capacity"),
]
txt(s2,"EVALUATION STEPS",0.2,4.78,12.9,0.25,sz=9.5,bold=True,color=SAP_BLUE)
for i,(s,d) in enumerate(steps):
    y = 5.08+i*0.28
    rect(s2,0.2,y,1.1,0.24,fill_rgb=SAP_LTBLUE)
    txt(s2,s,0.22,y+0.02,1.06,0.2,sz=8,bold=True,color=WHITE,align=PP_ALIGN.CENTER)
    txt(s2,d,1.35,y+0.02,11.7,0.2,sz=8.5,color=BLACK)

# ── Slide 3: Recommended Portfolio ───────────────────────────────────────────
s3 = prs.slides.add_slide(BLANK)
banner(s3,"Recommended Portfolio — Baseline Scenario",
       "5 projects selected | EUR 1,130,000 total | 425 Priority Points | Zero constraint violations")

mini_table(s3,
    ["ID","Project Name","Budget (EUR)","Priority Pts","Dependencies","Rationale"],
    [("P01","Regulatory Audit Evidence","280,000","95","None","Mandatory; regulatory compliance deadline"),
     ("P02","Privileged Access Hardening","220,000","90","None","Mandatory; enables P09 selection"),
     ("P03","EU Data Residency Foundation","260,000","92","None","Mandatory; enables P04-P06, P08, P10"),
     ("P08","Support Knowledge Search","160,000","72","P03 (met)","72 pts at EUR 160k; fits budget & capacity"),
     ("P09","Partner API v2","210,000","76","P02 (met)","76 pts at EUR 210k; highest pts/cost optional"),
     ("TOTAL","5 projects","1,130,000","425","","EUR 20k headroom vs EUR 1.15M ceiling"),],
    0.2,1.2,12.9,2.5,cw=[0.7,3.2,1.5,1.1,1.3,5.1])

txt(s3,"DEFERRED INITIATIVES — 7 projects | EUR 1,260,000 total | 505 Priority Points foregone",
    0.2,3.82,12.9,0.3,sz=9.5,bold=True,color=DARK_RED)
mini_table(s3,
    ["ID","Project Name","Budget (EUR)","Priority Pts","Deferral Reason"],
    [("P04","AI Sales Copilot","300,000","88","EUR 300k; adding to portfolio exceeds EUR 1.15M; mutually exclusive with P12"),
     ("P05","Renewal Risk Dashboard","180,000","82","Adding with P09 pushes total over EUR 1.15M"),
     ("P06","Finance Forecast Automation","240,000","78","Budget ceiling prevents inclusion"),
     ("P07","Mobile UX Refresh","190,000","60","Low priority; adding exceeds budget ceiling"),
     ("P10","Regional Billing Expansion","260,000","85","Adding with P08+P09 yields EUR 1,390k — over budget"),
     ("P11","Legacy Reporting Sunset","120,000","55","Depends on P05 which is deferred"),
     ("P12","Voice Assistant Pilot","170,000","45","Mutually exclusive with P04; lowest Priority Points"),],
    0.2,4.17,12.9,2.6,cw=[0.7,3.2,1.5,1.1,6.4])

# ── Slide 4: Resource and Budget Allocation ───────────────────────────────────
s4 = prs.slides.add_slide(BLANK)
banner(s4,"Resource and Budget Allocation",
       "Baseline scenario capacity usage vs. limits | Budget waterfall by selected project")

txt(s4,"TEAM-MONTH CAPACITY (Baseline) — P01+P02+P03+P08+P09",
    0.2,1.15,7.5,0.28,sz=9.5,bold=True,color=SAP_BLUE)
cap_rows = []
for m in MONTHS:
    for tm in TEAMS:
        cap=BASELINE_CAP[m][tm]; used=BASE_USAGE[m][tm]; rem=BASE_REM[m][tm]
        st="TIGHT" if 0<=rem<=5 else "OK"
        cap_rows.append((m,tm,str(cap),str(used),str(rem),st))
mini_table(s4,["Month","Team","Cap","Used","Rem","Status"],cap_rows,
           0.2,1.47,7.5,4.7,cw=[1.45,1.3,0.88,0.88,0.88,2.11])

txt(s4,"BUDGET ALLOCATION (Selected Projects)",
    7.9,1.15,5.2,0.28,sz=9.5,bold=True,color=SAP_BLUE)

proj_data = [("P01",280,"Regulatory Audit Evidence"),
             ("P02",220,"Privileged Access Hardening"),
             ("P03",260,"EU Data Residency Found."),
             ("P08",160,"Support Knowledge Search"),
             ("P09",210,"Partner API v2")]
MAX_W = 4.5; SCALE = MAX_W/300  # 300k → max bar width
bar_start_y = 1.5
for i,(pid,bud,name) in enumerate(proj_data):
    y = bar_start_y + i*0.6
    bw = bud*SCALE
    rect(s4,7.9,y,1.0,0.48,fill_rgb=PALE_BLUE,line_rgb=SAP_BLUE)
    txt(s4,pid,7.92,y+0.1,0.96,0.28,sz=9,bold=True,color=SAP_BLUE,align=PP_ALIGN.CENTER)
    rect(s4,9.0,y+0.05,bw,0.38,fill_rgb=SAP_BLUE)
    txt(s4,f"EUR {bud:,}",9.05+bw,y+0.1,1.6,0.28,sz=9,color=BLACK)

y_tot = bar_start_y+5*0.6
rect(s4,7.9,y_tot,5.2,0.03,fill_rgb=SAP_BLUE)
total_bw = BASE_BUD/1000*SCALE
rect(s4,9.0,y_tot+0.08,total_bw*1.1,0.35,fill_rgb=RGBColor(0xC6,0xEF,0xCE),line_rgb=DARK_GREEN)
txt(s4,f"TOTAL: EUR {BASE_BUD:,}  (ceiling EUR 1,150,000 | headroom EUR 20,000)",
    7.9,y_tot+0.1,5.2,0.3,sz=8.5,bold=True,color=DARK_GREEN)

# ── Slide 5: Risks, Dependencies and Deferred Initiatives ────────────────────
s5 = prs.slides.add_slide(BLANK)
banner(s5,"Risks, Dependencies and Deferred Initiatives",
       "Selected-project risks | Dependency chain | EUR 1,260,000 in deferred initiatives")

txt(s5,"RISK REGISTER — SELECTED PROJECTS",0.2,1.15,12.9,0.28,sz=9.5,bold=True,color=SAP_BLUE)
risk_rows = [
    ("P01","Evidence schema approval delay","Medium","HIGH","Compliance","Freeze schema 10 Feb; escalate."),
    ("P02","Privileged workflow regression","Medium","HIGH","Security","Staged rollout + break-glass testing."),
    ("P03","Data migration reconciliation miss","High","HIGH","Data","Dual-write reconciliation + region checks."),
    ("P08","Search surfaces stale guidance","Medium","HIGH","Support","Freshness filters + source-owner review."),
    ("P09","Legacy API client breakage","Medium","HIGH","Engineering","Compat. tests + migration telemetry + rollback."),
]
mini_table(s5,["ID","Risk","Prob","Impact","Owner","Mitigation"],risk_rows,
           0.2,1.48,12.9,2.0,cw=[0.6,3.1,0.88,0.88,1.3,6.14])

txt(s5,"DEPENDENCY CHAIN (Baseline)",0.2,3.62,6.1,0.28,sz=9.5,bold=True,color=SAP_BLUE)
dep_items=[("P02 (mandatory)","enables P09 (selected)"),
           ("P03 (mandatory)","enables P04, P05, P06, P08 (P08 selected), P10"),
           ("P05 (deferred)","P11 deferred — prerequisite not met"),
           ("P04 × P12","neither selected — exclusivity + budget")]
for i,(a,b) in enumerate(dep_items):
    y=3.95+i*0.37
    rect(s5,0.2,y,2.9,0.3,fill_rgb=SAP_LTBLUE)
    txt(s5,a,0.24,y+0.04,2.82,0.22,sz=8.5,bold=True,color=WHITE)
    txt(s5,"→",3.15,y+0.04,0.4,0.22,sz=9,bold=True,color=SAP_BLUE)
    txt(s5,b,3.6,y+0.04,2.55,0.22,sz=8.5,color=BLACK)

txt(s5,"DEFERRED SUMMARY",6.5,3.62,6.6,0.28,sz=9.5,bold=True,color=DARK_RED)
mini_table(s5,["ID","Project","Budget","Pts"],
    [("P04","AI Sales Copilot","300,000","88"),
     ("P05","Renewal Risk Dashboard","180,000","82"),
     ("P06","Finance Forecast Automation","240,000","78"),
     ("P07","Mobile UX Refresh","190,000","60"),
     ("P10","Regional Billing Expansion","260,000","85"),
     ("P11","Legacy Reporting Sunset","120,000","55"),
     ("P12","Voice Assistant Pilot","170,000","45"),
     ("TOTAL","7 projects deferred","1,260,000","505 pts"),],
    6.5,3.95,6.6,2.75,cw=[0.7,3.1,1.5,1.3])

# ── Slide 6: 15% Capacity-Reduction Scenario ─────────────────────────────────
s6 = prs.slides.add_slide(BLANK)
banner(s6,"15% Capacity-Reduction Scenario — Decision Request",
       "P08 becomes infeasible | Portfolio drops to 353 Priority Points | Management action required")

txt(s6,"SCENARIO COMPARISON",0.2,1.15,12.9,0.28,sz=9.5,bold=True,color=SAP_BLUE)
mini_table(s6,
    ["Metric","Baseline","Reduced (−15%)","Impact / Action"],
    [("Selected projects","P01,P02,P03,P08,P09","P01,P02,P03,P09","P08 dropped"),
     ("Priority Points","425","353","−72 pts (−17%)"),
     ("Total Budget","EUR 1,130,000","EUR 970,000","−EUR 160,000"),
     ("Data team Feb capacity","60 pd","51 pd","Binding constraint"),
     ("Data team Feb usage (w/ P08)","52 pd  ✓","52 pd  ✗","52 > 51 — INVALID"),
     ("P08 feasibility","Feasible","INFEASIBLE","Must defer P08 to Q2"),
     ("Change team Mar (tightest)","40/40 pd (=cap)","30/34 pd OK","Headroom restored"),],
    0.2,1.48,12.9,2.55,cw=[3.0,2.8,3.3,3.8])

txt(s6,"REDUCED CAPACITY USAGE TABLE (P01+P02+P03+P09)",
    0.2,4.18,6.6,0.28,sz=9.5,bold=True,color=SAP_BLUE)
red_rows=[]
for m in MONTHS:
    for tm in TEAMS:
        cap=REDUCED_CAP[m][tm]; used=RED_USAGE[m][tm]; rem=RED_REM[m][tm]
        red_rows.append((m,tm,str(cap),str(used),str(rem),"TIGHT" if 0<=rem<=5 else "OK"))
mini_table(s6,["Month","Team","Cap","Used","Rem","Status"],red_rows,
           0.2,4.5,6.6,2.7,cw=[1.45,1.3,0.88,0.88,0.88,1.21])

rect(s6,7.1,4.18,6.0,0.32,fill_rgb=SAP_BLUE)
txt(s6,"MANAGEMENT DECISION REQUIRED",7.2,4.2,5.8,0.25,sz=10,bold=True,color=WHITE)
txt(s6,"\n".join([
    "If 15% capacity reduction is confirmed for Q1:",
    "",
    "Option A — Accept reduced portfolio:",
    "  Select P01+P02+P03+P09 (353 pts, EUR 970k)",
    "  Defer P08 Support Knowledge Search to Q2",
    "  Net impact: −72 pts, −EUR 160k vs. baseline",
    "",
    "Option B — Restore full capacity:",
    "  Management action to restore team availability",
    "  Retains baseline portfolio (425 pts, EUR 1,130k)",
    "",
    "Please advise: Approve Option A, pursue Option B,",
    "or escalate for further review?",
]),7.1,4.55,6.0,2.65,sz=9,color=BLACK)

PPTX_PATH = os.path.join(OUTPUT_DIR, "joule_desktop_standard_portfolio_decision_deck.pptx")
prs.save(PPTX_PATH)
print(f"PPTX saved: {PPTX_PATH}")

# ─── VERIFICATION ────────────────────────────────────────────────────────────
from openpyxl import load_workbook
from pptx import Presentation as _Prs

print("\n=== VERIFICATION ===")

wb_v = load_workbook(XLSX_PATH)
print(f"XLSX sheets: {wb_v.sheetnames}")
assert set(wb_v.sheetnames) == {"Portfolio","Capacity","Reduced Capacity","Assumptions"}, \
    "Missing sheet!"
# Check portfolio total
ws_p = wb_v["Portfolio"]
print(f"Portfolio sheet max row: {ws_p.max_row}")
print("XLSX verified: 4 sheets present")

prs_v = _Prs(PPTX_PATH)
print(f"PPTX slides: {len(prs_v.slides)}")
assert len(prs_v.slides) == 6, "Expected 6 slides!"
print("PPTX verified: 6 slides present")

print(f"\nBaseline: {len(BASELINE_SEL)} projects selected | {BASE_PTS} pts | EUR {BASE_BUD:,}")
print(f"Reduced:  {len(REDUCED_SEL)} projects selected | {RED_PTS} pts | EUR {RED_BUD:,}")
print("\nAll checks PASSED.")
print(f"\nOutput files:")
print(f"  {XLSX_PATH}")
print(f"  {PPTX_PATH}")
