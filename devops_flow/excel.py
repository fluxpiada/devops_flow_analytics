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
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


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
        fmt = ("yyyy-mm-dd hh:mm" if h in ("created", "started", "done")
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
                   window_start: date) -> Path:
    wb = Workbook()
    dash = wb.active
    dash.title = "Dashboard"

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
        dash[f"B{i}"].number_format = "yyyy-mm-dd" if isinstance(value, date) else "0.0"
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

    # P50/P85-lijnen voor de scatter: twee punten, van eerste tot laatste afronding.
    dash["G1"], dash["H1"], dash["I1"] = "x", "P50", "P85"
    dash["G2"], dash["G3"] = f"=MIN({done_rng})", f"=MAX({done_rng})"
    for r in (2, 3):
        dash[f"G{r}"].number_format = "yyyy-mm-dd"
        dash[f"H{r}"] = f"=$B${row_of['Cycle time P50 (werkdagen)']}"
        dash[f"I{r}"] = f"=$B${row_of['Cycle time P85 (werkdagen)']}"

    aging = sorted((r for r in items if r["age"] is not None),
                   key=lambda r: -r["age"])[:30]
    dash["K1"], dash["L1"], dash["M1"] = "lopend werk", "status", "leeftijd"
    for i, r in enumerate(aging, start=2):
        dash[f"K{i}"], dash[f"L{i}"], dash[f"M{i}"] = r["key"], r["status"], r["age"]

    # ── grafieken (rechts van de hulptabellen) ────────────────────────────
    scatter = ScatterChart()
    scatter.title, scatter.style = "Cycle time per afgerond item", 13
    scatter.x_axis.title, scatter.y_axis.title = "afgerond op", "werkdagen"
    scatter.x_axis.number_format = "yyyy-mm-dd"
    pts = Series(Reference(wb["Items"], min_col=col_idx(ic, "cycle_time"), min_row=1,
                           max_row=n + 1),
                 Reference(wb["Items"], min_col=col_idx(ic, "done"), min_row=2,
                           max_row=n + 1), title_from_data=True)
    pts.marker.symbol, pts.marker.size = "circle", 5
    pts.marker.graphicalProperties = GraphicalProperties(solidFill="4472C4")
    pts.graphicalProperties.line.noFill = True
    scatter.series.append(pts)
    for col in (8, 9):  # H = P50, I = P85
        line = Series(Reference(dash, min_col=col, min_row=1, max_row=3),
                      Reference(dash, min_col=7, min_row=2, max_row=3),
                      title_from_data=True)
        line.marker.symbol = "none"
        scatter.series.append(line)
    _place(dash, scatter, "O1")

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


def col_idx(cols: dict[str, str], name: str) -> int:
    return list(cols).index(name) + 1


def _place(ws, chart, anchor: str) -> None:
    chart.width, chart.height = 18, 7.5
    chart.x_axis.delete = chart.y_axis.delete = False  # openpyxl 3.1 verbergt ze anders
    ws.add_chart(chart, anchor)
