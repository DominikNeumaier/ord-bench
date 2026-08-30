"""
FD_02 Portfolio Optimization - Complete Generator
Generates joule_desktop_standard_portfolio_plan.xlsx and
         joule_desktop_standard_portfolio_decision_deck.pptx
"""
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "openpyxl", "python-pptx"], capture_output=True)

import os, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.chart.data import ChartData
from pptx.enum.chart import XL_CHART_TYPE

# Paths
OUT = "/Users/I750252/Downloads/eac-e2e-testing-main/competitor_eval/results/FD_02/files"
os.makedirs(OUT, exist_ok=True)
XLSX = os.path.join(OUT, "joule_desktop_standard_portfolio_plan.xlsx")
PPTX_PATH = os.path.join(OUT, "joule_desktop_standard_portfolio_decision_deck.pptx")

# Project data
PROJECTS = [
    ("P01","Regulatory Audit Evidence",    True, 280000, 95,""),
    ("P02","Privileged Access Hardening",  True, 220000, 90,""),
    ("P03","EU Data Residency Foundation", True, 260000, 92,""),
    ("P04","AI Sales Copilot",            False, 300000, 88,"P03"),
    ("P05","Renewal Risk Dashboard",      False, 180000, 82,"P03"),
    ("P06","Finance Forecast Automation", False, 240000, 78,"P03"),
    ("P07","Mobile UX Refresh",           False, 190000, 60,""),
    ("P08","Support Knowledge Search",    False, 160000, 72,"P03"),
    ("P09","Partner API v2",              False, 210000, 76,"P02"),
    ("P10","Regional Billing Expansion",  False, 260000, 85,"P03"),
    ("P11","Legacy Reporting Sunset",     False, 120000, 55,"P05"),
    ("P12","Voice Assistant Pilot",       False, 170000, 45,"Excl. P04"),
]
MONTHS = ["Jan 2027","Feb 2027","Mar 2027"]
TEAMS  = ["Platform","Data","Security","Change"]
EFFORT = {
    "P01":{"Jan 2027":{"Platform":18,"Data":10,"Security":8,"Change":6},
           "Feb 2027":{"Platform":16,"Data":12,"Security":8,"Change":8},
           "Mar 2027":{"Platform":10,"Data":8, "Security":6,"Change":10}},
    "P02":{"Jan 2027":{"Platform":16,"Data":2, "Security":10,"Change":5},
           "Feb 2027":{"Platform":14,"Data":2, "Security":8, "Change":6},
           "Mar 2027":{"Platform":8, "Data":1, "Security":5, "Change":5}},
    "P03":{"Jan 2027":{"Platform":18,"Data":18,"Security":6,"Change":5},
           "Feb 2027":{"Platform":16,"Data":20,"Security":6,"Change":6},
           "Mar 2027":{"Platform":10,"Data":14,"Security":4,"Change":7}},
    "P04":{"Jan 2027":{"Platform":12,"Data":18,"Security":4,"Change":8},
           "Feb 2027":{"Platform":20,"Data":24,"Security":6,"Change":14},
           "Mar 2027":{"Platform":18,"Data":18,"Security":5,"Change":14}},
    "P05":{"Jan 2027":{"Platform":8, "Data":12,"Security":2,"Change":5},
           "Feb 2027":{"Platform":10,"Data":18,"Security":3,"Change":10},
           "Mar 2027":{"Platform":8, "Data":15,"Security":2,"Change":12}},
    "P06":{"Jan 2027":{"Platform":6, "Data":12,"Security":2,"Change":6},
           "Feb 2027":{"Platform":14,"Data":18,"Security":4,"Change":12},
           "Mar 2027":{"Platform":12,"Data":16,"Security":3,"Change":14}},
    "P07":{"Jan 2027":{"Platform":10,"Data":2, "Security":1,"Change":10},
           "Feb 2027":{"Platform":16,"Data":4, "Security":2,"Change":16},
           "Mar 2027":{"Platform":14,"Data":3, "Security":2,"Change":18}},
    "P08":{"Jan 2027":{"Platform":6, "Data":10,"Security":2,"Change":4},
           "Feb 2027":{"Platform":10,"Data":14,"Security":3,"Change":9},
           "Mar 2027":{"Platform":8, "Data":12,"Security":2,"Change":10}},
    "P09":{"Jan 2027":{"Platform":10,"Data":2, "Security":5,"Change":4},
           "Feb 2027":{"Platform":20,"Data":4, "Security":8,"Change":7},
           "Mar 2027":{"Platform":18,"Data":3, "Security":6,"Change":8}},
    "P10":{"Jan 2027":{"Platform":8, "Data":8, "Security":3,"Change":7},
           "Feb 2027":{"Platform":16,"Data":10,"Security":5,"Change":14},
           "Mar 2027":{"Platform":16,"Data":8, "Security":4,"Change":16}},
    "P11":{"Jan 2027":{"Platform":4, "Data":6, "Security":1,"Change":3},
           "Feb 2027":{"Platform":8, "Data":10,"Security":2,"Change":7},
           "Mar 2027":{"Platform":6, "Data":8, "Security":1,"Change":9}},
    "P12":{"Jan 2027":{"Platform":8, "Data":6, "Security":2,"Change":5},
           "Feb 2027":{"Platform":14,"Data":10,"Security":3,"Change":10},
           "Mar 2027":{"Platform":12,"Data":8, "Security":2,"Change":12}},
}
BASE_CAP = {"Platform":80,"Data":60,"Security":40,"Change":40}
RED_CAP  = {"Platform":68,"Data":51,"Security":34,"Change":34}
BASE_SEL = {"P01","P02","P03","P08","P09"}
RED_SEL  = {"P01","P02","P03","P09"}

