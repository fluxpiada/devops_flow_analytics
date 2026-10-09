"""Jira-issues → drie tabellen: items, daily (CFD) en sprints.

Puur rekenwerk, geen I/O. Alle duren in werkdagen (zie workdays.py).

- cycle time = eerste stap in een In Progress-status → laatste stap naar Done
- lead time  = aangemaakt → Done
- age        = eerste In Progress → nu, voor werk dat nu In Progress staat
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date, datetime, timedelta

from .workdays import is_workday, workdays_between

CATEGORIES = ("To Do", "In Progress", "Done")

# ≈1 uur: een issue waarvan álle statusovergangen binnen dit venster vallen is
# achteraf bijgewerkt — de tijdstempels beschrijven de administratie, niet het werk.
BACKFILL_THRESHOLD_D = 0.04


def parse_dt(value: str) -> datetime:
    """Jira ISO-string → naïeve lokale datetime."""
    return datetime.fromisoformat(value).replace(tzinfo=None)


class Workflow:
    """Status-id → (naam, categorie), in flow-volgorde.

    Op id, niet op naam: de changelog bewaart de naam zoals die tóén was, in de
    taal van toen ("Done"), terwijl de API hem nu in de taal van het token
    teruggeeft ("Gedaan"). Het id blijft gelijk.
    """

    def __init__(self, statuses: dict[str, tuple[str, str]]):
        self.statuses = statuses
        self.unknown: set[str] = set()

    def name(self, sid: str | None) -> str:
        if sid in self.statuses:
            return self.statuses[sid][0]
        self.unknown.add(str(sid))
        return f"status {sid}"

    def category(self, sid: str | None) -> str:
        return self.statuses.get(sid, ("", "To Do"))[1]

    def ordered(self, ids: set[str]) -> list[str]:
        """Per categorie, dan in de volgorde van de workflow."""
        known = list(self.statuses)
        return sorted(ids, key=lambda i: (CATEGORIES.index(self.category(i)),
                                          known.index(i) if i in known else len(known)))


# ── per issue ────────────────────────────────────────────────────────────────


def transitions(issue: dict) -> list[tuple[datetime, str | None, str | None]]:
    """(moment, van-id, naar-id) van elke statuswijziging, op tijd gesorteerd."""
    out = [(parse_dt(h["created"]), item.get("from"), item.get("to"))
           for h in (issue.get("changelog") or {}).get("histories") or []
           for item in h.get("items") or [] if item.get("field") == "status"]
    return sorted(out, key=lambda t: t[0])


def spans(issue: dict, trans: list, end: datetime) -> list[tuple[str, datetime, datetime]]:
    """(status-id, van, tot) per aaneengesloten verblijf, van created tot `end`.

    Aanname: het issue stond vanaf created in de van-status van de eerste overgang.
    """
    cursor = parse_dt(issue["fields"]["created"])
    status = trans[0][1] if trans else issue["fields"]["status"]["id"]
    out = []
    for ts, _, to in trans:
        if ts >= end:
            break
        out.append((status, cursor, ts))
        cursor, status = ts, to
    if end > cursor:
        out.append((status, cursor, end))
    return out


def _started(created: datetime, trans: list, wf: Workflow) -> datetime | None:
    first = trans[0][1] if trans else None
    if first and wf.category(first) == "In Progress":
        return created  # aangemaakt ín een In Progress-status
    return next((ts for ts, _, to in trans if wf.category(to) == "In Progress"), None)


def _done(issue: dict, trans: list, wf: Workflow) -> datetime | None:
    """Het moment van de laatste stap van niet-Done naar Done, als het issue nu Done is."""
    f = issue["fields"]
    if wf.category(f["status"]["id"]) != "Done":
        return None
    done = None
    for ts, frm, _ in reversed(trans):
        done = ts
        if wf.category(frm) != "Done":
            break
    return done or parse_dt(f.get("resolutiondate") or f["created"])


def item_row(issue: dict, wf: Workflow, now: datetime) -> tuple[dict, list[dict]]:
    """Eén issue → (rij voor items.csv, rijen tijd per status)."""
    f = issue["fields"]
    trans = transitions(issue)
    created = parse_dt(f["created"])
    started, done = _started(created, trans, wf), _done(issue, trans, wf)
    stop = done or now

    per_status: dict[str, float] = {}
    for sid, a, b in spans(issue, trans, stop):
        per_status[sid] = per_status.get(sid, 0.0) + workdays_between(a, b)
    current = f["status"]["id"]

    def wd(a, b):
        return round(workdays_between(a, b), 1) if a and b else None

    row = {
        "key": issue["key"],
        "type": (f.get("issuetype") or {}).get("name"),
        "summary": (f.get("summary") or "")[:120],
        "status": wf.name(current),
        "category": wf.category(current),
        "created": created,
        "started": started,
        "done": done,
        "cycle_time": wd(started, done),
        "lead_time": wd(created, done),
        # Alleen werk dat nú in een In Progress-status staat: teruggezet naar To Do is geen WIP.
        "age": (wd(started, now) if started and not done
                and wf.category(current) == "In Progress" else None),
        "story_points": f.get("story_points"),
        "sprint": None,  # gevuld vanuit de sprintrapporten
        "backfilled": len(trans) >= 2 and (trans[-1][0] - trans[0][0])
        .total_seconds() / 86400 < BACKFILL_THRESHOLD_D,
    }
    tis = [{"key": issue["key"], "status": wf.name(sid), "category": wf.category(sid),
            "workdays": round(d, 2)} for sid, d in per_status.items()]
    return row, tis


def items_table(issues: list[dict], wf: Workflow,
                now: datetime) -> tuple[list[dict], list[dict]]:
    items, tis = [], []
    for issue in issues:
        row, rows = item_row(issue, wf, now)
        items.append(row)
        tis.extend(rows)
    return items, tis


# ── per dag (CFD) ────────────────────────────────────────────────────────────


def daily_table(issues: list[dict], wf: Workflow, first: date,
                now: datetime) -> tuple[list[str], list[list]]:
    """(kolommen, rijen): per werkdag het aantal issues per status aan het eind
    van die dag. Breed, zodat Excel er direct een gestapeld vlakdiagram van maakt.
    """
    days = [first + timedelta(days=i) for i in range((now.date() - first).days + 1)]
    days = [d for d in days if is_workday(d)]
    samples = [min(datetime.combine(d + timedelta(days=1), datetime.min.time()), now)
               for d in days]
    counts: list[dict[str, int]] = [{} for _ in days]
    for issue in issues:
        sp = spans(issue, transitions(issue), now + timedelta(seconds=1))
        starts = [a for _, a, _ in sp]
        for i, t in enumerate(samples):
            j = bisect_right(starts, t) - 1
            if j >= 0 and t < sp[j][2]:
                sid = sp[j][0]
                counts[i][sid] = counts[i].get(sid, 0) + 1

    ids = wf.ordered({sid for c in counts for sid in c})
    wip = [sid for sid in ids if wf.category(sid) == "In Progress"]
    rows = [[d, *(c.get(sid, 0) for sid in ids), sum(c.get(sid, 0) for sid in wip)]
            for d, c in zip(days, counts)]
    return ["date", *(wf.name(sid) for sid in ids), "wip"], rows


# ── per sprint ───────────────────────────────────────────────────────────────


def _points(issue: dict, stat: str) -> float:
    return ((issue.get(stat) or {}).get("statFieldValue") or {}).get("value") or 0


def sprint_table(sprints: list[dict], reports: list[dict | None],
                 items: list[dict]) -> list[dict]:
    """Eén rij per afgesloten sprint, uit Jira's Sprint Report.

    committed = in de sprint bij de start; completed_committed daarvan afgerond
    (de teller van say/do); completed_points = velocity zoals Jira hem toont.
    Vult tegelijk `sprint` in de items-rijen voor het werk dat erin afrondde.
    """
    by_key = {r["key"]: r for r in items}
    rows = []
    for s, rep in zip(sprints, reports):
        if rep is None:
            continue
        completed = rep.get("completedIssues") or []
        not_done = rep.get("issuesNotCompletedInCurrentSprint") or []
        removed = rep.get("puntedIssues") or []
        elsewhere = rep.get("issuesCompletedInAnotherSprint") or []
        added = set(rep.get("issueKeysAddedDuringSprint") or {})
        committed = [i for i in completed + not_done + removed + elsewhere
                     if i["key"] not in added]
        for i in completed:
            if i["key"] in by_key:
                by_key[i["key"]]["sprint"] = s["name"]
        rows.append({
            "sprint": s["name"],
            "start": parse_dt(s["startDate"]).date(),
            "end": parse_dt(s["completeDate"]).date(),
            "committed": len(committed),
            "added": len(added),
            "removed": len(removed),
            "completed": len(completed),
            "completed_committed": sum(1 for i in completed if i["key"] not in added),
            "not_completed": len(not_done),
            "committed_points": sum(_points(i, "estimateStatistic") for i in committed),
            "completed_points": sum(_points(i, "currentEstimateStatistic")
                                    for i in completed),
        })
    return rows
