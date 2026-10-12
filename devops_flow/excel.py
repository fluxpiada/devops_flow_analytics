"""De tabellen naar CSV (voor wie zelf wil bouwen) en naar één dashboard-werkmap.

CSV's zijn geschreven voor een Nederlandstalige Excel: UTF-8 mét BOM (anders
worden accenten ANSI), `;` als scheidingsteken en een decimale komma. Datums ISO.

De werkmap laat Excel het presenteren: KPI's zijn formules over de tabellen, dus
wie een rij wegfiltert of een drempel aanpast ziet dat meteen doorwerken.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import (
    AreaChart,
    BarChart,
    LineChart,
    Reference,
    ScatterChart,
    Series,
)
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from .workdays import WORKDAY_H


def _csv_cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):
        return f"{v:g}".replace(".", ",")
    return str(v)


def write_csv(path: Path, header: list[str], rows: list[list]) -> Path:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(header)
        w.writerows([_csv_cell(v) for v in row] for row in rows)
    return path


def as_rows(dicts: list[dict]) -> tuple[list[str], list[list]]:
    header = list(dicts[0]) if dicts else []
    return header, [[d[h] for h in header] for d in dicts]


# ── werkmap ──────────────────────────────────────────────────────────────────


def _sheet(wb: Workbook, name: str, header: list[str], rows: list[list]):
    """Een datablad als Excel-tabel; retourneert {kolomnaam: kolomletter}."""
    ws = wb.create_sheet(name)
    ws.append(header)
    for row in rows:
        ws.append(row)
    cols = {h: get_column_letter(i + 1) for i, h in enumerate(header)}
    for h, col in cols.items():
        ws.column_dimensions[col].width = 60 if h == "summary" else 14
        fmt = ("yyyy-mm-dd hh:mm" if h in ("created", "started", "done", "left_at")
               else "yyyy-mm-dd" if h in ("date", "start", "end") else None)
        if fmt:
            for cell in ws[col][1:]:
                cell.number_format = fmt
    if rows:
        ref = f"A1:{get_column_letter(len(header))}{len(rows) + 1}"
        tab = Table(displayName=name, ref=ref)
        tab.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(tab)
    ws.freeze_panes = "A2"
    return ws, cols


def _rng(sheet: str, col: str, n: int) -> str:
    return f"{sheet}!${col}$2:${col}${n + 1}"


def write_workbook(path: Path, project: str, items: list[dict], tis: list[dict],
                   daily: tuple[list[str], list[list]], sprints: list[dict],
                   window_start: date, stream: tuple[list[dict], dict],
                   limits: dict[str, tuple]) -> Path:
    """`limits`: per maat (centrum, ondergrens, bovengrens) uit metrics.flag_items."""
    wb = Workbook()
    dash = wb.active
    dash.title = "Dashboard"
    _value_stream_sheet(wb, project, *stream)

    ih, ir = as_rows(items)
    _, ic = _sheet(wb, "Items", ih, ir)
    dh, dr = daily
    dws, dc = _sheet(wb, "Daily", dh, dr)
    sh, sr = as_rows(sprints)
    _, sc = _sheet(wb, "Sprints", sh, sr) if sprints else (None, {})
    _sheet(wb, "TimeInStatus", *as_rows(tis))
    n, nd, ns = len(ir), len(dr), len(sr)

    # ── KPI's: formules, zodat Excel de definitie toont ──────────────────
    done_ok = f"({_rng('Items', ic['backfilled'], n)}=FALSE)"

    def pct(col: str, k: float) -> str:
        # AGGREGATE(16, 6, …) = PERCENTILE.INC die fouten overslaat: delen door
        # een onwaar filter geeft #DEEL/0 en valt zo weg — geen matrixformule nodig.
        r = _rng("Items", ic[col], n)
        return f'=_xlfn.AGGREGATE(16,6,{r}/({done_ok}*({r}<>"")),{k})'

    kpis = [
        ("Project", project),
        ("Venster vanaf", window_start),
        ("Afgerond (excl. backfilled)",
         (f'=COUNTIFS({_rng("Items", ic["done"], n)},"<>",'
          f'{_rng("Items", ic["backfilled"], n)},FALSE)')),
        ("Cycle time P50 (werkdagen)", pct("cycle_time", 0.5)),
        ("Cycle time P85 (werkdagen)", pct("cycle_time", 0.85)),
        ("Cycle time P95 (werkdagen)", pct("cycle_time", 0.95)),
        ("Lead time P50 (werkdagen)", pct("lead_time", 0.5)),
        ("Lead time P85 (werkdagen)", pct("lead_time", 0.85)),
        # De XmR-limieten komen uit Python: een mediaan van moving ranges over een
        # gefilterde tabel is als Excel-formule broos.
        ("Cycle time bovengrens XmR (werkdagen)",
         round(limits["cycle_time"][2], 1)
         if limits.get("cycle_time", (None,) * 3)[2] is not None else None),
        ("Uitschieters cycle time (> bovengrens)",
         f'=COUNTIFS({_rng("Items", ic["ct_outlier"], n)},"hoog")'),
        ("Uitschieters lead time (> bovengrens)",
         f'=COUNTIFS({_rng("Items", ic["lt_outlier"], n)},"hoog")'),
        ("WIP nu", f"=Daily!{dc['wip']}{nd + 1}" if nd else 0),
        ("Doorvoer per week (gem.)", None),  # na de weektabel ingevuld
    ]
    # Een team dat niet in punten schat heeft geen velocity — liever weglaten dan 0 tonen.
    points = any(r["completed_points"] for r in sprints)
    if points:
        kpis.append(("Velocity (gem. punten)",
                     f"=AVERAGE({_rng('Sprints', sc['completed_points'], ns)})"))
    if sprints:
        kpis.append(("Say/do (afgerond van toegezegd)",
                     (f"=SUM({_rng('Sprints', sc['completed_committed'], ns)})"
                      f"/SUM({_rng('Sprints', sc['committed'], ns)})")))
    dash["A1"] = "Kerncijfers"
    for i, (label, value) in enumerate(kpis, start=2):
        dash[f"A{i}"], dash[f"B{i}"] = label, value
        dash[f"B{i}"].number_format = ("yyyy-mm-dd" if isinstance(value, date)
                                       else "0" if label.startswith("Uitschieters")
                                       else "0.0")
    if sprints:
        dash[f"B{len(kpis) + 1}"].number_format = "0%"
    dash.column_dimensions["A"].width = 34
    for col, width in (("B", 14), ("D", 12), ("G", 12), ("K", 12), ("L", 14)):
        dash.column_dimensions[col].width = width
    row_of = {label: i for i, (label, _) in enumerate(kpis, start=2)}

    # ── hulptabellen voor de grafieken (kolommen D…) ──────────────────────
    monday = window_start - timedelta(days=window_start.weekday())
    weeks = []
    while monday <= date.today():
        weeks.append(monday)
        monday += timedelta(days=7)
    dash["D1"], dash["E1"] = "week", "afgerond"
    done_rng = _rng("Items", ic["done"], n)
    for i, wk in enumerate(weeks, start=2):
        dash[f"D{i}"] = wk
        dash[f"D{i}"].number_format = "yyyy-mm-dd"
        dash[f"E{i}"] = f'=COUNTIFS({done_rng},">="&D{i},{done_rng},"<"&(D{i}+7))'
    dash[f"B{row_of['Doorvoer per week (gem.)']}"] = f"=AVERAGE(E2:E{len(weeks) + 1})"

    aging = sorted((r for r in items if r["age"] is not None),
                   key=lambda r: -r["age"])[:30]
    dash["K1"], dash["L1"], dash["M1"] = "lopend werk", "status", "leeftijd"
    for i, r in enumerate(aging, start=2):
        dash[f"K{i}"], dash[f"L{i}"], dash[f"M{i}"] = r["key"], r["status"], r["age"]

    # ── grafieken (rechts van de hulptabellen) ────────────────────────────
    # Bovenaan de procesgedragskaart (XmR) van de cycle time: punten op volgorde
    # van afronden, mediaan, bovengrens (UPL) en ondergrens (LPL), uitschieters
    # in rood, plus P85 als verwachting ("85% is binnen … klaar").
    # Geen lead-time-kaart: op MOD tellen ~170 items vanaf een migratiedatum
    # (jan 2026), dus die kaart toont vooral het opruimen van de backlog. De
    # lead-time-KPI's en de lt_-kolommen in Items blijven.
    xws = wb.create_sheet("XmR")
    p85 = ("P85", f"=Dashboard!$B${row_of['Cycle time P85 (werkdagen)']}")
    chart = _xmr_chart(xws, 1, items, "cycle_time", limits.get("cycle_time"),
                       "Cycle time per afgerond item (XmR)", p85)
    if chart:
        _place(dash, chart, "O1")

    thr = BarChart()
    thr.title, thr.y_axis.title = "Doorvoer per week", "items"
    thr.add_data(Reference(dash, min_col=5, min_row=1, max_row=len(weeks) + 1),
                 titles_from_data=True)
    thr.set_categories(Reference(dash, min_col=4, min_row=2, max_row=len(weeks) + 1))
    thr.legend = None
    _place(dash, thr, "O17")

    if nd:
        cfd = AreaChart()
        cfd.title, cfd.grouping, cfd.y_axis.title = "Cumulative flow", "stacked", "items"
        # Done onderop, To Do bovenop: de kolommen staan in flow-volgorde, dus omgekeerd.
        for col in range(len(dh) - 1, 1, -1):  # zonder date (1) en wip (laatste)
            cfd.add_data(Reference(dws, min_col=col, min_row=1, max_row=nd + 1),
                         titles_from_data=True)
        cfd.set_categories(Reference(dws, min_col=1, min_row=2, max_row=nd + 1))
        _place(dash, cfd, "O33")

    if aging:
        age = BarChart()
        age.type, age.title = "bar", "Leeftijd lopend werk (werkdagen)"
        age.add_data(Reference(dash, min_col=13, min_row=1, max_row=len(aging) + 1),
                     titles_from_data=True)
        age.set_categories(Reference(dash, min_col=11, min_row=2, max_row=len(aging) + 1))
        age.legend = None
        _place(dash, age, "AA1")

    if sprints:
        sws = wb["Sprints"]
        bars = BarChart()
        bars.title, bars.y_axis.title = "Sprints: toegezegd vs afgerond", "items"
        for name in ("committed", "completed_committed"):
            bars.add_data(Reference(sws, min_col=col_idx(sc, name), min_row=1,
                                    max_row=ns + 1), titles_from_data=True)
        bars.set_categories(Reference(sws, min_col=1, min_row=2, max_row=ns + 1))
        if points:
            vel = LineChart()
            vel.add_data(Reference(sws, min_col=col_idx(sc, "completed_points"), min_row=1,
                                   max_row=ns + 1), titles_from_data=True)
            vel.y_axis.axId, vel.y_axis.title, vel.y_axis.crosses = 200, "punten", "max"
            vel.y_axis.delete = False
            bars += vel
        _place(dash, bars, "AA17")

    wb.calculation.fullCalcOnLoad = True  # formules zonder cachewaarde: Excel rekent bij openen
    wb.save(path)
    return path


# ── waardestroom ─────────────────────────────────────────────────────────────

_BLUE, _NOTE, _ARROW = "4A72B8", "EDBB5F", "EDA93A"
_PER_ROW = 4  # blokken per rij, zoals een waardestroomkaart op een wand


def _num(v: float) -> str:
    """Eén decimaal onder de 10, anders heel — met decimale komma; "0", niet "0,0"."""
    text = f"{v:.1f}" if v < 10 else f"{v:.0f}"
    return text.removesuffix(".0").replace(".", ",")


def _dur(h: float | None, unit: str | None = None) -> str:
    """Werkuren leesbaar: tot en met 40 h in uren, daarboven in dagen van 8 h."""
    if h is None:
        return "—"
    unit = unit or ("h" if h <= 40 else "d")
    return f"{_num(h)} h" if unit == "h" else f"{_num(h / WORKDAY_H)} d"


def _line(step: dict, kind: str) -> str:
    """"0–24 d (med 5,9 d)" — één eenheid per regel, gekozen op de mediaan."""
    med = step[f"{kind}_median_h"]
    if med is None:
        return "—"
    unit = "h" if med <= 40 else "d"
    if step[f"{kind}_upper_h"] is None:  # geen spreiding: geen limieten
        return f"med {_dur(med, unit)}"
    lo, hi = (_dur(step[f"{kind}_{k}_h"], unit).split()[0] for k in ("lower", "upper"))
    return f"{lo}–{hi} {unit} (med {_dur(med, unit)})"


LEGEND = [
    ("Eenheid", ("1 d = 8 werkuur. Weekend en feestdagen tellen niet. Tot en met 40 h in "
                 "uren, daarboven in dagen (h ÷ 8).")),
    ("PT", ("Tijd in de stap, opgeteld over alle bezoeken. Per bezoek: korter dan 8 h → de "
            "echte duur; 8–24 h → 8 h (1 werkdag); langer → 8 h per werkdag. Nooit meer dan "
            "LT. Een proxy: géén gemeten inspanning.")),
    ("LT", ("Elke werkdag waarop het item in de stap stond telt helemaal mee (00:00–23:59 = "
            "8 h). LT ≥ PT; het verschil is de rest van de begin- en einddag, géén "
            "Lean-wachttijd.")),
    ("Bereik", ("Natuurlijke proceslimieten (Wheeler XmR): mediaan ± 3,145 × de mediaan van "
                "de moving ranges, met de items op volgorde van verlaten. Ondergrens "
                "minimaal 0; items die in één klik verschoven tellen als één punt.")),
    ("Uitschieters", ("Aantal items met LT boven de bovengrens: een speciale oorzaak, "
                      "uitzoeken. Binnen de grenzen is het systeem zelf; niet per item "
                      "najagen.")),
    ("Doorgeklikt", ("Items met PT onder 1 werkuur in de stap: overgeslagen of "
                     "administratief doorgezet. Een vaste regel, geen statistiek.")),
    ("%C&A", ("Deel van de items dat de stap verliet en er nooit vanuit een latere stap "
              "naar werd teruggestuurd. Gerold = het product over alle stappen.")),
    ("n", ("Items die de stap verlieten. Backfilled items (alle overgangen binnen een uur) "
           "tellen niet mee.")),
]


def _box(ws, top: int, left: int, height: int, width: int, text: str,
         fill: str, font: Font) -> None:
    """Een samengevoegd vlak met gecentreerde, omlopende tekst."""
    ws.merge_cells(start_row=top, start_column=left,
                   end_row=top + height - 1, end_column=left + width - 1)
    cell = ws.cell(top, left, text)
    cell.font, cell.alignment = font, Alignment(horizontal="center", vertical="center",
                                                wrap_text=True)
    for r in range(top, top + height):
        for c in range(left, left + width):
            ws.cell(r, c).fill = PatternFill("solid", fgColor=fill)


def _value_stream_sheet(wb: Workbook, project: str, steps: list[dict],
                        totals: dict) -> None:
    """Waardestroomkaart van cellen: per stap een blauw blok met een geel
    briefje (PT, LT: bereik en mediaan; uitschieters, %C&A), pijlen ertussen,
    en een legenda met de berekening van elk getal."""
    ws = wb.create_sheet("Waardestroom", 1)
    ws.sheet_view.showGridLines = False
    ws["B1"] = f"Waardestroom — {project}"
    ws["B1"].font = Font(bold=True, size=16)
    rolled = totals["rolled_ca_pct"]
    ws["B2"] = (f"Totaal (som van de medianen): PT {_dur(totals['pt_h'])} · "
                f"LT {_dur(totals['lt_h'])} · gerolde %C&A "
                f"{'—' if rolled is None else f'{rolled}%'}")
    ws["B2"].font = Font(bold=True)

    ws.column_dimensions["A"].width = 5  # pijl aan het begin van een vervolgrij
    for k in range(_PER_ROW):
        for i in range(3):
            ws.column_dimensions[get_column_letter(2 + 4 * k + i)].width = 11
        ws.column_dimensions[get_column_letter(5 + 4 * k)].width = 5

    arrow = Font(size=22, bold=True, color=_ARROW)
    band = 12  # rijen per rij blokken: blok 4 + briefje 6 + lucht
    for i, st in enumerate(steps):
        row, k = divmod(i, _PER_ROW)
        top, left = 4 + row * band, 2 + 4 * k
        _box(ws, top, left, 4, 3, st["step"].upper(), _BLUE,
             Font(bold=True, size=13, color="FFFFFF"))
        _box(ws, top + 4, left + 1, 6, 3,
             f"PT: {_line(st, 'pt')}\nLT: {_line(st, 'lt')}\n"
             f"uitschieters: {st['lt_outliers']} hoog\ndoorgeklikt: {st['doorgeklikt']}\n"
             f"%C&A: {st['ca_pct']}%  ·  n = {st['items']}",
             _NOTE, Font(bold=True, size=10, color="404040"))
        for r in range(top + 4, top + 10):
            ws.row_dimensions[r].height = 16
        if i + 1 < len(steps):  # pijl naar de volgende stap: rechts, of aan het begin van de volgende rij
            r, c = (top + 1, left + 3) if k + 1 < _PER_ROW else (top + band + 1, 1)
            ws.cell(r, c, "➜").font = arrow

    first = 4 + (-(-len(steps) // _PER_ROW)) * band + 1
    ws.cell(first, 2, "Legenda").font = Font(bold=True)
    small = Font(italic=True, size=9, color="595959")
    for j, (term, text) in enumerate(LEGEND, start=first + 1):
        head = ws.cell(j, 2, term)
        head.font = Font(bold=True, size=9, color="595959")
        head.alignment = Alignment(vertical="top")
        ws.merge_cells(start_row=j, start_column=3, end_row=j, end_column=17)
        cell = ws.cell(j, 3, text)
        cell.font, cell.alignment = small, Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[j].height = 26


def col_idx(cols: dict[str, str], name: str) -> int:
    return list(cols).index(name) + 1


def _xmr_chart(ws, col: int, items: list[dict], field: str, lim: tuple | None,
               title: str, extra: tuple[str, str] | None = None) -> ScatterChart | None:
    """Schrijft de reeks naar `ws` vanaf kolom `col` en geeft de XmR-kaart terug.

    Kolommen: afgerond, waarde, binnen de limieten, uitschieter (hoog/laag);
    daaronder de lijnen centrum / UPL / LPL als twee punten (eerste → laatste),
    plus eventueel `extra` = (kop, formule), bv. de P85 uit het dashboard.
    Alleen items die flag_items meetelde (afgerond, niet backfilled).
    """
    prefix = "ct" if field == "cycle_time" else "lt"
    rows = sorted((r for r in items if r[f"{prefix}_outlier"] is not None),
                  key=lambda r: r["done"])
    if not rows or lim is None:
        return None
    c = [get_column_letter(col + i) for i in range(4)]
    for k, head in enumerate(("afgerond", field, "binnen", "uitschieter")):
        ws[f"{c[k]}1"] = head
    for i, r in enumerate(rows, start=2):
        ws[f"{c[0]}{i}"], ws[f"{c[1]}{i}"] = r["done"], r[field]
        ws[f"{c[0]}{i}"].number_format = "yyyy-mm-dd"
        ws[f"{c[3 if r[f'{prefix}_outlier'] else 2]}{i}"] = r[field]
    n = len(rows)
    centre, lower, upper = lim
    # Lijnen onder de reeks: x, mediaan, UPL, LPL.
    top = n + 4
    ws[f"{c[0]}{top}"], ws[f"{c[1]}{top}"] = "x", "mediaan"
    ws[f"{c[2]}{top}"], ws[f"{c[3]}{top}"] = "UPL", "LPL"
    for j, x in ((1, rows[0]["done"]), (2, rows[-1]["done"])):
        ws[f"{c[0]}{top + j}"] = x
        ws[f"{c[0]}{top + j}"].number_format = "yyyy-mm-dd"
        ws[f"{c[1]}{top + j}"] = round(centre, 1)
        if upper is not None:
            ws[f"{c[2]}{top + j}"], ws[f"{c[3]}{top + j}"] = round(upper, 1), round(lower, 1)
    if extra:
        c.append(get_column_letter(col + 4))
        ws[f"{c[4]}{top}"] = extra[0]
        for j in (1, 2):
            ws[f"{c[4]}{top + j}"] = extra[1]
    for letter in c:
        ws.column_dimensions[letter].width = 14

    chart = ScatterChart()
    chart.title, chart.style = title, 13
    chart.x_axis.title, chart.y_axis.title = "afgerond op", "werkdagen"
    chart.x_axis.number_format = "yyyy-mm-dd"
    x = Reference(ws, min_col=col, min_row=2, max_row=n + 1)
    for k, color in ((2, "4472C4"), (3, "C00000")):  # binnen, uitschieters
        pts = Series(Reference(ws, min_col=col + k, min_row=1, max_row=n + 1), x,
                     title_from_data=True)
        pts.marker.symbol, pts.marker.size = "circle", 5 if k == 2 else 7
        pts.marker.graphicalProperties = GraphicalProperties(solidFill=color)
        pts.graphicalProperties.line.noFill = True
        chart.series.append(pts)
    lx = Reference(ws, min_col=col, min_row=top + 1, max_row=top + 2)
    for k, color, dash_style in ((1, "404040", None), (2, "C00000", "dash"),
                                 (3, "C00000", "dash")):
        if k > 1 and upper is None:
            break  # geen spreiding: alleen het centrum
        line = Series(Reference(ws, min_col=col + k, min_row=top, max_row=top + 2), lx,
                      title_from_data=True)
        line.marker.symbol = "none"
        line.graphicalProperties.line.solidFill = color
        line.graphicalProperties.line.width = 19050  # 1,5 pt
        if dash_style:
            line.graphicalProperties.line.dashStyle = dash_style
        chart.series.append(line)
    if extra:
        line = Series(Reference(ws, min_col=col + 4, min_row=top, max_row=top + 2), lx,
                      title_from_data=True)
        line.marker.symbol = "none"
        line.graphicalProperties.line.solidFill = "A5A5A5"
        line.graphicalProperties.line.dashStyle = "sysDot"
        chart.series.append(line)
    return chart


def _place(ws, chart, anchor: str) -> None:
    chart.width, chart.height = 18, 7.5
    chart.x_axis.delete = chart.y_axis.delete = False  # openpyxl 3.1 verbergt ze anders
    ws.add_chart(chart, anchor)