def usage(sel):
    u = {m:{t:0 for t in TEAMS} for m in MONTHS}
    for pid in sel:
        for m in MONTHS:
            for t in TEAMS:
                u[m][t] += EFFORT[pid][m][t]
    return u

def totals(sel):
    return (sum(p[3] for p in PROJECTS if p[0] in sel),
            sum(p[4] for p in PROJECTS if p[0] in sel))

BU = usage(BASE_SEL); RU = usage(RED_SEL)
BB, BP = totals(BASE_SEL); RB, RP = totals(RED_SEL)
print(f"Baseline: {sorted(BASE_SEL)} Budget={BB:,} Points={BP}")
print(f"Reduced:  {sorted(RED_SEL)}  Budget={RB:,} Points={RP}")
print("\nCapacity verification:")
all_ok=True
for m in MONTHS:
    for t in TEAMS:
        bu=BU[m][t]; bc=BASE_CAP[t]
        ru2=RU[m][t]; rc=RED_CAP[t]
        if bu>bc: print(f"  VIOLATION BASE {m} {t}: {bu}>{bc}"); all_ok=False
        if ru2>rc: print(f"  VIOLATION RED  {m} {t}: {ru2}>{rc}"); all_ok=False
        else: print(f"  {m} {t:10}: Base {bu:2}/{bc} OK  | Red {ru2:2}/{rc} OK")
if all_ok: print("All capacity checks PASSED")

# Style helpers
H_FILL=PatternFill("solid",fgColor="1F4E79"); H_FONT=Font(bold=True,color="FFFFFF",size=11)
A_FILL=PatternFill("solid",fgColor="D6E4F0"); G_FILL=PatternFill("solid",fgColor="C6EFCE")
Y_FILL=PatternFill("solid",fgColor="FFEB9C"); R_FILL=PatternFill("solid",fgColor="FFC7CE")
BOLD=Font(bold=True,size=11)
THIN=Border(left=Side(style='thin'),right=Side(style='thin'),
            top=Side(style='thin'),bottom=Side(style='thin'))
def hcell(c): c.font=H_FONT;c.fill=H_FILL;c.border=THIN;c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
def dcell(c,alt=False,fill=None):
    c.fill=fill if fill else (A_FILL if alt else PatternFill())
    c.alignment=Alignment(vertical="center",wrap_text=True);c.border=THIN
def aw(ws):
    for col in ws.columns:
        ws.column_dimensions[get_column_letter(col[0].column)].width=min(max(max(len(str(cell.value or "")) for cell in col)+2,10),40)

RATIONALE = {
    "P01":"Mandatory — cannot be deferred",
    "P02":"Mandatory — cannot be deferred",
    "P03":"Mandatory — prerequisite for P04,P05,P06,P08,P10",
    "P04":"Deferred: budget+exclusivity — adding P04 exceeds EUR 1.15M and violates P04 XOR P12 rule",
    "P05":"Deferred: adding P05+mandatories exceeds EUR 1.15M budget ceiling",
    "P06":"Deferred: adding P06 exceeds EUR 1.15M budget ceiling",
    "P07":"Deferred: 60 pts only; adding P07 would exceed EUR 1.15M budget",
    "P08":"Baseline: 72 pts within budget, P03 satisfied. Reduced: Feb Data 38+14=52>51 cap",
    "P09":"Selected: 76 pts; P02 prerequisite satisfied; feasible both scenarios",
    "P10":"Deferred: adding P10 would exceed EUR 1.15M budget ceiling",
    "P11":"Deferred: prerequisite P05 not selected in either scenario",
    "P12":"Deferred: mutually exclusive with P04; lowest priority (45 pts)",
}

# === EXCEL ===
wb = openpyxl.Workbook(); wb.remove(wb.active)

# Sheet 1: Portfolio
ws1=wb.create_sheet("Portfolio")
h1=["Project ID","Project Name","Status (Baseline)","Status (Reduced Cap.)","Budget (EUR)","Priority Points","Dependencies","Selection Rationale"]
for i,h in enumerate(h1,1): hcell(ws1.cell(1,i,h))
for ri,p in enumerate(PROJECTS):
    pid,nm,mand,bud,pts,dep=p; r=ri+2; alt=(ri%2==1)
    sb="Selected" if pid in BASE_SEL else "Deferred"
    sr="Selected" if pid in RED_SEL else "Deferred"
    for ci,v in enumerate([pid,nm,sb,sr,bud,pts,dep if dep else "None",RATIONALE[pid]],1):
        c=ws1.cell(r,ci,v); dcell(c,alt)
        if ci==5: c.number_format='#,##0'
        if ci==3: c.fill=G_FILL if sb=="Selected" else Y_FILL
        if ci==4: c.fill=G_FILL if sr=="Selected" else Y_FILL
