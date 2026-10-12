from datetime import date, datetime

import pytest

from devops_flow import metrics, stats
from devops_flow.cli import months_ago, project_key
from devops_flow.excel import _csv_cell

# Status-id → (naam van nu, categorie). De changelog hieronder gebruikt soms een
# oude naam ("Done") — het id beslist, niet de naam.
WF = {"1": ("Te doen", "To Do"), "3": ("In uitvoering", "In Progress"),
      "4": ("Review", "In Progress"), "5": ("Gedaan", "Done"), "6": ("Gesloten", "Done")}
ID = {"To Do": "1", "In Progress": "3", "Review": "4", "Done": "5", "Closed": "6"}
NOW = datetime(2026, 1, 16, 12)


def issue(key, created, steps, status, resolved=None):
    """steps = [(moment, van, naar), …]"""
    return {"key": key,
            "fields": {"created": created, "resolutiondate": resolved,
                       "status": {"id": ID[status], "name": status},
                       "issuetype": {"name": "Story"},
                       "summary": key, "story_points": 3},
            "changelog": {"histories": [
                {"created": ts, "items": [{"field": "status", "from": ID[a], "fromString": a,
                                           "to": ID[b], "toString": b}]}
                for ts, a, b in steps]}}


DONE = issue("T-1", "2026-01-02T09:00:00.000+0100", [
    ("2026-01-05T09:00:00.000+0100", "To Do", "In Progress"),
    ("2026-01-07T09:00:00.000+0100", "In Progress", "Review"),
    ("2026-01-08T09:00:00.000+0100", "Review", "Done"),
    ("2026-01-09T09:00:00.000+0100", "Done", "Closed"),          # Done → Done telt niet
], "Closed", "2026-01-09T09:00:00.000+0100")
OPEN = issue("T-2", "2026-01-05T09:00:00.000+0100", [
    ("2026-01-12T09:00:00.000+0100", "To Do", "In Progress")], "In Progress")
SKIPPED = issue("T-3", "2026-01-05T09:00:00.000+0100", [
    ("2026-01-06T09:00:00.000+0100", "To Do", "Done")], "Done", "2026-01-06T09:00:00.000+0100")

# Rework: Review stuurt terug naar In Progress, daarna opnieuw Review.
REWORK = issue("T-4", "2026-01-05T09:00:00.000+0100", [
    ("2026-01-05T13:00:00.000+0100", "To Do", "In Progress"),
    ("2026-01-06T13:00:00.000+0100", "In Progress", "Review"),
    ("2026-01-07T09:00:00.000+0100", "Review", "In Progress"),
    ("2026-01-07T13:00:00.000+0100", "In Progress", "Review"),
    ("2026-01-08T09:00:00.000+0100", "Review", "Done"),
], "Done", "2026-01-08T09:00:00.000+0100")


def rows():
    wf = metrics.Workflow(WF)
    items, tis = metrics.items_table([DONE, OPEN, SKIPPED], wf, NOW)
    return wf, {r["key"]: r for r in items}, tis


def test_cycle_and_lead_time():
    _, items, _ = rows()
    done = items["T-1"]
    assert done["started"] == datetime(2026, 1, 5, 9)
    assert done["done"] == datetime(2026, 1, 8, 9)   # eerste stap naar Done
    assert done["cycle_time"] == 3.0                 # ma 09:00 → do 09:00
    assert done["lead_time"] == 4.0                  # vr → do, zonder weekend
    assert done["age"] is None


def test_open_and_skipped_work():
    _, items, _ = rows()
    assert items["T-2"]["age"] == 4.1 and items["T-2"]["cycle_time"] is None
    assert items["T-3"]["started"] is None and items["T-3"]["cycle_time"] is None
    assert items["T-3"]["lead_time"] == 1.0


def test_time_in_status_uses_current_names_and_stops_at_done():
    _, _, tis = rows()
    t1 = {r["status"]: r["workdays"] for r in tis if r["key"] == "T-1"}
    assert t1 == {"Te doen": 1.0, "In uitvoering": 2.0, "Review": 1.0}


