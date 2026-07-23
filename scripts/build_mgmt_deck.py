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
import sys
from datetime import date
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_content as dc  # noqa: E402 — naast dit script

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


def _vsm_row(d: Deck, s, y, rows, *, label):
    """Eén waardestroom-rij: blokken (werk) met klokjes (wachttijd) ertussen.

    `rows` komt uit het bewerkbare checkpoint (deck_content, sleutel
    tijdlijn.rijen_*): per stap [naam, werkdagen, wachtdagen, ca% of '-',
    marker]. Zo bepaalt de bewerkte md élk label en getal op deze dia."""
    x = Inches(0.6)
    bw, gap = Inches(1.75), Inches(0.62)
    tf = d.box(s, Inches(0.6), y - Inches(0.42), Inches(6.0), Inches(0.35))
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = label
    r.font.size = Pt(15)
    r.font.bold = True
    r.font.color.rgb = DARK
    for i, cells in enumerate(rows):
        name = cells[0]
        active = _r(float(cells[1])) if len(cells) > 1 and cells[1] else 0
        wait = _r(float(cells[2])) if len(cells) > 2 and cells[2] else 0
        ca_raw = cells[3] if len(cells) > 3 else "-"
        ca = None if ca_raw in ("", "-") else int(float(ca_raw))
        marker = cells[4] if len(cells) > 4 else ""
        blok = s.shapes.add_shape(5, x, y, bw, Inches(0.85))
        blok.fill.solid()
        blok.fill.fore_color.rgb = DARK
        blok.line.fill.background()
        tfb = blok.text_frame
        tfb.word_wrap = True
        pb = tfb.paragraphs[0]
        pb.alignment = PP_ALIGN.CENTER
        rb = pb.add_run()
        rb.text = name + (" *" if marker else "")
        rb.font.size = Pt(12)
        rb.font.bold = True
        rb.font.color.rgb = WHITE
        # actieve tijd onder het blok
        tfa = d.box(s, x, y + Inches(0.9), bw, Inches(0.3))
        pa = tfa.paragraphs[0]
        pa.alignment = PP_ALIGN.CENTER
        ra = pa.add_run()
        ra.text = f"{active} d werk"
        ra.font.size = Pt(12)
        ra.font.bold = True
        ra.font.color.rgb = ACCENT
        if ca is not None:
            tfc = d.box(s, x, y + Inches(1.18), bw, Inches(0.3))
            pc = tfc.paragraphs[0]
            pc.alignment = PP_ALIGN.CENTER
            rc = pc.add_run()
            rc.text = f"{ca}% goed"
            rc.font.size = Pt(11)
            rc.font.color.rgb = RED if ca < 90 else GREY
        x += bw
        if i < len(rows) - 1:
            klok = s.shapes.add_shape(9, x + Inches(0.08), y + Inches(0.16),
                                      Inches(0.46), Inches(0.46))
            klok.fill.solid()
            klok.fill.fore_color.rgb = RED if wait >= 5 else RGBColor(0xE0, 0xE0, 0xE0)
            klok.line.color.rgb = GREY
            tfw = d.box(s, x, y + Inches(0.9), gap, Inches(0.3))
            pw = tfw.paragraphs[0]
            pw.alignment = PP_ALIGN.CENTER
            rw = pw.add_run()
            rw.text = f"{wait} d"
            rw.font.size = Pt(11)
            rw.font.color.rgb = RED if wait >= 5 else GREY
            x += gap