tr=len(PROJECTS)+2
ws1.cell(tr,1,"TOTALS — Baseline Selected").font=BOLD
c=ws1.cell(tr,5,BB); c.number_format='#,##0'; c.font=BOLD
ws1.cell(tr,6,BP).font=BOLD
tr2=tr+1
ws1.cell(tr2,1,"TOTALS — Reduced Capacity Selected").font=BOLD
c=ws1.cell(tr2,5,RB); c.number_format='#,##0'; c.font=BOLD
ws1.cell(tr2,6,RP).font=BOLD
ws1.row_dimensions[1].height=30
aw(ws1); ws1.column_dimensions["B"].width=30; ws1.column_dimensions["H"].width=50

# Sheet 2: Capacity
ws2=wb.create_sheet("Capacity")
for i,h in enumerate(["Month","Team","Baseline Capacity (pd)","Usage (pd)","Remaining (pd)"],1): hcell(ws2.cell(1,i,h))
r=2
for m in MONTHS:
    for t in TEAMS:
        cap=BASE_CAP[t]; u=BU[m][t]; alt=((r-2)%2==1)
        for ci,v in enumerate([m,t,cap,u,f"=C{r}-D{r}"],1):
            c=ws2.cell(r,ci,v); dcell(c,alt); c.alignment=Alignment(horizontal="center",vertical="center")
        rem=cap-u; ws2.cell(r,5).fill=G_FILL if rem>5 else (Y_FILL if rem>=0 else R_FILL); r+=1
for m in MONTHS:
    ws2.cell(r,1,f"TOTAL {m}").font=BOLD; ws2.cell(r,3,sum(BASE_CAP[t] for t in TEAMS)).font=BOLD
    ws2.cell(r,4,sum(BU[m][t] for t in TEAMS)).font=BOLD; ws2.cell(r,5,f"=C{r}-D{r}").font=BOLD; r+=1
aw(ws2)

# Sheet 3: Reduced Capacity
ws3=wb.create_sheet("Reduced Capacity")
for i,h in enumerate(["Month","Team","Reduced Capacity (pd)","Usage (pd)","Remaining (pd)"],1): hcell(ws3.cell(1,i,h))
r=2
for m in MONTHS:
    for t in TEAMS:
        cap=RED_CAP[t]; u=RU[m][t]; alt=((r-2)%2==1)
        for ci,v in enumerate([m,t,cap,u,f"=C{r}-D{r}"],1):
            c=ws3.cell(r,ci,v); dcell(c,alt); c.alignment=Alignment(horizontal="center",vertical="center")
        rem=cap-u; ws3.cell(r,5).fill=G_FILL if rem>5 else (Y_FILL if rem>=0 else R_FILL); r+=1
for m in MONTHS:
    ws3.cell(r,1,f"TOTAL {m}").font=BOLD; ws3.cell(r,3,sum(RED_CAP[t] for t in TEAMS)).font=BOLD
    ws3.cell(r,4,sum(RU[m][t] for t in TEAMS)).font=BOLD; ws3.cell(r,5,f"=C{r}-D{r}").font=BOLD; r+=1
aw(ws3)

# Sheet 4: Assumptions
ws4=wb.create_sheet("Assumptions")
ws4.column_dimensions["A"].width=32; ws4.column_dimensions["B"].width=72
hf=PatternFill("solid",fgColor="2E75B6"); hfont=Font(bold=True,color="FFFFFF",size=11)
def sec(ws,row,title,items):
    c=ws.cell(row,1,title); c.font=hfont; c.fill=hf
    c.alignment=Alignment(horizontal="left",vertical="center"); ws.merge_cells(f"A{row}:B{row}"); ws.row_dimensions[row].height=22
    for i,(k,v) in enumerate(items):
        r2=row+1+i; kc=ws.cell(r2,1,k); kc.font=Font(bold=True,size=10)
        kc.alignment=Alignment(vertical="top",wrap_text=True); kc.border=THIN
        vc=ws.cell(r2,2,v); vc.alignment=Alignment(vertical="top",wrap_text=True); vc.border=THIN
        ws.row_dimensions[r2].height=32
    return row+1+len(items)+1
