"""Jira-issues → tabellen: items, time in status, daily (CFD), sprints en de waardestroom.

Puur rekenwerk, geen I/O. Duren per item in werkdagen (zie workdays.py):

- cycle time = eerste stap in een In Progress-status → laatste stap naar Done
- lead time  = aangemaakt → Done
- age        = eerste In Progress → nu, voor werk dat nu In Progress staat

De waardestroom rekent per stap (status) in uren:

- PT    = uren binnen kantooruren in de status (proxy, geen gemeten inspanning)
- LT    = kloktijd in de status
- %C&A  = aandeel items dat de stap verliet en er nooit naar werd teruggestuurd
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_right
from collections import Counter
from datetime import date, datetime, timedelta

from .workdays import is_workday, office_hours_between, workdays_between

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

    def learn_order(self, issues: list[dict]) -> None:
        """Zet de statussen in de volgorde waarin het werk er écht doorheen gaat.

        Jira's statuslijst staat niet in flow-volgorde (MOD: "In Review" vóór
        "Test", terwijl het werk Test → In Review loopt). Per status telt hier de
        gemiddelde plek van het eerste bezoek in het pad van elk item.
        """
        firsts: dict[str, list[int]] = {}
        for issue in issues:
            trans = transitions(issue)
            path = [trans[0][1] if trans else issue["fields"]["status"]["id"]]
            path += [to for _, _, to in trans]
            for pos, sid in enumerate(dict.fromkeys(path)):  # eerste bezoek telt
                firsts.setdefault(sid, []).append(pos)
        known = list(self.statuses)
        self.statuses = dict(sorted(self.statuses.items(), key=lambda kv: (
            CATEGORIES.index(kv[1][1]),
            statistics.mean(firsts[kv[0]]) if kv[0] in firsts else math.inf,
            known.index(kv[0]))))

    def is_later(self, a: str | None, b: str | None) -> bool:
        """Staat `a` verder in de flow dan `b`? Onbekende statussen: nee."""
        known = list(self.statuses)
        return a in known and b in known and known.index(a) > known.index(b)

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


def _sent_back(trans: list, first: str | None, wf: Workflow,
               stop: datetime) -> Counter:
    """Per status: hoe vaak het werk ernaar werd teruggestuurd.

    Teruggestuurd = een stap vanuit een latere status naar een status waar het
    item al eerder was (Test → In uitvoering). Dat is rework van díe status.
    Het opnieuw doorlopen van Test ná de fix telt níet tegen Test: Test deed
    zijn werk juist goed door de fout te vinden.
    """
    seen, out = {first}, Counter()
    for ts, frm, to in trans:
        if ts >= stop:
            break
        if to in seen and wf.is_later(frm, to):
            out[to] += 1
        seen.add(to)
    return out


def item_row(issue: dict, wf: Workflow, now: datetime) -> tuple[dict, list[dict]]:
    """Eén issue → (rij voor items.csv, rijen tijd per status)."""
    f = issue["fields"]
    trans = transitions(issue)
    created = parse_dt(f["created"])
    started, done = _started(created, trans, wf), _done(issue, trans, wf)
    stop = done or now

    current = f["status"]["id"]
    per_status: dict[str, dict] = {}
    for sid, a, b in spans(issue, trans, stop):
        st = per_status.setdefault(sid, {"workdays": 0.0, "visits": 0,
                                         "pt_hours": 0.0, "lt_hours": 0.0})
        st["workdays"] += workdays_between(a, b)
        st["visits"] += 1
        st["pt_hours"] += office_hours_between(a, b)
        st["lt_hours"] += (b - a).total_seconds() / 3600
    sent_back = _sent_back(trans, trans[0][1] if trans else current, wf, stop)

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
            "workdays": round(st["workdays"], 2), "visits": st["visits"],
            "pt_hours": round(st["pt_hours"], 1), "lt_hours": round(st["lt_hours"], 1),
            "sent_back": sent_back[sid],
            # Staat het item hier nú nog? Dan is het laatste bezoek niet af.
            "current": sid == current and done is None}
           for sid, st in per_status.items()]
    return row, tis


def items_table(issues: list[dict], wf: Workflow,
                now: datetime) -> tuple[list[dict], list[dict]]:
    items, tis = [], []
    for issue in issues:
        row, rows = item_row(issue, wf, now)
        items.append(row)
        tis.extend(rows)
    return items, tis


# ── waardestroom ─────────────────────────────────────────────────────────────

def _modal_class(values: list[float]) -> tuple[float, float] | tuple[None, None]:
    """De meest voorkomende klasse (van, tot) in uren; bij gelijkspel de kleinste.

    Verdubbelende klassen (<1, 1–2, 2–4, … 512–1024 h): tijden zijn continu én
    scheef verdeeld. Met vaste klassen van een halve dag viel de modus op MOD
    in "0 h" met 7 van de 51 items — een klasse die niets typeert.
    """
    if not values:
        return None, None
    classes = Counter(0 if v < 1 else 2 ** math.floor(math.log2(v)) for v in values)
    top = max(classes.values())
    lo = min(c for c, n in classes.items() if n == top)
    return lo, (1 if lo == 0 else 2 * lo)


def value_stream(tis: list[dict], wf: Workflow,
                 skip: set[str] = frozenset()) -> tuple[list[dict], dict]:
    """(stappen, totalen) — een pure aggregatie van de time-in-status-rijen.

    Een stap is elke To Do- of In Progress-status; Done is het eind van de
    stroom en krijgt geen blok.
    - PT/LT: over items die de stap verlieten (een lopend bezoek is niet af).
    - %C&A: van de items die de stap verlieten, het deel dat er nooit vanuit
      een latere stap naar werd teruggestuurd (zie `_sent_back`).
    `skip`: sleutels die niet meetellen (backfilled items, net als bij de percentielen).
    """
    names = [n for n, _ in wf.statuses.values()]
    by_step: dict[str, list[dict]] = {}
    for r in tis:
        if r["category"] != "Done" and r["key"] not in skip:
            by_step.setdefault(r["status"], []).append(r)

    steps = []
    for name in sorted(by_step, key=lambda n: (CATEGORIES.index(by_step[n][0]["category"]),
                                                names.index(n) if n in names else len(names))):
        rows = by_step[name]
        left = [r for r in rows if not r["current"]]
        ca_pop = [r for r in rows if not r["current"] or r["visits"] > 1]
        if not ca_pop:
            continue  # niemand heeft deze stap ooit verlaten
        pt = [r["pt_hours"] for r in left]
        lt = [r["lt_hours"] for r in left]
        (pt_lo, pt_hi), (lt_lo, lt_hi) = _modal_class(pt), _modal_class(lt)
        steps.append({
            "step": name,
            "items": len(ca_pop),
            "pt_mode_from_h": pt_lo, "pt_mode_to_h": pt_hi,
            "pt_median_h": round(statistics.median(pt), 1) if pt else None,
            "lt_mode_from_h": lt_lo, "lt_mode_to_h": lt_hi,
            "lt_median_h": round(statistics.median(lt), 1) if lt else None,
            "ca_pct": round(100 * sum(1 for r in ca_pop if not r["sent_back"])
                            / len(ca_pop)),
        })

    pt_total = sum(s["pt_median_h"] or 0 for s in steps)
    lt_total = sum(s["lt_median_h"] or 0 for s in steps)
    rolled = 1.0
    for s in steps:
        rolled *= s["ca_pct"] / 100
    totals = {"pt_h": round(pt_total, 1), "lt_h": round(lt_total, 1),
              "activity_pct": round(100 * pt_total / lt_total) if lt_total else None,
              "rolled_ca_pct": round(100 * rolled) if steps else None}
    return steps, totals


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
