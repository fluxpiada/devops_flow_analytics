from datetime import date, datetime

from devops_flow import metrics
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