r=1
r=sec(ws4,r,"SOURCE PRECEDENCE",[
    ("Authoritative sources","executive_priorities.md, delivery_constraints.md, portfolio_data.xlsx, risk_register.csv"),
    ("Non-authoritative (superseded)","prior_quarter_notes.md — retained as historical context only"),
    ("Planning period","FY2027 Q1: 2 January – 31 March 2027"),
])
r=sec(ws4,r,"OPTIMIZATION OBJECTIVE",[
    ("Primary objective","Maximize total Priority Points"),
    ("Tie-break 1","Lower total implementation budget (EUR)"),
    ("Tie-break 2","Fewer High-impact risks (per risk_register.csv)"),
    ("Budget ceiling","EUR 1,150,000"),
    ("Mandatory projects","P01, P02, P03 — cannot be deferred under any scenario"),
    ("Indivisibility","Projects must be fully funded and staffed — no partial delivery"),
    ("Effort fixity","Monthly effort profiles are fixed — no reallocation across teams or months"),
])
r=sec(ws4,r,"DEPENDENCY RULES",[
    ("P04 requires P03","AI Sales Copilot depends on EU Data Residency Foundation"),
    ("P05 requires P03","Renewal Risk Dashboard depends on EU Data Residency Foundation"),
    ("P06 requires P03","Finance Forecast Automation depends on EU Data Residency Foundation"),
    ("P08 requires P03","Support Knowledge Search depends on EU Data Residency Foundation"),
    ("P09 requires P02","Partner API v2 depends on Privileged Access Hardening"),
    ("P10 requires P03","Regional Billing Expansion depends on EU Data Residency Foundation"),
    ("P11 requires P05","Legacy Reporting Sunset depends on Renewal Risk Dashboard"),
])
r=sec(ws4,r,"EXCLUSIVITY RULES",[
    ("P04 XOR P12","AI Sales Copilot and Voice Assistant Pilot require the same specialist architecture slot in Q1. Cannot select both even if numeric capacity allows."),
])
r=sec(ws4,r,"CAPACITY CONSTRAINTS",[
    ("Baseline (pd/month)","Platform: 80 | Data: 60 | Security: 40 | Change: 40"),
    ("Reduced (pd/month)","Platform: 68 | Data: 51 | Security: 34 | Change: 34 (exactly 15% reduction)"),
    ("No carry-over","Unused capacity does not transfer between teams or months"),
    ("Zero tolerance","Over-allocation by any amount renders the plan invalid"),
])
r=sec(ws4,r,"OPTIMIZATION RESULTS — BASELINE",[
    ("Selected","P01, P02, P03, P08, P09"),
    ("Deferred","P04, P05, P06, P07, P10, P11, P12"),
    ("Total budget",f"EUR {BB:,} (EUR {1_150_000-BB:,} headroom)"),
    ("Priority Points",f"{BP} pts — maximum achievable under constraints"),
    ("Constraint violations","0 — fully feasible plan"),
])
r=sec(ws4,r,"OPTIMIZATION RESULTS — 15% REDUCED CAPACITY",[
    ("Reduced capacity","Platform: 68 | Data: 51 | Security: 34 | Change: 34 pd/month"),
    ("Selected","P01, P02, P03, P09"),
    ("Deferred","P04, P05, P06, P07, P08, P10, P11, P12"),
    ("Why P08 dropped","Feb 2027 Data team: P01+P02+P03+P09 = 38 pd. Adding P08 = 38+14 = 52 > 51 pd cap. Plan invalid."),
    ("Total budget",f"EUR {RB:,}"),
    ("Priority Points",f"{RP} pts — maximum achievable under reduced constraints"),
    ("Constraint violations","0 — fully feasible plan"),
])
r=sec(ws4,r,"SUPERSEDED PRIOR-QUARTER RECOMMENDATION",[
    ("Prior recommendation","Earlier workshop proposed selecting P04 (AI Sales Copilot) AND P12 (Voice Assistant Pilot) together in Q1."),
    ("Prior assumptions","EUR 1.8 million budget and additional contractor capacity."),
    ("Current binding constraints","EUR 1.15 million budget limit; P04 XOR P12 exclusivity; no additional contractors."),
    ("Why overridden","(1) P04+P12 violates exclusivity. (2) Budget with P04 exceeds EUR 1.15M. (3) P12 is lowest-priority project at 45 pts."),
    ("Conclusion","Prior recommendation is OVERRIDDEN. Both P04 and P12 are deferred under current authoritative constraints."),
])
wb.save(XLSX); print(f"\nExcel saved: {XLSX}")

# === POWERPOINT ===
DB=RGBColor(0x1F,0x4E,0x79); MB=RGBColor(0x2E,0x75,0xB6); LB=RGBColor(0xBD,0xD7,0xEE)
GR=RGBColor(0x70,0xAD,0x47); OR=RGBColor(0xED,0x7D,0x31); WH=RGBColor(0xFF,0xFF,0xFF)
YC=RGBColor(0xFF,0xC0,0x00); GY=RGBColor(0x40,0x40,0x40); OY=RGBColor(0xFF,0xF2,0xCC)
DY=RGBColor(0x7F,0x60,0x00); LG=RGBColor(0xC6,0xEF,0xCE); LR=RGBColor(0xFF,0xC7,0xCE)
LY=RGBColor(0xFF,0xEB,0x9C)

prs=Presentation(); prs.slide_width=Inches(13.33); prs.slide_height=Inches(7.5)
BL=prs.slide_layouts[6]
def newsl(): return prs.slides.add_slide(BL)
def rect(s,l,t,w,h,fc=None,lc=None):
    sh=s.shapes.add_shape(1,Inches(l),Inches(t),Inches(w),Inches(h))
    if fc: sh.fill.solid(); sh.fill.fore_color.rgb=fc
    else: sh.fill.background()
    if lc: sh.line.color.rgb=lc; sh.line.width=Pt(1)
    else: sh.line.fill.background()
    return sh
def txt(s,l,t,w,h,text,sz=10,bold=False,color=GY,align=PP_ALIGN.LEFT):
    tb=s.shapes.add_textbox(Inches(l),Inches(t),Inches(w),Inches(h))
    tf=tb.text_frame; tf.word_wrap=True; p=tf.paragraphs[0]; p.alignment=align
    run=p.add_run(); run.text=str(text); run.font.size=Pt(sz); run.font.bold=bold; run.font.color.rgb=color
    return tb