def test_daily_cfd():
    wf = metrics.Workflow(WF)
    header, table = metrics.daily_table([DONE, OPEN, SKIPPED], wf, date(2026, 1, 5), NOW)
    assert header == ["date", "Te doen", "In uitvoering", "Review", "Gedaan", "Gesloten", "wip"]
    by_day = {r[0]: dict(zip(header, r)) for r in table}
    assert date(2026, 1, 10) not in by_day                  # zaterdag
    assert by_day[date(2026, 1, 5)]["In uitvoering"] == 1   # T-1
    assert by_day[date(2026, 1, 5)]["Te doen"] == 2         # T-2, T-3
    assert by_day[date(2026, 1, 9)]["Gesloten"] == 1
    assert by_day[date(2026, 1, 16)]["wip"] == 1            # T-2


def test_sprint_report():
    def i(key, initial, current):
        return {"key": key, "estimateStatistic": {"statFieldValue": {"value": initial}},
                "currentEstimateStatistic": {"statFieldValue": {"value": current}}}
    report = {"completedIssues": [i("T-1", 3, 5), i("T-9", 2, 2)],
              "issuesNotCompletedInCurrentSprint": [i("T-2", 8, 8)],
              "puntedIssues": [i("T-4", 1, 1)],
              "issueKeysAddedDuringSprint": {"T-9": True}}
    sprint = {"name": "S1", "startDate": "2026-01-05T09:00:00.000+01:00",
              "completeDate": "2026-01-16T16:00:00.000+01:00"}
    _, items, _ = rows()
    [row] = metrics.sprint_table([sprint], [report], list(items.values()))
    assert row == {"sprint": "S1", "start": date(2026, 1, 5), "end": date(2026, 1, 16),
                   "committed": 3, "added": 1, "removed": 1, "completed": 2,
                   "completed_committed": 1, "not_completed": 1,
                   "committed_points": 12, "completed_points": 7}
    assert items["T-1"]["sprint"] == "S1"


def test_csv_cells_for_dutch_excel():
    assert _csv_cell(2.5) == "2,5"
    assert _csv_cell(True) == "1"
    assert _csv_cell(None) == ""
    assert _csv_cell(datetime(2026, 1, 5, 9, 30)) == "2026-01-05 09:30"


def test_project_key():
    for arg, want in (("https://jira.vitens.lan/jira/browse/MOD", "MOD"),
                      ("https://jira.vitens.lan/jira/browse/S34-2907", "S34"),
                      ("mod", "MOD")):
        assert project_key(arg) == want


def test_months_ago_clamps():
    assert months_ago(datetime(2026, 3, 31), 6) == datetime(2025, 9, 30)
    assert months_ago(datetime(2024, 3, 31), 1) == datetime(2024, 2, 29)
    assert months_ago(datetime(2026, 1, 15), 12) == datetime(2025, 1, 15)


def test_time_in_status_hours_and_visits():
    wf = metrics.Workflow(WF)
    _, tis = metrics.items_table([REWORK], wf, NOW)
    t4 = {r["status"]: (r["visits"], r["pt_hours"], r["lt_hours"], r["sent_back"])
          for r in tis}
    # Te doen ma 09–13: 4 h echt; LT = 1 aangeraakte werkdag = 8 h.
    # In uitvoering ma 13 → di 13 (24 h → 8) + wo 09–13 (4) = 12; dagen ma, di, wo.
    # Review di 13 → wo 09 (20 h → 8) + wo 13 → do 09 (8) = 16; dagen di, wo, do.
    # Review → In uitvoering is terugsturen; daarna weer naar Review is gewoon
    # vooruit — dat tweede bezoek aan Review is géén rework van Review.
    assert t4 == {"Te doen": (1, 4.0, 8.0, 0), "In uitvoering": (2, 12.0, 24.0, 1),
                  "Review": (2, 16.0, 24.0, 0)}


def test_pt_never_exceeds_lt():
    _, tis = metrics.items_table([DONE, OPEN, SKIPPED, REWORK], metrics.Workflow(WF), NOW)
    assert all(r["pt_hours"] <= r["lt_hours"] for r in tis)