def build(data: dict, content: dict[str, str], f: dict, out_path: Path) -> int:
    """Render het deck. ALLE zichtbare tekst komt uit `content` (het bewerkbare
    checkpoint); `f` levert alleen de testertabel. `data` wordt niet meer voor
    tekst gelezen — zo bepaalt een bewerkte deck_content.md het hele deck."""
    def C(k, default=""):
        return content.get(k) or default
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
    r.text = C("titel.kop")
    r.font.size = Pt(40)
    r.font.bold = True
    r.font.color.rgb = WHITE
    p2 = tf.add_paragraph()
    r2 = p2.add_run()
    r2.text = C("titel.sub")
    r2.font.size = Pt(22)
    r2.font.color.rgb = ACCENT
    p3 = tf.add_paragraph()
    r3 = p3.add_run()
    r3.text = f"{C('titel.voet')} · {date.today().strftime('%d-%m-%Y')}"
    r3.font.size = Pt(14)
    r3.font.color.rgb = RGBColor(0xBF, 0xDC, 0xF5)

    # 2. de situatie
    s = d.slide()
    d.title(s, C("situatie.kop"))
    tf = d.box(s, Inches(0.7), Inches(1.6), Inches(12.0), Inches(5.4))
    d.bullets(tf, dc.bullets(C("situatie.bullets")), size=22)

    # 3. tijdlijn (waardestroom) — nu vs straks. Rijen komen uit het checkpoint;
    # oude checkpoints zonder die sleutels vallen terug op de JSON-stappen.
    s = d.slide()
    d.title(s, C("tijdlijn.kop"), C("tijdlijn.sub"))
    default_nu = dc._vsm_rows(data["value_stream"]["steps"])
    default_straks = dc._vsm_rows(data["value_stream"]["automated_scenario"]["steps"])
    _vsm_row(d, s, Inches(1.55), dc.pipe_rows(C("tijdlijn.rijen_nu", default_nu)),
             label=C("tijdlijn.nu"))
    _vsm_row(d, s, Inches(4.15),
             dc.pipe_rows(C("tijdlijn.rijen_straks", default_straks)),
             label=C("tijdlijn.straks"))
    tf = d.box(s, Inches(0.6), Inches(6.15), Inches(12.2), Inches(1.2))
    d.bullets(tf, dc.bullets(C("tijdlijn.bullets")), size=16)
    voet = C("tijdlijn.voet")
    if voet:
        tfv = d.box(s, Inches(0.6), Inches(7.02), Inches(12.2), Inches(0.35))
        pv = tfv.paragraphs[0]
        rv = pv.add_run()
        rv.text = voet
        rv.font.size = Pt(11)
        rv.font.italic = True
        rv.font.color.rgb = GREY

    # 4. wat kost één ronde nu
    s = d.slide()
    d.title(s, C("ronde.kop"), C("ronde.sub"))
    xs = [Inches(0.5), Inches(3.75), Inches(7.0), Inches(10.25)]
    cw = Inches(3.0)
    for i, (key, colour) in enumerate([("ronde.kpi1", DARK), ("ronde.kpi2", DARK),
                                       ("ronde.kpi3", RED), ("ronde.kpi4", RED)]):
        value, _, label = C(key).partition("|")
        d.kpi(s, xs[i], Inches(1.45), cw, value.strip(), label.strip(), colour)
    tf = d.box(s, Inches(0.7), Inches(3.5), Inches(5.8), Inches(0.5))
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = C("ronde.tabelkop", "Werkverdeling (geanonimiseerd):")
    r.font.size = Pt(18)
    r.font.bold = True
    r.font.color.rgb = DARK
    d.table(s, Inches(0.7), Inches(4.1), Inches(5.8), f["tester_table"],
            col_w=[1, 1, 2.4], size=15)
    tf = d.box(s, Inches(7.0), Inches(4.1), Inches(5.8), Inches(2.8))
    d.bullets(tf, dc.bullets(C("ronde.bullets")), size=17)

    # 5. de rekensom
    s = d.slide()
    d.title(s, C("rekensom.kop"), C("rekensom.sub"))
    kopregel = dc.pipe_rows(C("rekensom.kopregel", "|Vraag|Antwoord"))
    d.table(s, Inches(0.7), Inches(1.5), Inches(11.9),
            kopregel + dc.pipe_rows(C("rekensom.rows")),
            col_w=[0.4, 3.6, 7.9], size=16)
    for x, key in ((Inches(0.7), "rekensom.kpi1"), (Inches(7.0), "rekensom.kpi2")):
        value, _, label = C(key).partition("|")
        d.kpi(s, x, Inches(4.8), Inches(5.8), value.strip(), label.strip(),
              GREEN, h=1.4)
    tf = d.box(s, Inches(0.7), Inches(6.5), Inches(12.0), Inches(0.7))
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = C("rekensom.voet")
    r.font.size = Pt(14)
    r.font.italic = True
    r.font.color.rgb = GREY

    # 6. waarom nu
    s = d.slide()
    d.title(s, C("waarom.kop"))
    tf = d.box(s, Inches(0.7), Inches(1.6), Inches(12.0), Inches(5.4))
    d.bullets(tf, dc.bullets(C("waarom.bullets")), size=20)

    # 7. gevraagd besluit
    s = d.slide()
    d.title(s, C("besluit.kop"))
    tf = d.box(s, Inches(0.7), Inches(1.6), Inches(12.0), Inches(4.6))
    d.bullets(tf, dc.bullets(C("besluit.bullets")), size=20)
    tf = d.box(s, Inches(0.7), Inches(6.7), Inches(12.0), Inches(0.5))
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = C("besluit.voet")
    r.font.size = Pt(12)
    r.font.color.rgb = GREY

    return d.save(out_path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=None,
                    help="Analyse-JSON (default: nieuwste in output/)")
    ap.add_argument("--content", default=None,
                    help="Bewerkt deck_content.md; zonder deze vlag wordt de "
                         "tekst rechtstreeks uit de JSON afgeleid")
    ap.add_argument("--emit-content", action="store_true",
                    help="Schrijf deck_content.md en stop (checkpoint om te "
                         "bewerken vóór het renderen)")
    ap.add_argument("--out", default=None,
                    help="Pad voor de .pptx (default: naast de gekozen JSON)")
    args = ap.parse_args()

    # Artefacts live in per-key subdirs (output/<KEY>/…); keep the flat legacy
    # location working too. Newest by mtime wins.
    matches = sorted(
        glob.glob(str(_OUT / "testauto_businesscase_*.json"))
        + glob.glob(str(_OUT / "**" / "testauto_businesscase_*.json")),
        key=lambda p: Path(p).stat().st_mtime)
    if not args.json and not matches:
        raise SystemExit(f"Geen analyse-JSON gevonden in {_OUT}/ — draai eerst "
                         f"testauto_businesscase.py, of geef --json op.")
    path = args.json or matches[-1]
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "value_stream" not in data:
        raise SystemExit(f"{path} bevat geen value_stream — draai eerst "
                         f"scripts/testauto_businesscase.py opnieuw.")

    # Artefacts land next to the JSON they belong to (per-key subdir).
    json_dir = Path(path).parent
    f = dc.facts(data)
    if args.emit_content:
        out = json_dir / "deck_content.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dc.to_md(dc.default_content(f), f), encoding="utf-8")
        print(f"✓ {out} — bewerk en render met --content {out}")
        return

    if args.content:
        content = dc.parse_md(Path(args.content).read_text(encoding="utf-8"))
        src = f"tekst: {Path(args.content).name}"
    else:
        content = dc.default_content(f)
        src = "tekst: afgeleid uit JSON"

    out_path = Path(args.out) if args.out else \
        json_dir / "testauto_businesscase_mgmt.pptx"
    n = build(data, content, f, out_path)
    print(f"✓ {out_path} — {n} slides "
          f"(data: {Path(path).name} · {src} · {f['story_key']}/run {f['run_id']})")


if __name__ == "__main__":
    main()