def hdr(s,title,sub=None):
    rect(s,0,0,13.33,1.3,fc=DB); txt(s,0.3,0.1,12.5,0.85,title,22,True,WH,PP_ALIGN.LEFT)
    if sub: txt(s,0.3,0.88,12.5,0.38,sub,10.5,False,LB,PP_ALIGN.LEFT)
    rect(s,0,1.3,13.33,0.06,fc=MB)
def foot(s):
    rect(s,0,7.2,13.33,0.3,fc=DB)
    txt(s,0.3,7.22,12.7,0.25,"CONFIDENTIAL  |  FD_02 FY2027 Q1 Portfolio Plan  |  Joule Desktop Standard",7.5,False,WH,PP_ALIGN.CENTER)
def ptbl(s,l,t,wi,rows,cws=None,rh=0.28):
    nr=len(rows); nc=len(rows[0][0])
    tab=s.shapes.add_table(nr,nc,Inches(l),Inches(t),Inches(wi),Inches(rh*nr)).table
    if cws:
        for i,w in enumerate(cws): tab.columns[i].width=Inches(w)
    for ri,(vals,is_h,fc) in enumerate(rows):
        for ci,v in enumerate(vals):
            cell=tab.cell(ri,ci); cell.text=str(v) if v is not None else ""
            tf=cell.text_frame; tf.paragraphs[0].alignment=PP_ALIGN.CENTER
            for run in tf.paragraphs[0].runs:
                run.font.size=Pt(9 if not is_h else 9.5); run.font.bold=is_h
                run.font.color.rgb=WH if is_h else GY
            if fc: cell.fill.solid(); cell.fill.fore_color.rgb=fc
    return tab

# Slide 1: Portfolio Decision Required
s1=newsl(); hdr(s1,"Portfolio Decision Required","FY2027 Q1 · Executive Committee Approval Needed · Two scenarios presented")
rect(s1,0.35,1.45,8.7,5.65,fc=RGBColor(0xF2,0xF7,0xFF),lc=MB)
txt(s1,0.5,1.5,8.4,0.35,"DECISION CONTEXT",11,True,MB)
items=[("Budget Limit","EUR 1,150,000 (hard ceiling)"),
       ("Horizon","Q1 2027: 2 Jan – 31 Mar 2027"),
       ("Mandatory","P01 Regulatory Audit  |  P02 Privileged Access  |  P03 EU Data Residency"),
       ("Objective","Maximize Priority Points — all constraints are hard"),
       ("Tie-breaks","1st: Lower budget  |  2nd: Fewer High-impact risks"),
       ("Indivisibility","Projects cannot be partially funded or staffed"),
       ("Scenario 2","15% capacity reduction — P08 dropped, 353 pts"),
       ("Prior Rec.","Prior-quarter P04+P12 recommendation SUPERSEDED"),]
y=2.02
for k,v in items:
    txt(s1,0.55,y,2.4,0.35,k+":",10,True,DB); txt(s1,2.95,y,5.9,0.35,v,10,False,GY); y+=0.435
kpis=[(f"{BP} pts","Baseline Points",f"EUR {BB//1000:,}k",GR),(f"{RP} pts","Reduced Points",f"EUR {RB//1000:,}k",OR),("EUR 1,150k","Budget Ceiling","Hard limit",MB)]
for ki,(v,t2,s2,c) in enumerate(kpis):
    x=9.3; y2=1.5+ki*1.85; rect(s1,x,y2,3.7,1.7,fc=c)
    txt(s1,x+0.1,y2+0.08,3.5,0.32,t2,10,True,WH,PP_ALIGN.CENTER)
    txt(s1,x+0.1,y2+0.42,3.5,0.7,v,24,True,WH,PP_ALIGN.CENTER)
    txt(s1,x+0.1,y2+1.2,3.5,0.32,s2,9,False,WH,PP_ALIGN.CENTER)
rect(s1,9.3,6.95,3.7,0.1,fc=YC)
txt(s1,9.3,6.45,3.7,0.45,"Note: Prior P04+P12 recommendation superseded — both deferred.",8.5,True,DY,PP_ALIGN.CENTER)
foot(s1)

# Slide 2: Constraints and Evaluation Logic
s2=newsl(); hdr(s2,"Constraints and Evaluation Logic","All constraints are hard — any violation makes the plan invalid")
coldata=[
    ("Budget & Mandatory",["Budget cap: EUR 1,150,000","Mandatory (cannot defer):","  P01 Regulatory Audit Evidence","  P02 Privileged Access Hardening","  P03 EU Data Residency Foundation","","Projects are indivisible","Effort profiles fixed — no re-allocation","","Tie-break 1: lower budget","Tie-break 2: fewer High risks"]),
    ("Dependencies & Exclusivity",["Dependencies:","  P04 requires P03","  P05 requires P03","  P06 requires P03","  P08 requires P03","  P09 requires P02","  P10 requires P03","  P11 requires P05","","Exclusivity (hard):","  P04 XOR P12 (same arch. slot)","  Cannot coexist even if capacity allows"]),
    ("Capacity Constraints",["Baseline capacity (pd/month):","  Platform:  80","  Data:      60","  Security:  40","  Change:    40","","Reduced -15% (pd/month):","  Platform:  68","  Data:      51","  Security:  34","  Change:    34","","Zero tolerance — overalloc = invalid"]),
]
for ci,(title,items2) in enumerate(coldata):
    x=0.3+ci*4.32; rect(s2,x,1.45,4.2,5.75,fc=RGBColor(0xF2,0xF7,0xFF),lc=LB)
    rect(s2,x,1.45,4.2,0.4,fc=MB); txt(s2,x+0.1,1.5,4.0,0.35,title,11,True,WH,PP_ALIGN.CENTER)
    y=1.95
    for item in items2: txt(s2,x+0.15,y,4.0,0.31,item,9.5,False,GY); y+=0.315
