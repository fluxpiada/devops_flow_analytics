#!/usr/bin/env python3
"""Zelftest voor de flow-analyse — draait offline, zonder Jira.

Dekt het rekenwerk waar een fout stilletjes doorwerkt in het rapport:
feestdagen en werkdagenduur, de percentiel- en verdelingsfuncties, het parsen
van greenhopper-sprintstrings, de bulk-aanmaakdetectie, en een end-to-end
`build_flow` + `render_flow_md` op een handgemaakte changelog.

Alles is synthetisch: geen netwerk, geen creds, geen cache. Bedoeld om ná een
wijziging in `jira_core.py` of `jira_flow_analysis.py` te draaien.

Gebruik:
    uv run python scripts/selftest_flow.py        # stil bij succes
    uv run python scripts/selftest_flow.py -v     # toont elke check

Exitcode 0 = alles goed, 1 = er faalde iets.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import jira_flow_analysis as fa  # noqa: E402 — naast dit script
from jira_core import (  # noqa: E402
    _count_workdays,
    _easter,
    _is_workday,
    _status_transitions,
    _time_in_status,
    _time_in_status_workdays,
    _workdays_elapsed,
    dutch_holidays,
)

_VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv
_RESULTS: list[tuple[str, bool]] = []


def check(label: str, got, want) -> None:
    ok = got == want
    _RESULTS.append((label, ok))
    if not ok:
        print(f"  ✗ {label}\n      kreeg    {got!r}\n      verwacht {want!r}")
    elif _VERBOSE:
        print(f"  ✓ {label}")


def _holiday(year: int, name: str) -> date:
    return next(d for d, n in dutch_holidays(year).items() if n == name)


# ── feestdagen en werkdagen ──────────────────────────────────────────────────


def test_holidays() -> None:
    for year, easter in ((2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)),
                         (2026, date(2026, 4, 5)), (2027, date(2027, 3, 28))):
        check(f"Eerste Paasdag {year}", _easter(year), easter)
    check("Tweede Paasdag 2026", _holiday(2026, "Tweede Paasdag"), date(2026, 4, 6))
    check("Hemelvaart 2026", _holiday(2026, "Hemelvaartsdag"), date(2026, 5, 14))
    check("Tweede Pinksterdag 2026", _holiday(2026, "Tweede Pinksterdag"),
          date(2026, 5, 25))
    # 27 april 2025 valt op zondag; Koningsdag schuift dan naar 26 april.
    check("Koningsdag 2025 schuift naar za", _holiday(2025, "Koningsdag"),
          date(2025, 4, 26))
    check("Koningsdag 2026 blijft 27 apr", _holiday(2026, "Koningsdag"),
          date(2026, 4, 27))
    check("Bevrijdingsdag in lustrumjaar",
          any(n == "Bevrijdingsdag" for n in dutch_holidays(2025).values()), True)
    check("Bevrijdingsdag niet in ander jaar",
          any(n == "Bevrijdingsdag" for n in dutch_holidays(2026).values()), False)
    check("Goede Vrijdag telt als werkdag", _is_workday(date(2026, 4, 3)), True)
    check("Hemelvaart is geen werkdag", _is_workday(date(2026, 5, 14)), False)
    check("zaterdag is geen werkdag", _is_workday(date(2026, 5, 16)), False)


def test_workdays_elapsed() -> None:
    # wo 09:00 -> vr 09:00 met Hemelvaart (do) ertussen = 1 werkdag i.p.v. 2.
    check("wo→vr over Hemelvaart",
          round(_workdays_elapsed(datetime(2026, 5, 13, 9),
                                  datetime(2026, 5, 15, 9)), 2), 1.0)
    check("wo→vr in een gewone week",
          round(_workdays_elapsed(datetime(2026, 5, 20, 9),
                                  datetime(2026, 5, 22, 9)), 2), 2.0)
    check("vr→ma (weekend eruit)",
          round(_workdays_elapsed(datetime(2026, 1, 2, 9),
                                  datetime(2026, 1, 5, 9)), 2), 1.0)
    # De kern van het verschil met _workdays(): dit is een duur, geen faselengte.
    check("tien minuten is geen dag",
          round(_workdays_elapsed(datetime(2026, 1, 5, 9),
                                  datetime(2026, 1, 5, 9, 10)), 2), 0.01)
    check("een dag op de feestdag zelf",
          _workdays_elapsed(datetime(2026, 5, 14, 9), datetime(2026, 5, 14, 17)), 0.0)
    check("een dag in het weekend",
          _workdays_elapsed(datetime(2026, 1, 3, 9), datetime(2026, 1, 4, 9)), 0.0)
    check("eind vóór start", _workdays_elapsed(datetime(2026, 1, 5, 9),
                                               datetime(2026, 1, 5, 9)), 0.0)
    # 21 t/m 27 dec 2026: ma-vr = 5, minus Eerste (vr 25) en Tweede Kerstdag (za).
    check("_count_workdays kerstweek 2026",
          _count_workdays(date(2026, 12, 21), date(2026, 12, 28)), 4)


def test_time_in_status() -> None:
    issue = {
        "key": "T-1",
        "fields": {"created": "2026-01-02T09:00:00.000",
                   "resolutiondate": "2026-01-05T09:00:00.000",
                   "updated": "2026-01-05T09:00:00.000",
                   "status": {"name": "Closed"}},
        "changelog": {"histories": [
            {"created": "2026-01-05T09:00:00.000", "author": {"displayName": "x"},
             "items": [{"field": "status", "fromString": "To Do",
                        "toString": "Closed"}]}]},
    }
    tr = _status_transitions(issue)
    check("kalenderdagen tellen het weekend mee",
          _time_in_status(issue, tr), {"To Do": 3.0})
    check("werkdagen laten het weekend weg",
          _time_in_status_workdays(issue, tr), {"To Do": 1.0})


# ── statistiek ───────────────────────────────────────────────────────────────


def test_statistics() -> None:
    check("p85 van 1..10", fa._p85([float(i) for i in range(1, 11)]), 8.6)
    check("p85 van een lege reeks", fa._p85([]), None)
    check("p85 van één waarde", fa._p85([4.0]), 4.0)
    check("sparkline met gat", fa._sparkline([1.0, 2.0, None, 3.0]), "▁▄·█")
    check("sparkline vlak", fa._sparkline([2.0, 2.0, 2.0]), "▅▅▅")
    check("trend stijgend", fa._trend([1.0, 2.0, 3.0, 4.0])["direction"], "stijgend")
    check("trend dalend", fa._trend([4.0, 3.0, 2.0, 1.0])["direction"], "dalend")
    check("trend bij te weinig punten", fa._trend([1.0, 2.0]), None)


def test_histogram() -> None:
    h = fa._histogram([1.0, 2.0, 3.0, 50.0])
    check("histogram telt alles mee", sum(b[2] for b in h), 4)
    check("histogram sluit aaneen",
          all(abs(h[i][1] - h[i + 1][0]) < 1e-9 for i in range(len(h) - 1)), True)
    check("histogram van een lege reeks", fa._histogram([]), [])
    check("histogram bij één waarde", sum(b[2] for b in fa._histogram([5.0])), 1)


# ── parsers ──────────────────────────────────────────────────────────────────


def test_project_key() -> None:
    for arg, want in (
            ("https://jira.vitens.lan/jira/browse/MOD", "MOD"),
            ("https://jira.vitens.lan/jira/browse/MOD-123", "MOD"),
            ("https://jira.vitens.lan/jira/browse/S34-2907", "S34"),
            ("MOD", "MOD"), ("mod", "MOD")):
        check(f"projectsleutel uit {arg}", fa._project_key(arg), want)


def test_months_ago() -> None:
    check("6 maanden terug", fa._months_ago(datetime(2026, 3, 31), 6),
          datetime(2025, 9, 30))
    check("12 maanden terug", fa._months_ago(datetime(2026, 1, 15), 12),
          datetime(2025, 1, 15))
    check("klemt op maandlengte", fa._months_ago(datetime(2026, 3, 31), 1),
          datetime(2026, 2, 28))
    check("klemt in een schrikkeljaar", fa._months_ago(datetime(2024, 3, 31), 1),
          datetime(2024, 2, 29))


_GH_CLOSED = ("com.atlassian.greenhopper.service.sprint.Sprint@1f39bc[id=123,"
              "rapidViewId=45,state=CLOSED,name=Sprint 12, incasso,"
              "startDate=2026-01-05T09:00:00.000+01:00,"
              "endDate=2026-01-19T09:00:00.000+01:00,"
              "completeDate=2026-01-19T14:30:00.000+01:00,sequence=123,goal=]")


def test_sprint_parsing() -> None:
    s = fa._parse_sprint_value(_GH_CLOSED)
    check("sprint-id", s["id"], "123")
    check("sprintnaam met komma erin", s["name"], "Sprint 12, incasso")
    check("gesloten sprint", s["closed"], True)
    check("eind = completeDate", s["end"], datetime(2026, 1, 19, 14, 30))
    check("planned_end = endDate", s["planned_end"], datetime(2026, 1, 19, 9, 0))

    open_sprint = fa._parse_sprint_value(
        "S@abc[id=124,state=ACTIVE,name=Sprint 13,"
        "startDate=2026-01-19T09:00:00.000+01:00,"
        "endDate=2026-02-02T09:00:00.000+01:00,completeDate=<null>]")
    check("open sprint niet gesloten", open_sprint["closed"], False)
    check("open sprint eindigt op endDate", open_sprint["end"],
          datetime(2026, 2, 2, 9, 0))

    as_dict = fa._parse_sprint_value(
        {"id": 200, "state": "closed", "name": "Sprint X",
         "startDate": "2026-01-05T09:00:00.000Z",
         "endDate": "2026-01-19T09:00:00.000Z",
         "completeDate": "2026-01-19T09:00:00.000Z"})
    check("JSON-vorm wordt ook geparsed", (as_dict["id"], as_dict["closed"]),
          ("200", True))
    check("sprint zonder datums valt af",
          fa._parse_sprint_value("S@x[id=9,name=n]"), None)


def test_snap_window() -> None:
    sprints = [fa._parse_sprint_value(_GH_CLOSED),
               fa._parse_sprint_value(
                   "S@x[id=124,state=CLOSED,name=Sprint 13,"
                   "startDate=2026-01-19T09:00:00.000+01:00,"
                   "endDate=2026-02-02T09:00:00.000+01:00,"
                   "completeDate=2026-02-02T10:00:00.000+01:00]"),
               fa._parse_sprint_value(
                   "S@y[id=125,state=ACTIVE,name=Sprint 14,"
                   "startDate=2026-02-02T09:00:00.000+01:00,"
                   "endDate=2026-02-16T09:00:00.000+01:00,completeDate=<null>]")]
    kept, start, end = fa.snap_window(sprints, datetime(2026, 1, 1),
                                      datetime(2026, 2, 10))
    check("open sprint valt buiten het venster", [k["id"] for k in kept],
          ["123", "124"])
    check("venster begint op de eerste sprintstart", start, sprints[0]["start"])
    check("venster eindigt op het laatste sprinteind", end, sprints[1]["end"])
    kept2, _, _ = fa.snap_window(sprints, datetime(2026, 1, 10),
                                 datetime(2026, 2, 10))
    check("deelsprint aan de rand valt af", [k["id"] for k in kept2], ["124"])
    check("geen passende sprints ⇒ ruw venster",
          fa.snap_window([], datetime(2026, 1, 1), datetime(2026, 2, 1))[0], [])


def test_bulk_detection() -> None:
    records = ([{"created": "2026-01-22T11:30:00.000"} for _ in range(7)]
               + [{"created": f"2026-02-0{i}T09:1{i}:00.000"} for i in range(1, 4)])
    bulk = fa.detect_bulk_creation(records)
    check("bulk-issues geteld", bulk["n_bulk_created"], 7)
    check("importmoment gevonden",
          bulk["moments"][0]["timestamp"] if bulk["moments"] else None,
          "2026-01-22T11:30")
    check("percentage bulk", bulk["pct"], 70.0)
    check("los issue niet gemarkeerd", records[-1]["bulk_created"], False)
    check("onder de drempel is het geen import",
          fa.detect_bulk_creation([{"created": "2026-01-22T11:30:00.000"}
                                   for _ in range(fa.BULK_CREATE_MIN - 1)]
                                  )["moments"], [])


# ── end-to-end ───────────────────────────────────────────────────────────────

_STATUS_MAP = {"To Do": "To Do", "In Progress": "In Progress",
               "Test": "In Progress", "In Review": "In Progress", "Done": "Done"}


def _issue(key, created, steps, resolved, status):
    """steps = [(tijdstip, van-status, naar-status)]"""
    return {"key": key,
            "fields": {"summary": key, "issuetype": {"name": "Story"},
                       "status": {"name": status}, "created": created,
                       "resolutiondate": resolved, "updated": resolved or created},
            "changelog": {"histories": [
                {"created": ts, "author": {"displayName": "t"},
                 "items": [{"field": "status", "fromString": a, "toString": b}]}
                for ts, a, b in steps]}}


def _fixture():
    sp1 = fa._parse_sprint_value(
        "S@a[id=1,state=CLOSED,name=Sprint 1,"
        "startDate=2026-01-05T09:00:00.000+01:00,"
        "endDate=2026-01-19T09:00:00.000+01:00,"
        "completeDate=2026-01-19T09:00:00.000+01:00]")
    sp2 = fa._parse_sprint_value(
        "S@b[id=2,state=CLOSED,name=Sprint 2,"
        "startDate=2026-01-19T09:00:00.000+01:00,"
        "endDate=2026-02-02T09:00:00.000+01:00,"
        "completeDate=2026-02-02T09:00:00.000+01:00]")
    periods = fa.sprint_periods([sp1, sp2], datetime(2026, 2, 2, 9))

    # Zes issues op één moment aangemaakt = een import; één los aangemaakt.
    issues = [_issue(f"P-{i}", "2026-01-05T09:00:00.000",
                     [("2026-01-07T09:00:00.000", "To Do", "In Progress"),
                      ("2026-01-09T09:00:00.000", "In Progress", "Done")],
                     "2026-01-09T09:00:00.000", "Done") for i in range(6)]
    issues.append(_issue("P-99", "2026-01-20T09:00:00.000",
                         [("2026-01-22T09:00:00.000", "To Do", "In Progress"),
                          ("2026-01-26T09:00:00.000", "In Progress", "Done")],
                         "2026-01-26T09:00:00.000", "Done"))
    # Alle overgangen binnen een uur = achteraf geadministreerd.
    issues.append(_issue("P-BF", "2026-01-06T09:00:00.000",
                         [("2026-01-20T09:00:00.000", "To Do", "In Progress"),
                          ("2026-01-20T09:20:00.000", "In Progress", "Done")],
                         "2026-01-20T09:20:00.000", "Done"))
    issues.append(_issue("P-WIP", "2026-01-20T09:00:00.000",
                         [("2026-01-21T09:00:00.000", "To Do", "In Progress")],
                         None, "In Progress"))
    window = {"months": 6, "raw_start": "2025-08-05T00:00:00",
              "raw_end": "2026-02-02T09:00:00",
              "start": sp1["start"].isoformat(), "end": sp2["end"].isoformat(),
              "snapped": True, "snap_note": "", "sprints_kept": 2,
              "sprints_dropped": 0}
    return fa.build_flow(issues, _STATUS_MAP, periods, window,
                         datetime(2026, 2, 3, 9))


def test_build_flow(report) -> None:
    c = report["counts"]
    check("geanalyseerde issues", c["analysed"], 7)
    check("backfill uitgesloten", c["excluded_backfilled"], 1)
    check("onderhanden werk apart", c["in_flight_wip"], 1)
    check("niets buiten de sprintperioden", c["resolved_outside_sprints"], 0)
    check("doorvoer totaal", report["throughput"]["total"], 7)
    check("doorvoer mediaan per sprint", report["throughput"]["median"], 3.5)
    check("Done blijft in de JSON staan", "Done" in report["categories"], True)
    check("bulk-cohort", report["lead_time_by_cohort"]["bulk_created"]["n"], 6)
    check("los-cohort", report["lead_time_by_cohort"]["individually_created"]["n"], 1)
    check("histogram gevuld", len(report["lead_time_histogram"]) > 0, True)
    check("actief aandeel berekend",
          report["active_share_pct"]["median"] is not None, True)
    check("doorvoertrend aanwezig", "throughput" in report["trends"], True)
    check("geen onbekende statussen", report["unknown_statuses"], [])
    check("WIP per categorie", report["in_flight_by_category"], {"In Progress": 1})
    # De invariant die elke rekenfout in de categorie-optelling vangt.
    for r in report["_records"]:
        if not r["in_flight"]:
            total = round(sum(r["per_category"].values()), 1)
            check(f"{r['key']}: som categorieën ≈ doorlooptijd",
                  abs(total - r["lead_time_days"]) <= 0.2, True)


def test_render(report) -> None:
    md = fa.render_flow_md(report, "P")
    for needle in ("## 0. De kern", "## 1. Verantwoording",
                   "## 2. Doorlooptijd en categorieën",
                   "### Doorlooptijd per cohort",
                   "### Verdeling van de doorlooptijd", "## 3. Drill-down",
                   "## 4. Per sprint", "## 5. Beperkingen",
                   "Bulk aangemaakte issues", "doorvoer", "feestdagen",
                   "← mediaan"):
        check(f"rapport bevat {needle!r}", needle in md, True)
    section2 = md.split("## 2. ")[1].split("## 3. ")[0]
    check("Done staat niet als verblijfsduur in §2",
          "| Done |" not in section2, True)
    check("Done staat wel als eindstatus in §3",
          "| Done |" in md.split("## 3. ")[1], True)
    check("doorlooptijdregel zonder gemiddelde",
          "| Doorlooptijd totaal | n | mediaan | p85 |" in md, True)


def _run(name: str, fn, *args) -> None:
    """Draai één sectie en rapporteer het resultaat.

    Een sectie die crasht mag de rest niet meenemen: juist als er iets stuk is
    wil je de overige checks nog zien, niet één traceback.
    """
    before = len(_RESULTS)
    try:
        fn(*args)
    except Exception as exc:  # noqa: BLE001 — een kapotte sectie is óók een fail
        _RESULTS.append((f"{name}: onverwachte fout", False))
        print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
        return
    failed = sum(1 for _, ok in _RESULTS[before:] if not ok)
    print(f"  {'✗' if failed else '✓'} {name} ({len(_RESULTS) - before} checks)")


def main() -> int:
    print("Zelftest flow-analyse (offline)\n")
    sections = (
        ("feestdagen", test_holidays),
        ("werkdagenduur", test_workdays_elapsed),
        ("tijd per status", test_time_in_status),
        ("statistiek", test_statistics),
        ("histogram", test_histogram),
        ("projectsleutel", test_project_key),
        ("vensterberekening", test_months_ago),
        ("sprint parsen", test_sprint_parsing),
        ("venstersnapping", test_snap_window),
        ("bulk-detectie", test_bulk_detection),
    )
    for name, fn in sections:
        _run(name, fn)

    try:
        report = _fixture()
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ fixture: {type(exc).__name__}: {exc}")
        _RESULTS.append(("fixture: onverwachte fout", False))
    else:
        _run("build_flow", test_build_flow, report)
        _run("rapport", test_render, report)

    bad = [label for label, ok in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)} ok, {len(bad)} fail")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
