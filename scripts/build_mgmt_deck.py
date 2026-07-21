#!/usr/bin/env python3
"""Managementdeck voor de testautomatisering-business-case.

Leest de laatste (of opgegeven) testauto_businesscase_*.json en bouwt een
PowerPoint in beslisser-taal: testdagen als eenheid, ronde getallen, en een
waardestroom-tijdlijn (actieve tijd vs wachttijd per stap).

Gebruik:
    uv run --with python-pptx python scripts/build_mgmt_deck.py
    ... [--json output/testauto_businesscase_<ts>.json] [--out output/deck.pptx]
"""

from __future__ import annotations

import argparse
import glob
import json
from datetime import date
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

_OUT = Path("output")  # relatief aan de werkdirectory

DARK = RGBColor(0x00, 0x30, 0x82)
ACCENT = RGBColor(0x00, 0x9F, 0xE3)
GREY = RGBColor(0x58, 0x58, 0x58)
RED = RGBColor(0xC0, 0x39, 0x2B)
GREEN = RGBColor(0x1E, 0x84, 0x49)
LIGHT = RGBColor(0xE8, 0xF1, 0xFA)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)


def _r(x: float) -> int:
    """Ronde af op hele eenheden — managers lezen geen decimalen."""
    return int(round(x))


class Deck:
    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width = Inches(13.333)
        self.prs.slide_height = Inches(7.5)
        self.W = self.prs.slide_width
        self.H = self.prs.slide_height

    def slide(self):
        return self.prs.slides.add_slide(self.prs.slide_layouts[6])

    def box(self, s, x, y, w, h):
        tb = s.shapes.add_textbox(Emu(int(x)), Emu(int(y)), Emu(int(w)), Emu(int(h)))
        tb.text_frame.word_wrap = True
        return tb.text_frame

    def title(self, s, text, sub=""):
        bar = s.shapes.add_shape(1, 0, 0, self.W, Inches(1.05))
        bar.fill.solid()
        bar.fill.fore_color.rgb = DARK
        bar.line.fill.background()
        tf = bar.text_frame
        tf.margin_left = Inches(0.5)
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = text
        r.font.size = Pt(28)
        r.font.bold = True
        r.font.color.rgb = WHITE
        if sub:
            p2 = tf.add_paragraph()
            r2 = p2.add_run()
            r2.text = sub
            r2.font.size = Pt(13)
            r2.font.color.rgb = RGBColor(0xBF, 0xDC, 0xF5)

    def bullets(self, tf, items, size=20):
        first = True
        for level, text, bold in items:
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            p.level = level
            p.space_after = Pt(10)
            r = p.add_run()
            r.text = ("• " if level == 0 else "– ") + text
            r.font.size = Pt(size - 3 * level)
            r.font.color.rgb = RGBColor(0x20, 0x20, 0x20)
            if bold:
                r.font.bold = True
                r.font.color.rgb = DARK

    def table(self, s, x, y, w, rows, col_w=None, size=15):
        t = s.shapes.add_table(len(rows), len(rows[0]), Emu(int(x)), Emu(int(y)),
                               Emu(int(w)), Inches(0.45 * len(rows))).table
        if col_w:
            total = sum(col_w)
            for i, cw in enumerate(col_w):
                t.columns[i].width = Emu(int(w * cw / total))
        for ri, row in enumerate(rows):
            for ci, val in enumerate(row):
                cell = t.cell(ri, ci)
                cell.margin_top = cell.margin_bottom = Pt(3)
                p = cell.text_frame.paragraphs[0]
                r = p.add_run()
                r.text = str(val)
                r.font.size = Pt(size)
                if ri == 0:
                    r.font.bold = True
                    r.font.color.rgb = WHITE
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = DARK
                else:
                    r.font.color.rgb = RGBColor(0x20, 0x20, 0x20)
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = LIGHT if ri % 2 else WHITE
        return t

    def kpi(self, s, x, y, w, value, label, color=DARK, h=1.6):
        card = s.shapes.add_shape(5, Emu(int(x)), Emu(int(y)), Emu(int(w)), Inches(h))
        card.fill.solid()
        card.fill.fore_color.rgb = LIGHT
        card.line.color.rgb = color
        tf = card.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = value
        r.font.size = Pt(32)
        r.font.bold = True
        r.font.color.rgb = color
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run()
        r2.text = label
        r2.font.size = Pt(13)
        r2.font.color.rgb = GREY

    def save(self, path):
        self.prs.save(path)
        return len(self.prs.slides._sldIdLst)