foot(s2)

# Slide 3: Recommended Portfolio
s3=newsl(); hdr(s3,"Recommended Portfolio — Baseline Scenario",f"5 projects selected  |  {BP} Priority Points  |  EUR {BB//1000:,}k  |  0 constraint violations")
sel_p=[p for p in PROJECTS if p[0] in BASE_SEL]; def_p=[p for p in PROJECTS if p[0] not in BASE_SEL]
rows3=[(["Project ID","Project Name","Budget (EUR k)","Priority Pts","Dependencies","Rationale"],True,DB)]
for p in sel_p:
    pid,nm,mand,bud,pts,dep=p
    short=("Mandatory" if mand else (RATIONALE[pid][:45]+"..." if len(RATIONALE[pid])>45 else RATIONALE[pid]))
    rows3.append(([pid,nm,f"{bud//1000}",str(pts),dep if dep else "None",short],False,LG))
rows3.append((["","","","","",""],False,RGBColor(0xE0,0xE0,0xE0)))
rows3.append((["TOTAL SELECTED","",f"{BB//1000:,}",str(BP),"",""],False,LG))
ptbl(s3,0.3,1.5,8.9,rows3,cws=[0.65,2.7,1.1,1.0,1.05,2.4],rh=0.32)
rect(s3,9.4,1.45,3.65,5.7,fc=OY,lc=YC)
txt(s3,9.5,1.5,3.5,0.35,"DEFERRED PROJECTS (7)",11,True,DY,PP_ALIGN.CENTER)
y=1.97
for p in def_p:
    pid,nm,_,bud,pts,dep=p; rect(s3,9.45,y,0.58,0.3,fc=YC)
    txt(s3,9.45,y,0.58,0.3,pid,8.5,True,GY,PP_ALIGN.CENTER)
    txt(s3,10.06,y,2.4,0.3,nm,8.5,False,GY); txt(s3,12.48,y,0.5,0.3,f"{pts}p",8.5,False,GY,PP_ALIGN.RIGHT); y+=0.34
for kt,kv,ks,kc in [("Budget Used",f"EUR {BB//1000:,}k",f"of 1,150k ({BB*100//1_150_000}%)",GR),("Headroom",f"EUR {(1_150_000-BB)//1000:,}k","within limit",MB),(f"Priority Points",str(BP),"Maximum feasible",DB),("Violations","0","Fully feasible",GR)]:
    x2=0.3 if kt=="Budget Used" else (2.55 if kt=="Headroom" else (4.8 if "Priority" in kt else 7.05))
    rect(s3,x2,6.3,2.1,0.9,fc=kc); txt(s3,x2+0.05,6.33,2.0,0.28,kt,8.5,True,WH,PP_ALIGN.CENTER)
    txt(s3,x2+0.05,6.6,2.0,0.38,kv,16,True,WH,PP_ALIGN.CENTER); txt(s3,x2+0.05,6.95,2.0,0.22,ks,7.5,False,WH,PP_ALIGN.CENTER)
foot(s3)

# Slide 4: Resource and Budget Allocation
s4=newsl(); hdr(s4,"Resource and Budget Allocation","Baseline scenario — team capacity vs. usage (person-days)")
cd=ChartData(); cd.categories=TEAMS
cd.add_series("Jan 2027 Usage",[BU["Jan 2027"][t] for t in TEAMS])
cd.add_series("Feb 2027 Usage",[BU["Feb 2027"][t] for t in TEAMS])
cd.add_series("Mar 2027 Usage",[BU["Mar 2027"][t] for t in TEAMS])
cd.add_series("Baseline Capacity",[BASE_CAP[t] for t in TEAMS])
ch=s4.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,Inches(0.3),Inches(1.5),Inches(7.2),Inches(4.5),cd).chart
ch.has_title=True; ch.chart_title.text_frame.text="Team Capacity vs. Monthly Usage (Baseline)"
ch.chart_title.text_frame.paragraphs[0].runs[0].font.size=Pt(11); ch.chart_title.text_frame.paragraphs[0].runs[0].font.bold=True
sc=[RGBColor(0x2E,0x75,0xB6),RGBColor(0x70,0xAD,0x47),RGBColor(0xED,0x7D,0x31),RGBColor(0xFF,0xC0,0x00)]
for i,ser in enumerate(ch.series): ser.format.fill.solid(); ser.format.fill.fore_color.rgb=sc[i]
ch.has_legend=True; ch.legend.position=3; ch.legend.include_in_layout=False
rect(s4,7.7,1.45,5.35,5.7,fc=RGBColor(0xF2,0xF7,0xFF),lc=LB)
txt(s4,7.8,1.5,5.15,0.32,"CAPACITY DETAIL (pd)",10,True,DB,PP_ALIGN.CENTER)
ct=[(["Month","Team","Cap.","Used","Rem."],True,DB)]
for m in MONTHS:
    for t in TEAMS:
        cap=BASE_CAP[t]; u=BU[m][t]; rem=cap-u
        ct.append(([m[:3],t,str(cap),str(u),str(rem)],False,LG if rem>5 else (LY if rem>=0 else LR)))