def test_value_stream():
    wf = metrics.Workflow(WF)
    _, tis = metrics.items_table([DONE, OPEN, SKIPPED, REWORK], wf, NOW)
    steps, totals = metrics.value_stream(tis, wf)
    by = {s["step"]: s for s in steps}
    assert list(by) == ["Te doen", "In uitvoering", "Review"]  # Done krijgt geen blok
    # Te doen, op volgorde van verlaten (T-1, T-4, T-3, T-2):
    # PT [8, 4, 8, 40] → mediaan 8, mR [4, 4, 32] → 8 ± 3,145 × 4 = 0–20,6
    # LT [16, 8, 16, 48] → mediaan 16, mR [8, 8, 32] → 16 ± 25,2 = 0–41,2
    #   (T-2: ma 5 → ma 12 raakt zes werkdagen, beide maandagen tellen) → T-2 is hoog
    assert by["Te doen"] == {"step": "Te doen", "items": 4,
                             "pt_median_h": 8.0, "pt_lower_h": 0.0, "pt_upper_h": 20.6,
                             "pt_outliers": 1,
                             "lt_median_h": 16.0, "lt_lower_h": 0.0, "lt_upper_h": 41.2,
                             "lt_outliers": 1, "doorgeklikt": 0, "ca_pct": 100}
    # In uitvoering: T-2 staat er nog (telt niet mee), T-4 werd teruggestuurd → 50%.
    # PT [16, 12] → 14 ± 12,6; LT [24, 24] heeft geen spreiding → geen limieten.
    iu = by["In uitvoering"]
    assert (iu["items"], iu["ca_pct"]) == (2, 50)
    assert (iu["pt_median_h"], iu["pt_lower_h"], iu["pt_upper_h"]) == (14.0, 1.4, 26.6)
    assert (iu["lt_median_h"], iu["lt_lower_h"], iu["lt_upper_h"]) == (24.0, None, None)
    # Review: T-1 en T-4 verlieten in dezelfde minuut → één punt, geen limieten.
    # T-4 kwam er twee keer, maar werd er nooit náártoe teruggestuurd.
    rv = by["Review"]
    assert (rv["pt_median_h"], rv["lt_median_h"], rv["lt_upper_h"], rv["ca_pct"]) == \
        (12.0, 20.0, None, 100)
    assert totals == {"pt_h": 34.0, "lt_h": 60.0, "rolled_ca_pct": 50}
    # De rijen zelf dragen rang, z en vlag, zodat het briefje na te rekenen is.
    t2 = next(r for r in tis if r["key"] == "T-2" and r["status"] == "Te doen")
    assert (t2["lt_pct_rank"], t2["lt_robust_z"], t2["outlier"], t2["doorgeklikt"]) == \
        (1.0, 5.4, "hoog", False)


def test_median_always_within_limits():
    wf = metrics.Workflow(WF)
    _, tis = metrics.items_table([DONE, OPEN, SKIPPED, REWORK], wf, NOW)
    for s in metrics.value_stream(tis, wf)[0]:
        for k in ("pt", "lt"):
            if s[f"{k}_upper_h"] is not None:
                assert s[f"{k}_lower_h"] <= s[f"{k}_median_h"] <= s[f"{k}_upper_h"]


def test_clicked_through():
    # Te doen → In uitvoering na 10 minuten: doorgeklikt.
    quick = issue("T-6", "2026-01-05T09:00:00.000+0100", [
        ("2026-01-05T09:10:00.000+0100", "To Do", "In Progress"),
        ("2026-01-07T09:00:00.000+0100", "In Progress", "Done")], "Done",
        "2026-01-07T09:00:00.000+0100")
    wf = metrics.Workflow(WF)
    _, tis = metrics.items_table([quick, DONE], wf, NOW)
    steps, _ = metrics.value_stream(tis, wf)
    assert {s["step"]: s["doorgeklikt"] for s in steps} == {"Te doen": 1, "In uitvoering": 0,
                                                                  "Review": 0}