def _vsm_row(d: Deck, s, y, steps, *, label, active_key="active_days",
             wait_key="wait_days", show_ca=True):
    """Eén waardestroom-rij: blokken (werk) met klokjes (wachttijd) ertussen."""
    x = Inches(0.6)
    bw, gap = Inches(1.75), Inches(0.62)
    tf = d.box(s, Inches(0.6), y - Inches(0.42), Inches(6.0), Inches(0.35))
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = label
    r.font.size = Pt(15)
    r.font.bold = True
    r.font.color.rgb = DARK
    for i, st in enumerate(steps):
        blok = s.shapes.add_shape(5, x, y, bw, Inches(0.85))
        blok.fill.solid()
        blok.fill.fore_color.rgb = DARK
        blok.line.fill.background()
        tfb = blok.text_frame
        tfb.word_wrap = True
        pb = tfb.paragraphs[0]
        pb.alignment = PP_ALIGN.CENTER
        rb = pb.add_run()
        rb.text = st["step"].replace(" (development)", "").replace(" / oplevering", "")
        rb.font.size = Pt(12)
        rb.font.bold = True
        rb.font.color.rgb = WHITE
        # actieve tijd onder het blok
        tfa = d.box(s, x, y + Inches(0.9), bw, Inches(0.3))
        pa = tfa.paragraphs[0]
        pa.alignment = PP_ALIGN.CENTER
        ra = pa.add_run()
        ra.text = f"{_r(st[active_key])} d werk"
        ra.font.size = Pt(12)
        ra.font.bold = True
        ra.font.color.rgb = ACCENT
        if show_ca and st.get("ca_pct") is not None:
            tfc = d.box(s, x, y + Inches(1.18), bw, Inches(0.3))
            pc = tfc.paragraphs[0]
            pc.alignment = PP_ALIGN.CENTER
            rc = pc.add_run()
            rc.text = f"{st['ca_pct']}% goed"
            rc.font.size = Pt(11)
            rc.font.color.rgb = RED if st["ca_pct"] < 90 else GREY
        x += bw
        if i < len(steps) - 1:
            wait = st[wait_key]
            klok = s.shapes.add_shape(9, x + Inches(0.08), y + Inches(0.16),
                                      Inches(0.46), Inches(0.46))
            klok.fill.solid()
            klok.fill.fore_color.rgb = RED if wait >= 5 else RGBColor(0xE0, 0xE0, 0xE0)
            klok.line.color.rgb = GREY
            tfw = d.box(s, x, y + Inches(0.9), gap, Inches(0.3))
            pw = tfw.paragraphs[0]
            pw.alignment = PP_ALIGN.CENTER
            rw = pw.add_run()
            rw.text = f"{_r(wait)} d"
            rw.font.size = Pt(11)
            rw.font.color.rgb = RED if wait >= 5 else GREY
            x += gap