ptbl(s4,7.8,1.88,5.15,ct,cws=[0.7,1.1,0.82,0.75,0.78],rh=0.255)
rect(s4,0.3,6.1,12.8,1.05,fc=RGBColor(0xF2,0xF2,0xF2),lc=MB)
txt(s4,0.4,6.12,12.6,0.28,"BUDGET BREAKDOWN — BASELINE SELECTED PROJECTS",10,True,DB)
x3=0.45; scale=11.2/BB
bc=[MB,GR,DB,OR,RGBColor(0x9E,0x48,0x0E)]
for pi,p in enumerate(sel_p):
    pid,nm,_,bud,pts,dep=p; w=bud*scale; rect(s4,x3,6.45,w,0.5,fc=bc[pi])
    if w>0.7: txt(s4,x3+0.04,6.47,w-0.08,0.25,f"{pid}: {bud//1000}k",8,True,WH,PP_ALIGN.CENTER); x3+=w+0.04
foot(s4)

# Slide 5: Risks, Dependencies and Deferred Initiatives
s5=newsl(); hdr(s5,"Risks, Dependencies and Deferred Initiatives","Selected portfolio carries 4 High-impact risks — all have active mitigations")
RISKS={"P01":("Evidence schema approval slips","Medium","High","Freeze schema by 10 Feb; escalate unresolved fields"),
       "P02":("Privileged workflow regression","Medium","High","Staged rollout, break-glass testing, rollback"),
       "P03":("Data migration misses regional records","High","High","Dual-write reconciliation, region-level checks"),
       "P07":("Accessibility regressions in redesign","Medium","High","WCAG regression testing before release"),
       "P08":("Search surfaces stale guidance","Medium","High","Freshness filters and source-owner review"),
       "P09":("Partner migration breaks legacy clients","Medium","High","Compat tests, migration telemetry, rollback"),
       "P04":("Sales adoption below forecast","Medium","Medium","Pilot 2 regions; adoption exit criteria"),
       "P05":("False-positive renewal alerts","Medium","Medium","Back-test against prior renewals; monitor"),
       "P06":("Forecast explanations reduce trust","Low","Medium","Source-linked variance; manual approval"),
       "P10":("Localization misses tax requirement","Low","High","Market-specific tax sign-off"),
       "P11":("Report retired too early","Medium","Medium","Confirm equivalence; owner acceptance"),
       "P12":("Voice recognition poor in field","High","Medium","Controlled eval; minimum accuracy gate"),}
txt(s5,0.3,1.42,8.1,0.3,"RISK REGISTER — SELECTED PROJECTS (BASELINE)",10,True,DB)
rr=[(["ID","Risk Description","Prob.","Impact","Mitigation"],True,DB)]
for pid in sorted(BASE_SEL):
    ri2,prob,impact,mit=RISKS[pid]
    rr.append(([pid,ri2[:52],prob,impact,mit[:48]],False,LR if impact=="High" else (LY if impact=="Medium" else None)))
ptbl(s5,0.3,1.78,8.1,rr,cws=[0.52,2.9,0.65,0.75,3.28],rh=0.3)
rect(s5,8.55,1.42,4.5,3.8,fc=RGBColor(0xF2,0xF7,0xFF),lc=LB)
txt(s5,8.65,1.47,4.3,0.32,"DEPENDENCY STATUS",10,True,DB,PP_ALIGN.CENTER)
deps=[("P01","No dependencies — standalone",GR),("P02","No dependencies — standalone",GR),
      ("P03","Prerequisite: enables P04,05,06,08,10",GR),("P08","P03 selected — dependency OK",GR),
      ("P09","P02 selected — dependency OK",GR),("P04","P03 OK but budget+excl. block",LY),
      ("P05","P03 OK but budget blocks",LY),("P11","P05 NOT selected — BLOCKED",LR),]
y5=1.87
for dpid,note,dc in deps:
    rect(s5,8.6,y5,0.52,0.29,fc=dc); txt(s5,8.6,y5,0.52,0.29,dpid,8.5,True,GY if dc==LY or dc==LR else WH,PP_ALIGN.CENTER)
    txt(s5,9.15,y5,3.75,0.29,note,8.5,False,GY); y5+=0.32
rect(s5,0.3,5.25,12.75,1.6,fc=OY,lc=YC)
txt(s5,0.4,5.28,12.55,0.3,"DEFERRED PROJECTS — BASELINE (7 initiatives, EUR "+f"{sum(p[3] for p in def_p)//1000:,}k total)",10,True,DY)
x5=0.45
for p in def_p:
    pid,nm,_,bud,pts,dep=p; rect(s5,x5,5.65,1.72,0.65,fc=LY,lc=GY)
    txt(s5,x5+0.05,5.67,1.62,0.25,pid,9,True,GY,PP_ALIGN.CENTER)
    txt(s5,x5+0.05,5.93,1.62,0.2,(nm[:16]+"..." if len(nm)>16 else nm),7.5,False,GY,PP_ALIGN.CENTER)
    txt(s5,x5+0.05,6.12,1.62,0.15,f"EUR{bud//1000}k | {pts}pts",7,False,GY,PP_ALIGN.CENTER); x5+=1.83