def test_flag_items():
    wf = metrics.Workflow(WF)
    items, _ = metrics.items_table([DONE, OPEN, SKIPPED, REWORK], wf, NOW)
    limits = metrics.flag_items(items)
    by = {r["key"]: r for r in items}
    # Cycle time: T-1 3,0 en T-4 2,8, beide afgerond op do 8 jan 09:00 → één punt,
    # dus geen spreiding en geen limieten; het centrum is de mediaan van beide.
    assert limits["cycle_time"] == (2.9, None, None)
    assert by["T-1"]["ct_outlier"] == "" and by["T-2"]["ct_outlier"] is None  # T-2 loopt nog


def test_value_stream_skips_backfilled():
    wf = metrics.Workflow(WF)
    _, tis = metrics.items_table([DONE, REWORK], wf, NOW)
    steps, _ = metrics.value_stream(tis, wf, skip={"T-4"})
    assert {s["step"]: s["items"] for s in steps} == {"Te doen": 1, "In uitvoering": 1,
                                                       "Review": 1}


def test_learn_order_follows_the_data():
    # Jira noemt Review vóór In Progress; de items lopen andersom.
    wf = metrics.Workflow({"4": ("Review", "In Progress"), **WF})
    wf.learn_order([DONE, OPEN, REWORK])
    assert [n for n, _ in wf.statuses.values()][:3] == ["Te doen", "In uitvoering", "Review"]


def test_first_visit_from_a_later_step_is_not_rework():
    # Te doen → Review → In uitvoering: dev overgeslagen en daarna alsnog
    # opgepakt. In uitvoering was er nooit eerder, dus niets is teruggestuurd.
    skipped_dev = issue("T-5", "2026-01-05T09:00:00.000+0100", [
        ("2026-01-05T10:00:00.000+0100", "To Do", "Review"),
        ("2026-01-05T11:00:00.000+0100", "Review", "In Progress"),
        ("2026-01-05T12:00:00.000+0100", "In Progress", "Done"),
    ], "Done", "2026-01-05T12:00:00.000+0100")
    _, tis = metrics.items_table([skipped_dev], metrics.Workflow(WF), NOW)
    assert all(r["sent_back"] == 0 for r in tis)


# ── robuuste statistiek ──────────────────────────────────────────────────────

def test_xmr_hand_computed():
    # mediaan 4; mR [2, 2, 6, 6] → mediaan 4 → 4 ± 12,58
    series = list(enumerate([2, 4, 6, 0, 6]))
    centre, lower, upper = stats.xmr(series)
    assert (centre, lower, round(upper, 2)) == (4, 0.0, 16.58)


def test_xmr_merges_batches_and_falls_back_to_the_mean():
    # Drie items in één klik (t=1) zijn één punt: mR [6, 6] i.p.v. [6, 0, 0, 6].
    centre, _, upper = stats.xmr([(0, 2), (1, 8), (1, 8), (1, 8), (2, 2)])
    assert (centre, round(upper, 2)) == (8, 26.87)        # 8 + 3,145 × 6
    # Mediaan mR 0, gemiddelde niet: [0, 0, 9] → 2,66 × 3
    assert stats.xmr(list(enumerate([5, 5, 5, 14])))[2] == pytest.approx(5 + 2.66 * 3)
    assert stats.xmr([(0, 7), (1, 7)]) == (7, None, None)  # geen spreiding


def test_robust_z_and_percent_rank():
    values = [1, 2, 3, 4, 100]
    assert stats.robust_z(100, values) == pytest.approx(97 / 1.4826)  # MAD = 1
    assert stats.robust_z(3, [3, 3, 3, 9]) is None                     # MAD = 0
    assert stats.percent_rank(100, values) == 1.0
    assert stats.percent_rank(1, values) == 0.0
    assert stats.side(50, 0.0, 20) == "hoog" and stats.side(1, 2, 20) == "laag"
    assert stats.side(1, 0.0, 20) == ""                                # ondergrens 0