def build(data: dict, out_path: Path) -> int:
    vs = data["value_stream"]
    tot = vs["totals"]
    auto = vs["automated_scenario"]
    rm = data["testrail_run"]
    ep = rm["effort_proxy"]
    testdagen = sum(v["active_days"] for v in ep["per_tester"].values())
    per_tester = sorted(ep["per_tester"].values(), key=lambda v: -v["results"])
    tot_res = sum(v["results"] for v in per_tester)
    d = Deck()

    # 1. titel
    s = d.slide()
    bg = s.shapes.add_shape(1, 0, 0, d.W, d.H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = DARK
    bg.line.fill.background()
    tf = d.box(s, Inches(0.8), Inches(2.4), Inches(11.7), Inches(2.6))
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "Regressietesten automatiseren — incassoproces"
    r.font.size = Pt(40)
    r.font.bold = True
    r.font.color.rgb = WHITE
    p2 = tf.add_paragraph()
    r2 = p2.add_run()
    r2.text = "Beslisvoorstel, onderbouwd met gemeten test- en Jira-data"
    r2.font.size = Pt(22)
    r2.font.color.rgb = ACCENT
    p3 = tf.add_paragraph()
    r3 = p3.add_run()
    r3.text = (f"Gemeten: één complete regressieronde (jan–feb 2026) + 3 jaar "
               f"testhistorie · {date.today().strftime('%d-%m-%Y')}")
    r3.font.size = Pt(14)
    r3.font.color.rgb = RGBColor(0xBF, 0xDC, 0xF5)

    # 2. de situatie
    s = d.slide()
    d.title(s, "De situatie")
    tf = d.box(s, Inches(0.7), Inches(1.6), Inches(12.0), Inches(5.4))
    d.bullets(tf, [
        (0, "We gaan het incassoproces vernieuwen en vereenvoudigen.", True),
        (1, "Om veilig te kunnen wijzigen willen we elke week (of elke sprint) "
            "een volledige regressietest draaien.", False),
        (0, "Eén handmatige regressieronde duurt 5 weken en houdt één tester "
            "bezig.", True),
        (1, "Gemeten aan de laatste complete ronde (35 testgevallen, "
            "jan–feb 2026).", False),
        (0, "Wekelijks handmatig testen kan dus simpelweg niet.", True),
        (1, "In de praktijk gebeurt het ook niet: de afgelopen 3 jaar zijn er per "
            "jaar maar een handvol regressietests echt uitgevoerd.", False),
        (1, "Van de 2.868 testgevallen is er vandaag 1 geautomatiseerd.", False),
    ], size=22)

    # 3. tijdlijn (waardestroom) — nu vs straks
    s = d.slide()
    d.title(s, "Tijdlijn: waar gaat de tijd heen?",
            "Blauw = werk · rood klokje = wachten · alles in werkdagen")
    _vsm_row(d, s, Inches(1.55), vs["steps"],
             label="NU — handmatig testen")
    _vsm_row(d, s, Inches(4.15), auto["steps"],
             label="STRAKS — met geautomatiseerde regressie")
    tf = d.box(s, Inches(0.6), Inches(6.35), Inches(12.2), Inches(1.0))
    d.bullets(tf, [
        (0, f"Nu: {_r(tot['lead_time_days'])} werkdagen van bouw tot oplevering — "
            f"{_r(tot['wait_days'])} daarvan is wachten. "
            f"Straks: {_r(auto['lead_time_days'])} werkdagen.", True),
        (0, "De grootste winst zit in de testuitvoering en de hertestlus: van "
            "dagen wachten naar uren.", False),
    ], size=16)

    # 4. wat kost één ronde nu
    s = d.slide()
    d.title(s, "Wat kost één handmatige regressieronde?",
            f"Gemeten: {rm['tests']} testgevallen, {rm['results']} uitvoeringen, "
            f"jan–feb 2026")
    xs = [Inches(0.5), Inches(3.75), Inches(7.0), Inches(10.25)]
    cw = Inches(3.0)
    d.kpi(s, xs[0], Inches(1.45), cw, "5 weken", "doorlooptijd (25 werkdagen)")
    d.kpi(s, xs[1], Inches(1.45), cw, f"{_r(testdagen)} testdagen",
          "totale inzet — ≈ 1 tester, 5 weken lang")
    d.kpi(s, xs[2], Inches(1.45), cw, "8 werkdagen",
          "alles stil: wachten op bugfixes", RED)
    d.kpi(s, xs[3], Inches(1.45), cw, f"{len(rm['defects'])} bugs",
          "gevonden; elke bug kost ±2 weken extra", RED)
    tf = d.box(s, Inches(0.7), Inches(3.5), Inches(5.8), Inches(0.5))
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "Werkverdeling (geanonimiseerd):"
    r.font.size = Pt(18)
    r.font.bold = True
    r.font.color.rgb = DARK
    labels = ["A", "B", "C", "D"]
    rows = [["Tester", "Testdagen", "Aandeel"]]
    for lbl, v in zip(labels, per_tester[:2]):
        rows.append([lbl, v["active_days"],
                     f"{_r(100 * v['results'] / tot_res)}% van de uitvoeringen"])
    rest = per_tester[2:]
    if rest:
        rows.append(["C + D", sum(v["active_days"] for v in rest),
                     f"{_r(100 * sum(v['results'] for v in rest) / tot_res)}%"])
    d.table(s, Inches(0.7), Inches(4.1), Inches(5.8), rows,
            col_w=[1, 1, 2.4], size=15)
    tf = d.box(s, Inches(7.0), Inches(4.1), Inches(5.8), Inches(2.8))
    d.bullets(tf, [
        (0, "Geen team van 4: twee mensen deden 95% van het werk.", True),
        (0, f"Elke test is gemiddeld {_r(rm['executions_per_test']['mean'])}× "
            f"uitgevoerd (falen → bugfix → opnieuw).", False),
        (0, "Testen op zich is snel; het meeste van de 5 weken is wachten en "
            "coördineren.", False),
    ], size=17)

    # 5. de rekensom
    s = d.slide()
    d.title(s, "De rekensom op één A4",
            "Alles in testdagen — details en aannames in de bijlage")
    d.table(s, Inches(0.7), Inches(1.5), Inches(11.9),
            [["", "Vraag", "Antwoord"],
             ["1", "Wat kost één ronde handmatig?",
              "±13 testdagen werk (bandbreedte 7–26) en 5 weken doorlooptijd"],
             ["2", "Hoe vaak willen we een ronde?",
              "elke week — of minimaal elke sprint (3 weken)"],
             ["3", "Wat kost automatiseren (eenmalig)?",
              "40–80 dagen bouwen (80 testgevallen), plus bijhouden bij "
              "proceswijzigingen"],
             ["4", "Wat levert elke ronde dan op?",
              "±13 testdagen bespaard, en de uitslag in uren i.p.v. weken"],
             ["5", "Wanneer terugverdiend?",
              "na ±5 rondes — bij wekelijks draaien: binnen een kwartaal"]],
            col_w=[0.4, 3.6, 7.9], size=16)
    d.kpi(s, Inches(0.7), Inches(4.8), Inches(5.8), "binnen 1 kwartaal",
          "terugverdiend bij wekelijks draaien", GREEN, h=1.4)
    d.kpi(s, Inches(7.0), Inches(4.8), Inches(5.8), "1 tester vrijgespeeld",
          "elke ronde — voor het verbeterwerk zelf", GREEN, h=1.4)
    tf = d.box(s, Inches(0.7), Inches(6.5), Inches(12.0), Inches(0.7))
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = ("Let op: automatiseren van alléén de huidige praktijk loont niet — er "
              "wordt nu nauwelijks geregresseerd. De winst zit in wat het mogelijk "
              "maakt.")
    r.font.size = Pt(14)
    r.font.italic = True
    r.font.color.rgb = GREY

    # 6. waarom nu
    s = d.slide()
    d.title(s, "Waarom nu beslissen?")
    tf = d.box(s, Inches(0.7), Inches(1.6), Inches(12.0), Inches(5.4))
    d.bullets(tf, [
        (0, "Het proces wijzigt continu — en juist dan is een vangnet nodig.", True),
        (1, "Per jaar draaien er 300 tot 1.100 tests voor wijzigingen; een "
            "regressie-vangnet daaromheen ontbreekt.", False),
        (0, "Bugs zijn nu traag en duur.", True),
        (1, "Elke gevonden bug kost ±2 weken: ±1 week repareren, ±1 week wachten "
            "op hertest. Geautomatiseerd is de hertest er binnen een dag.", False),
        (0, "De laatste regressieronde dekte niet alles.", True),
        (1, "5 van de 11 processtappen (W050, W070, W080, W085, W090) zaten er "
            "niet in — het vangnet heeft nu al gaten.", False),
        (0, "De drukste stappen zijn bekend: W010, W040 en W100.", True),
        (1, "Daar zitten de meeste wijzigingen én alle recente bugs — dáár begint "
            "de pilot.", False),
    ], size=20)

    # 7. gevraagd besluit
    s = d.slide()
    d.title(s, "Gevraagd besluit")
    tf = d.box(s, Inches(0.7), Inches(1.6), Inches(12.0), Inches(4.6))
    d.bullets(tf, [
        (0, "1.  Start een automatiseringspilot op de drie drukste processtappen "
            "(W010, W040, W100).", True),
        (1, "Meet in de pilot de echte bouw- en onderhoudsdagen — dat vervangt de "
            "aannames in de rekensom.", False),
        (0, "2.  Kies de testcadans: elke week of elke sprint.", True),
        (1, "Dit bepaalt de terugverdientijd (kwartaal vs. jaar).", False),
        (0, "3.  Registreer voortaan de testtijd in TestRail.", True),
        (1, "Kost niets, en maakt de volgende beslissing meetbaar in plaats van "
            "geschat.", False),
    ], size=20)
    tf = d.box(s, Inches(0.7), Inches(6.7), Inches(12.0), Inches(0.5))
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = ("Bijlage beschikbaar: volledige data-analyse (rapport + cijfers), "
              "reproduceerbaar uit Jira en TestRail.")
    r.font.size = Pt(12)
    r.font.color.rgb = GREY

    return d.save(out_path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=None,
                    help="Analyse-JSON (default: nieuwste in output/)")
    ap.add_argument("--out", default=str(_OUT / "testauto_businesscase_mgmt.pptx"))
    args = ap.parse_args()

    matches = sorted(glob.glob(str(_OUT / "testauto_businesscase_*.json")))
    if not args.json and not matches:
        raise SystemExit(f"Geen analyse-JSON gevonden in {_OUT}/ — draai eerst "
                         f"testauto_businesscase.py, of geef --json op.")
    path = args.json or matches[-1]
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "value_stream" not in data:
        raise SystemExit(f"{path} bevat geen value_stream — draai eerst "
                         f"scripts/testauto_businesscase.py opnieuw.")
    n = build(data, Path(args.out))
    print(f"✓ {args.out} — {n} slides (bron: {Path(path).name})")


if __name__ == "__main__":
    main()