foot(s5)

# Slide 6: 15% Capacity Reduction
s6=newsl(); hdr(s6,"15% Capacity-Reduction Scenario — Decision Required",f"4 projects  |  {RP} Priority Points  |  EUR {RB//1000:,}k  |  P08 deferred — Data capacity exceeded")
txt(s6,0.3,1.42,12.7,0.3,"SCENARIO COMPARISON: BASELINE vs. 15%-REDUCED CAPACITY",11,True,DB)
comp=[(["Metric","Baseline","15% Reduced","Impact"],True,DB),
      (["Platform capacity","80 pd/mo","68 pd/mo","-12 pd"],False,None),
      (["Data capacity","60 pd/mo","51 pd/mo","-9 pd"],False,None),
      (["Security capacity","40 pd/mo","34 pd/mo","-6 pd"],False,None),
      (["Change capacity","40 pd/mo","34 pd/mo","-6 pd"],False,None),
      (["Projects selected","P01 P02 P03 P08 P09","P01 P02 P03 P09","P08 dropped"],False,LR),
      (["# Projects","5","4","-1"],False,LR),
      ([f"Priority Points",f"{BP}",f"{RP}",f"-{BP-RP}"],False,LR),
      (["Budget (EUR k)",f"{BB//1000:,}",f"{RB//1000:,}",f"-{(BB-RB)//1000:,}"],False,LY),
      (["Constraint violations","0","0","None"],False,LG),]
ptbl(s6,0.3,1.82,12.7,comp,cws=[2.6,3.4,3.4,3.3],rh=0.32)
rect(s6,0.3,5.1,6.15,2.0,fc=RGBColor(0xF2,0xF7,0xFF),lc=MB)
txt(s6,0.4,5.15,5.95,0.3,"REDUCED CAPACITY USAGE (pd)",10,True,DB)
rc=[(["Month","Team","Cap.","Used","Rem."],True,DB)]
for m in MONTHS:
    for t in TEAMS:
        c=RED_CAP[t]; u=RU[m][t]; rem=c-u
        rc.append(([m[:3],t,str(c),str(u),str(rem)],False,LG if rem>5 else (LY if rem>=0 else LR)))
ptbl(s6,0.35,5.52,6.05,rc,cws=[0.65,1.1,0.82,0.75,0.73],rh=0.235)
rect(s6,6.65,5.1,6.35,2.0,fc=OY,lc=YC)
txt(s6,6.75,5.15,6.15,0.3,"WHY P08 DEFERRED IN REDUCED SCENARIO",10,True,DY)
p08l=["P08 Data effort: Jan=10, Feb=14, Mar=12 pd",
      "P01+P02+P03+P09 Data usage:",
      "  Jan: 10+2+18+2 = 32 pd  (cap 51 OK)",
      "  Feb: 12+2+20+4 = 38 pd  (cap 51 OK)",
      "  Mar:  8+1+14+3 = 26 pd  (cap 51 OK)",
      "Adding P08 in Feb: 38+14 = 52 pd",
      "Reduced Feb Data cap = 51 pd",
      "52 > 51  -- OVER-ALLOCATION -- Plan invalid"]
y6=5.5
for line in p08l:
    txt(s6,6.8,y6,6.1,0.23,line,9,"OVER-ALLOCATION" in line,GY); y6+=0.225
rect(s6,0.3,7.0,12.7,0.18,fc=DB)
txt(s6,0.35,7.02,12.6,0.15,"DECISION REQUEST: Approve Baseline Portfolio (P01+P02+P03+P08+P09 | EUR 1,130k | 425 pts) OR confirm 15% capacity reduction applies (4 projects | EUR 970k | 353 pts).",8.5,True,WH,PP_ALIGN.LEFT)
foot(s6)

prs.save(PPTX_PATH); print(f"PowerPoint saved: {PPTX_PATH}")

# === VERIFY ===
print("\n=== VERIFICATION ===")
wb2=openpyxl.load_workbook(XLSX)
print(f"Excel sheets: {wb2.sheetnames}")
assert set(wb2.sheetnames)=={"Portfolio","Capacity","Reduced Capacity","Assumptions"}
print("All 4 Excel sheets present: PASS")
from pptx import Presentation as P2
prs2=P2(PPTX_PATH); n=len(prs2.slides)
print(f"PowerPoint slides: {n}"); assert n==6
print("All 6 slides present: PASS")
ws_p=wb2["Portfolio"]
for row in ws_p.iter_rows(values_only=True):
    if row[0] and "Baseline" in str(row[0]) and "TOTAL" in str(row[0]):
        assert row[4]==BB,f"Budget mismatch {row[4]} vs {BB}"
        assert row[5]==BP,f"Points mismatch {row[5]} vs {BP}"
        print(f"Budget={row[4]:,} Points={row[5]} match expected values: PASS"); break
print(f"\nOutput files saved:")
print(f"  {XLSX}")
print(f"  {PPTX_PATH}")
print(f"\nBaseline: {sorted(BASE_SEL)} | EUR {BB:,} | {BP} pts")
print(f"Reduced:  {sorted(RED_SEL)} | EUR {RB:,} | {RP} pts")
print("\nAll verifications PASSED.")
