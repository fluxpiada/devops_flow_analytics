#!/usr/bin/env python3
"""Flow-analyse van een heel Jira-project (CFD-achtig, uit de changelog).

Leest van één Jira-project alle statusovergangen uit de changelog en leidt
daaruit af hoe lang werk gemiddeld in elke statuscategorie blijft hangen —
To Do, In Progress, Done — met een drill-down naar de losse statussen binnen
elke categorie en een drill-down + trendlijn per sprint.

Read-only. Geen urenregistratie nodig: alles komt uit tijdstempels die Jira
zelf al bijhoudt.

Gebruik:
    uv run python scripts/jira_flow_analysis.py \\
        --jira-url https://jira.vitens.lan/jira/browse/MOD
    ... [--project MOD] [--months 6|12] [--issue-types Story,Bug]
    ... [--include-subtasks] [--no-sprint-snap] [--refresh]
    ... [--creds creds.yaml] [--out-dir output/]

Het venster is standaard 6 maanden en wordt naar SPRINTGRENZEN gesnapt: alleen
sprints die volledig binnen het venster vallen en afgerond zijn tellen mee, zodat
een half gemeten sprint de gemiddelden niet vertekent. Artefacten landen in
output/<PROJECT>/.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import requests

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from jira_core import (  # noqa: E402 — naast dit script
    JiraClient,
    _dt,
    _find_creds,
    _is_backfilled,
    _load_creds,
    _md_table,
    _status_transitions,
    _time_in_status_workdays,
    _warn,
    _workdays_elapsed,
    _write_csv,
)

FLOW_CACHE_VERSION = 1

# Jira's eigen statusCategory-sleutels → de drie kolommen van een cumulative
# flow diagram. De namen komen uit Jira; de volgorde is de flow-richting.
_CATEGORY_BY_KEY = {"new": "To Do", "indeterminate": "In Progress",
                    "done": "Done"}
CATEGORIES = ("To Do", "In Progress", "Done")
UNKNOWN_CATEGORY = "onbekend"

_PROJECT_KEY_RE = re.compile(r"([A-Z][A-Z0-9_]+)")
_SPARK = "▁▂▃▄▅▆▇█"

# Zoveel issues met dezelfde aanmaakminuut = een import, geen toeval.
BULK_CREATE_MIN = 5


# ── invoer ───────────────────────────────────────────────────────────────────


def _project_key(arg: str) -> str:
    """Projectsleutel uit een browse-URL, een projects-URL of een kale sleutel.

    Accepteert .../browse/MOD, .../browse/MOD-123, .../projects/MOD en MOD.
    """
    raw = (arg or "").strip().rstrip("/")
    tail = raw.rsplit("/", 1)[-1] if "/" in raw else raw
    tail = tail.split("?")[0]
    m = _PROJECT_KEY_RE.match(tail.upper())
    if not m:
        raise SystemExit(
            f"Kan geen projectsleutel afleiden uit {arg!r}. Verwacht bv. "
            f"https://jira.vitens.lan/jira/browse/MOD of gewoon MOD.")
    return m.group(1)


def _months_ago(now: datetime, months: int) -> datetime:
    """Zelfde dag, `months` maanden terug; klemt op de maandlengte."""
    total = (now.year * 12 + now.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    day = min(now.day, [31, 29 if year % 4 == 0 and (year % 100 or not year % 400)
                        else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return now.replace(year=year, month=month, day=day)


def _ask_months(default: int = 6) -> int:
    """Eén prompt bij interactief gebruik; niet-interactief stil de default."""
    if not sys.stdin.isatty():
        return default
    answer = input(f"  Venster? [1] {default} maanden (default)  "
                   f"[2] 12 maanden: ").strip()
    return 12 if answer == "2" else default


# ── statistiek ───────────────────────────────────────────────────────────────


def _p85(values: list[float]) -> float | None:
    """85e percentiel met lineaire interpolatie (geen numpy)."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return round(s[0], 1)
    pos = 0.85 * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (pos - lo), 1)


def _stats(values: list[float]) -> dict:
    """n / mediaan / gemiddelde / p85 / totaal — de kop is de mediaan.

    Doorlooptijden zijn scheef verdeeld (een handvol issues blijft maanden
    liggen); een kaal gemiddelde beschrijft dan niemand. Mediaan is het
    typische geval, p85 de staart waar de planning last van heeft.
    """
    if not values:
        return {"n": 0, "median": None, "mean": None, "p85": None, "total": 0.0}
    return {
        "n": len(values),
        "median": round(statistics.median(values), 1),
        "mean": round(statistics.fmean(values), 1),
        "p85": _p85(values),
        "total": round(sum(values), 1),
    }


def _trend(series: list[float | None]) -> dict | None:
    """Least-squares helling over de sprintindex, in dagen per sprint."""
    pts = [(i, v) for i, v in enumerate(series) if v is not None]
    if len(pts) < 3:
        return None
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    denom = sum((x - mx) ** 2 for x, _ in pts)
    if denom == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in pts) / denom
    direction = "stabiel" if abs(slope) < 0.05 else (
        "stijgend" if slope > 0 else "dalend")
    return {"slope_days_per_sprint": round(slope, 2), "direction": direction,
            "n_sprints": n}


def _nice_bin(span: float, target: int) -> float:
    """Bakbreedte die op een 'rond' getal uitkomt (1, 2, 2.5, 5, 10 × 10ⁿ)."""
    raw = span / target
    if raw <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5):
        if raw <= mag * mult:
            return mag * mult
    return mag * 10


def _histogram(values: list[float], target_bins: int = 8) -> list[tuple]:
    """(ondergrens, bovengrens, aantal) per bak.

    Eén kengetal verbergt of de verdeling één piek heeft of twee; die vraag —
    "wat is nou het typische geval?" — beantwoordt alleen de verdeling zelf.
    """
    if not values:
        return []
    lo, hi = min(values), max(values)
    width = _nice_bin(hi - lo, target_bins) if hi > lo else 1.0
    start = math.floor(lo / width) * width
    n_bins = int(math.floor((hi - start) / width)) + 1
    counts = [0] * n_bins
    for v in values:
        counts[min(int((v - start) // width), n_bins - 1)] += 1
    return [(start + i * width, start + (i + 1) * width, counts[i])
            for i in range(n_bins)]


def _sparkline(series: list[float | None]) -> str:
    """Reeks als blokjes — een trendlijn die in platte tekst leesbaar blijft."""
    vals = [v for v in series if v is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    span = hi - lo
    out = []
    for v in series:
        if v is None:
            out.append("·")
        elif span == 0:
            out.append(_SPARK[len(_SPARK) // 2])
        else:
            out.append(_SPARK[min(int((v - lo) / span * (len(_SPARK) - 1)),
                                  len(_SPARK) - 1)])
    return "".join(out)


# ── statuscategorieën ────────────────────────────────────────────────────────


def build_status_map(jira: JiraClient, project_key: str) -> dict[str, str]:
    """{statusnaam: categorie} uit Jira's eigen statusCategory.

    De changelog levert alleen status*namen* (fromString/toString), geen
    categorie — die moet uit de workflowdefinitie komen, niet uit een
    hardgecodeerde lijst die per project anders ligt.
    """
    try:
        itypes = jira.project_statuses(project_key)
    except requests.HTTPError as exc:
        # Een vertypte projectsleutel is de meest waarschijnlijke fout van
        # allemaal; een kale traceback is daar een slecht antwoord op.
        code = exc.response.status_code if exc.response is not None else None
        if code == 404:
            raise SystemExit(
                f"Jira kent geen project {project_key!r} (404). Controleer de "
                f"sleutel — het is het prefix vóór het issuenummer, dus MOD in "
                f"MOD-123.") from exc
        if code in (401, 403):
            raise SystemExit(
                f"Geen toegang tot project {project_key} ({code}). Het token in "
                f"creds.yaml heeft geen leesrechten op dit project, of is "
                f"verlopen.") from exc
        raise SystemExit(f"Jira gaf {code} op de workflow van {project_key}: "
                         f"{exc}") from exc

    out: dict[str, str] = {}
    for itype in itypes:
        for st in itype.get("statuses") or []:
            key = ((st.get("statusCategory") or {}).get("key") or "").lower()
            name = st.get("name")
            if name:
                out[name] = _CATEGORY_BY_KEY.get(key, UNKNOWN_CATEGORY)
    if not out:
        raise SystemExit(f"Project {project_key} leverde geen statussen op — "
                         f"bestaat de sleutel, en heeft de PAT leesrechten?")
    return out


def canonical_statuses(status_map: dict[str, str]) -> dict[str, str]:
    """{statusnaam in kleine letters: schrijfwijze van de huidige workflow}.

    De changelog bewaart de statusnaam zoals die op dát moment was — en dat
    verschilt in de praktijk soms alleen in hoofdlettergebruik ("in Review"
    versus "In Review"). Zonder deze normalisatie valt één status uiteen in
    twee rijen, waarvan er één als *onbekend* wordt geteld.
    """
    return {name.lower(): name for name in status_map}


# ── sprints ──────────────────────────────────────────────────────────────────

_SPRINT_KV_RE = re.compile(r"(\w+)=(.*?)(?=,\w+=|\]$|$)")


def find_sprint_field(jira: JiraClient) -> str | None:
    """Het id van het Sprint-customfield (greenhopper), of None."""
    try:
        fields = jira.fields()
    except requests.RequestException as exc:
        _warn(f"veldenlijst niet op te halen ({exc}) — geen sprintanalyse")
        return None
    for f in fields:
        schema = f.get("schema") or {}
        if "gh-sprint" in str(schema.get("custom", "")):
            return f["id"]
    for f in fields:  # fallback op naam, voor afwijkende plugin-ids
        if (f.get("name") or "").strip().lower() == "sprint":
            return f["id"]
    return None


def _sprint_dt(value: str | None) -> datetime | None:
    if not value or value in ("<null>", "null", "None"):
        return None
    try:
        return _dt(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_sprint_value(value) -> dict | None:
    """Eén sprintwaarde → dict. Data Center levert óf een greenhopper-string
    (`…Sprint@1f39bc[id=…,state=CLOSED,name=…,startDate=…]`) óf, op nieuwere
    versies, al een JSON-object — beide komen hier binnen."""
    if isinstance(value, dict):
        raw = value
    elif isinstance(value, str):
        inner = value[value.find("[") + 1:value.rfind("]")] if "[" in value else ""
        raw = {k: v for k, v in _SPRINT_KV_RE.findall(inner)}
    else:
        return None
    sid = raw.get("id")
    start = _sprint_dt(str(raw.get("startDate")) if raw.get("startDate") else None)
    end = _sprint_dt(str(raw.get("endDate")) if raw.get("endDate") else None)
    complete = _sprint_dt(str(raw.get("completeDate"))
                          if raw.get("completeDate") else None)
    if sid is None or start is None or end is None:
        return None
    return {
        "id": str(sid),
        "name": str(raw.get("name") or f"sprint {sid}"),
        "state": str(raw.get("state") or "").upper(),
        "start": start,
        "end": complete or end,      # feitelijke afsluiting gaat vóór de planning
        "planned_end": end,
        "closed": bool(complete) or str(raw.get("state") or "").upper() == "CLOSED",
    }


def build_sprint_calendar(issues: list[dict], sprint_field: str) -> list[dict]:
    """Alle sprints die in de opgehaalde issues voorkomen, op startdatum."""
    found: dict[str, dict] = {}
    for issue in issues:
        raw = (issue.get("fields") or {}).get(sprint_field)
        for value in (raw if isinstance(raw, list) else [raw] if raw else []):
            sprint = _parse_sprint_value(value)
            if sprint and sprint["id"] not in found:
                found[sprint["id"]] = sprint
    return sorted(found.values(), key=lambda s: s["start"])


def snap_window(sprints: list[dict], raw_start: datetime,
                raw_end: datetime) -> tuple[list[dict], datetime, datetime]:
    """Houd alleen afgeronde sprints die VOLLEDIG in het ruwe venster vallen.

    Een half gemeten sprint aan de rand levert per definitie te lage
    doorlooptijden (het werk dat erna afliep valt buiten beeld) — die
    deelsprints vallen dus af, en het venster krimpt naar de echte
    sprintgrenzen.
    """
    kept = [s for s in sprints
            if s["closed"] and s["start"] >= raw_start and s["end"] <= raw_end]
    if not kept:
        return [], raw_start, raw_end
    return kept, kept[0]["start"], kept[-1]["end"]


def sprint_periods(sprints: list[dict], window_end: datetime) -> list[dict]:
    """Aaneengesloten perioden: sprint i loopt tot de start van sprint i+1.

    Sprints overlappen in de praktijk een paar uur of laten een gat vallen;
    door de grenzen door te trekken hoort elke afronddatum bij precies één
    sprint, zonder issues die in een gat verdwijnen.
    """
    out = []
    for i, s in enumerate(sprints):
        end = sprints[i + 1]["start"] if i + 1 < len(sprints) else max(
            s["end"], window_end)
        out.append({**s, "period_start": s["start"], "period_end": end})
    return out


# ── ophalen + cache ──────────────────────────────────────────────────────────


def build_jql(project: str, start: datetime, issue_types: str | None,
              include_subtasks: bool) -> str:
    since = start.strftime("%Y-%m-%d")
    parts = [f'project = "{project}"',
             f'(resolutiondate >= "{since}" OR '
             f'(resolutiondate IS EMPTY AND updated >= "{since}"))']
    if issue_types:
        types = ", ".join(f'"{t.strip()}"' for t in issue_types.split(",")
                          if t.strip())
        parts.append(f"issuetype IN ({types})")
    elif not include_subtasks:
        parts.append("issuetype NOT IN subTaskIssueTypes()")
    return " AND ".join(parts) + " ORDER BY key ASC"


def _cache_path(out_dir: Path, project: str) -> Path:
    return out_dir / project / f"jira_flow_cache_{project}.json"


def load_flow_cache(path: Path, fingerprint: dict) -> list[dict] | None:
    """Gevalideerde cachelees; None ⇒ de aanroeper haalt live op."""
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _warn(f"flow-cache onleesbaar ({exc}) — live ophalen")
        return None
    if raw.get("cache_version") != FLOW_CACHE_VERSION:
        _warn(f"flow-cache {path.name} is van een oudere versie — live ophalen")
        return None
    if {k: raw.get(k) for k in fingerprint} != fingerprint:
        _warn(f"flow-cache {path.name} hoort bij een andere query "
              f"(project/venster/issuetypes) — live ophalen")
        return None
    try:
        age_d = (datetime.now() - datetime.fromisoformat(raw["generated"])).days
    except (KeyError, ValueError):
        age_d = None
    note = f", {age_d} dagen oud" if age_d is not None else ""
    print(f"  {len(raw.get('issues') or [])} issues uit cache {path.name}{note} "
          f"(--refresh voor een verse fetch)")
    if age_d is not None and age_d > 7:
        _warn(f"flow-cache is {age_d} dagen oud — overweeg --refresh")
    return raw.get("issues") or []


def fetch_issues(jira: JiraClient, project: str, jql: str, sprint_field: str | None,
                 *, out_dir: Path, months: int, refresh: bool,
                 cache_path: Path | None = None) -> list[dict]:
    path = cache_path or _cache_path(out_dir, project)
    fingerprint = {"project": project, "months": months, "jql": jql}
    issues = None if refresh else load_flow_cache(path, fingerprint)
    if issues is not None:
        return issues

    fields = ["summary", "issuetype", "status", "created", "resolutiondate",
              "updated", "assignee"]
    if sprint_field:
        fields.append(sprint_field)
    print(f"  JQL: {jql}")
    issues = jira.search_all(jql, ",".join(fields), expand="changelog",
                             page_size=100, progress=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps({**fingerprint,
                                    "cache_version": FLOW_CACHE_VERSION,
                                    "generated": datetime.now().isoformat(
                                        timespec="seconds"),
                                    "issues": issues}, ensure_ascii=False),
                        encoding="utf-8")
        print(f"  flow-cache geschreven: {path}")
    except OSError as exc:
        _warn(f"flow-cache niet weggeschreven: {exc}")
    return issues


# ── analyse ──────────────────────────────────────────────────────────────────


def _observation_end(issue: dict, transitions: list[dict], category_of,
                     now: datetime) -> datetime:
    """Het moment waarop het issue ophield te stromen.

    Voor een issue dat in een eindstatus staat is dat de LAATSTE
    statusovergang: dagen 'in Closed' zijn geen doorlooptijd maar archieftijd.
    Is er een resolutiedatum zonder afsluitende statusovergang, dan telt die.
    Loopt het nog, dan telt de tijd door tot nu.
    """
    resolved = (issue.get("fields") or {}).get("resolutiondate")
    if not resolved:
        return now
    current = ((issue.get("fields") or {}).get("status") or {}).get("name")
    if transitions and category_of(current) == "Done":
        return max(_dt(transitions[-1]["ts"]), _dt(resolved))
    return _dt(resolved)


def _issue_record(issue: dict, canon: dict[str, str], category_of,
                  now: datetime) -> dict:
    """Eén issue → werkdagen per status en per categorie, plus vlaggen."""
    f = issue["fields"]
    transitions = _status_transitions(issue)
    created = _dt(f["created"])
    current = canon.get(((f.get("status") or {}).get("name") or "").lower(),
                        (f.get("status") or {}).get("name"))
    end = _observation_end(issue, transitions, category_of, now)

    # `_time_in_status_workdays` sluit af op resolutiondate/updated; hier telt
    # het venster tot de laatste overgang. Daarom een eigen einde meegeven via
    # een ondiepe kopie van de resolutievelden.
    shim = {"fields": {**f, "resolutiondate": end.isoformat(),
                       "updated": end.isoformat()}, "changelog": issue.get("changelog")}

    per_status: dict[str, float] = defaultdict(float)
    per_cat: dict[str, float] = defaultdict(float)
    for status, days in _time_in_status_workdays(shim, transitions).items():
        name = canon.get(status.lower(), status)
        per_status[name] += days
        per_cat[category_of(name)] += days
    per_status = {k: round(v, 1) for k, v in per_status.items()}

    sprint_changes = sum(
        1 for hist in (issue.get("changelog") or {}).get("histories") or []
        for item in hist.get("items") or []
        if item.get("field") == "Sprint")

    resolved = f.get("resolutiondate")
    return {
        "key": issue["key"],
        "issuetype": (f.get("issuetype") or {}).get("name"),
        "summary": (f.get("summary") or "")[:80],
        "status": current,
        "created": f["created"],
        "resolved": resolved,
        "resolved_dt": _dt(resolved) if resolved else None,
        "lead_time_days": round(_workdays_elapsed(created, end), 1),
        "per_status": per_status,
        "per_category": {c: round(per_cat.get(c, 0.0), 1)
                         for c in (*CATEGORIES, UNKNOWN_CATEGORY)},
        "terminal_status": current if resolved else None,
        "in_flight": resolved is None,
        "backfilled": _is_backfilled(transitions),
        "sprint_changes": sprint_changes,
        "spilled": sprint_changes > 1,
    }


def detect_bulk_creation(records: list[dict]) -> dict:
    """Aanmaakmomenten waarop een hele partij issues tegelijk is ontstaan.

    Bij een backlog-import krijgen tientallen issues dezelfde `created` — hun
    klok begint dan bij de import en niet bij het moment waarop iemand het werk
    vroeg. Dat blaast de To Do-tijd (en dus de doorlooptijd) op van precies die
    issues, en niet van de rest. Ze apart houden is het verschil tussen "het
    duurt 72 dagen" en "het duurt 72 dagen sinds we de backlog inlaadden".
    """
    per_minute = Counter(r["created"][:16] for r in records)
    moments = sorted(((ts, n) for ts, n in per_minute.items()
                      if n >= BULK_CREATE_MIN), key=lambda x: (-x[1], x[0]))
    bulk_ts = {ts for ts, _ in moments}
    for r in records:
        r["bulk_created"] = r["created"][:16] in bulk_ts
    n_bulk = sum(1 for r in records if r["bulk_created"])
    return {
        "moments": [{"timestamp": ts, "issues": n} for ts, n in moments],
        "n_bulk_created": n_bulk,
        "n_total": len(records),
        "pct": round(n_bulk / len(records) * 100, 1) if records else None,
    }


def _sprint_of(record: dict, periods: list[dict]) -> dict | None:
    ts = record["resolved_dt"]
    if ts is None:
        return None
    for p in periods:
        if p["period_start"] <= ts < p["period_end"]:
            return p
    return None


def build_flow(issues: list[dict], status_map: dict[str, str],
               periods: list[dict], window: dict, now: datetime) -> dict:
    """Alles bij elkaar: per categorie, per status en per sprint."""
    canon = canonical_statuses(status_map)

    def category_of(name: str | None) -> str:
        return status_map.get(canon.get((name or "").lower(), name),
                              UNKNOWN_CATEGORY)

    records = [_issue_record(i, canon, category_of, now) for i in issues]
    bulk = detect_bulk_creation(records)

    start, end = _dt(window["start"]), _dt(window["end"])
    in_window = [r for r in records
                 if r["resolved_dt"] and start <= r["resolved_dt"] <= end]
    excluded_backfill = [r for r in in_window if r["backfilled"]]
    analysed = [r for r in in_window if not r["backfilled"]]
    in_flight = [r for r in records if r["in_flight"]]

    cat_values: dict[str, list[float]] = {c: [] for c in
                                          (*CATEGORIES, UNKNOWN_CATEGORY)}
    status_values: dict[str, list[float]] = defaultdict(list)
    terminal = Counter()
    for r in analysed:
        for c, days in r["per_category"].items():
            cat_values[c].append(days)
        for s, days in r["per_status"].items():
            status_values[s].append(days)
        if r["terminal_status"]:
            terminal[r["terminal_status"]] += 1

    categories = {c: _stats(v) for c, v in cat_values.items() if c in CATEGORIES}
    if any(cat_values[UNKNOWN_CATEGORY]):  # alleen tonen als er écht tijd in zat
        categories[UNKNOWN_CATEGORY] = _stats(cat_values[UNKNOWN_CATEGORY])
    # Een status die alleen eindstatus is (Closed) kent per definitie geen
    # verblijfsduur — zonder deze seed valt hij helemaal uit de drill-down,
    # terwijl juist de vraag "waar eindigt het werk?" hem nodig heeft.
    for name in terminal:
        status_values.setdefault(name, [])
    statuses = {}
    for name, values in status_values.items():
        cat = category_of(name)
        cat_total = categories.get(cat, {}).get("total") or 0
        st = _stats(values)
        st["category"] = cat
        st["share_of_category_pct"] = (round(st["total"] / cat_total * 100, 1)
                                       if cat_total else None)
        st["times_terminal"] = terminal.get(name, 0)
        statuses[name] = st

    by_sprint: dict[str, list[dict]] = defaultdict(list)
    outside = 0
    for r in analysed:
        sprint = _sprint_of(r, periods)
        if sprint is None:
            outside += 1
            r["sprint"] = None
            continue
        r["sprint"] = sprint["name"]
        by_sprint[sprint["id"]].append(r)

    sprint_rows = []
    for p in periods:
        rs = by_sprint.get(p["id"], [])
        sprint_rows.append({
            "id": p["id"], "name": p["name"],
            # De toewijzingsperiode, niet de sprintdatums: sprints overlappen
            # elkaar in de praktijk een paar dagen, en dan is de grens waarop
            # geteld is de eerlijke kolom om te tonen.
            "start": p["period_start"].date().isoformat(),
            "end": p["period_end"].date().isoformat(),
            "sprint_end": p["end"].date().isoformat(),
            "n_completed": len(rs),
            "lead_time": _stats([r["lead_time_days"] for r in rs]),
            "per_category": {c: _stats([r["per_category"][c] for r in rs])
                             for c in CATEGORIES},
            "n_spilled": sum(1 for r in rs if r["spilled"]),
            "spilled_pct": (round(sum(1 for r in rs if r["spilled"])
                                  / len(rs) * 100, 1) if rs else None),
        })

    trends = {c: _trend([s["per_category"][c]["median"] for s in sprint_rows])
              for c in CATEGORIES}
    trends["lead_time"] = _trend([s["lead_time"]["median"] for s in sprint_rows])
    trends["throughput"] = _trend([float(s["n_completed"]) for s in sprint_rows])

    unknown = sorted({s for r in analysed for s in r["per_status"]
                      if s not in status_map})

    lead_values = [r["lead_time_days"] for r in analysed]
    # Actief aandeel per issue, dan de mediaan — niet mediaan/mediaan, want dat
    # deelt twee verschillende issues door elkaar.
    active_share = [r["per_category"]["In Progress"] / r["lead_time_days"] * 100
                    for r in analysed if r["lead_time_days"] > 0]
    throughput = [float(s["n_completed"]) for s in sprint_rows]

    return {
        "generated": now.isoformat(timespec="seconds"),
        "window": window,
        "counts": {
            "fetched": len(records),
            "resolved_in_window": len(in_window),
            "analysed": len(analysed),
            "excluded_backfilled": len(excluded_backfill),
            "in_flight_wip": len(in_flight),
            "resolved_outside_sprints": outside,
        },
        "lead_time": _stats(lead_values),
        "lead_time_histogram": [{"from": round(a, 1), "to": round(b, 1),
                                 "n": n} for a, b, n in _histogram(lead_values)],
        "lead_time_by_cohort": {
            "bulk_created": _stats([r["lead_time_days"] for r in analysed
                                    if r["bulk_created"]]),
            "individually_created": _stats([r["lead_time_days"] for r in analysed
                                            if not r["bulk_created"]]),
        },
        "bulk_creation": bulk,
        "throughput": {**_stats(throughput), "total": int(sum(throughput))},
        "active_share_pct": _stats(active_share),
        "categories": categories,
        "statuses": dict(sorted(statuses.items(),
                                key=lambda kv: (-(kv[1]["total"] or 0),))),
        "sprints": sprint_rows,
        "trends": trends,
        "unknown_statuses": unknown,
        "in_flight_by_category": dict(Counter(
            category_of(r["status"]) for r in in_flight)),
        "_records": records,
    }


# ── rapport ──────────────────────────────────────────────────────────────────


def _n(value, suffix: str = "") -> str:
    return "—" if value is None else f"{value}{suffix}"


def _stat_rows(mapping: dict, keys) -> list[list]:
    return [[k, mapping[k]["n"], _n(mapping[k]["median"]), _n(mapping[k]["mean"]),
             _n(mapping[k]["p85"])] for k in keys if k in mapping]


def render_flow_md(report: dict, project: str) -> str:
    w = report["window"]
    c = report["counts"]
    cats = report["categories"]
    L: list[str] = []

    L.append(f"# Flow-analyse {project} — doorlooptijd per statuscategorie\n")
    L.append(f"_Extractie {report['generated']} · venster "
             f"**{w['start'][:10]} t/m {w['end'][:10]}** · "
             f"{c['analysed']} geanalyseerde issues_\n")

    # §0 ─────────────────────────────────────────────────────────────────────
    L.append("## 0. De kern\n")
    lt = report["lead_time"]
    tp = report["throughput"]
    act = report["active_share_pct"]
    L.append(f"Een issue in **{project}** doet er typisch **{_n(lt['median'])} "
             f"werkdagen** over van aanmaak tot eindstatus (mediaan; p85 "
             f"{_n(lt['p85'])}). Het team rondt daarbij **{_n(tp['median'])} "
             f"issues per sprint** af ({tp['total']} in het hele venster). Die "
             f"doorlooptijd valt uiteen in:\n")
    for cat in ("To Do", "In Progress"):
        st = cats.get(cat) or {}
        L.append(f"- **{cat}** — mediaan {_n(st.get('median'))} werkdagen "
                 f"(gemiddeld {_n(st.get('mean'))}, p85 {_n(st.get('p85'))})")
    L.append("")
    if act["median"] is not None:
        L.append(f"Het **actieve aandeel** — de tijd in een In Progress-status "
                 f"gedeeld door de doorlooptijd — is **{_n(act['median'], '%')}** "
                 f"(mediaan per issue). De rest staat stil in de backlog. Let op "
                 f"de naam: dit is niet de flow-efficiëntie uit de waardestroom, "
                 f"want een issue dat een weekend lang in 'Test' staat telt hier "
                 f"als actief.\n")
    bulk = report["bulk_creation"]
    if bulk["moments"]:
        coh = report["lead_time_by_cohort"]
        L.append(f"⚠️ **{bulk['n_bulk_created']} van de {bulk['n_total']} "
                 f"opgehaalde issues ({_n(bulk['pct'], '%')}) zijn in bulk "
                 f"aangemaakt** — zie §1. Hun klok begint bij die import, niet "
                 f"bij het moment waarop het werk gevraagd werd, en dat blaast "
                 f"hun To Do-tijd op. Gesplitst: mediaan "
                 f"**{_n(coh['bulk_created']['median'])}** werkdagen voor de "
                 f"bulk-issues (n={coh['bulk_created']['n']}) tegenover "
                 f"**{_n(coh['individually_created']['median'])}** voor los "
                 f"aangemaakte issues (n={coh['individually_created']['n']}). "
                 f"De tweede is de eerlijkere maat voor het proces.\n")
    tr = report["trends"].get("lead_time")
    if tr:
        L.append(f"Over {tr['n_sprints']} sprints is de doorlooptijd "
                 f"**{tr['direction']}** ({tr['slope_days_per_sprint']:+} "
                 f"werkdag per sprint).\n")

    # §1 ─────────────────────────────────────────────────────────────────────
    L.append("## 1. Verantwoording — wat is gemeten\n")
    L.append("Alle tijden komen uit de **changelog** van Jira: elke "
             "statusovergang draagt een tijdstempel, en het verblijf tussen "
             "twee overgangen is de tijd in die status. Statussen worden aan "
             "**To Do / In Progress / Done** toegewezen via Jira's eigen "
             "`statusCategory` uit de workflow van dit project — niet via een "
             "vaste lijst statusnamen.\n")
    L.append("Alles is in **werkdagen**: een issue dat vrijdagmiddag blijft "
             "liggen en maandagochtend verdergaat heeft niet drie dagen "
             "gewacht. Weekenden tellen niet mee, en **Nederlandse landelijke "
             "feestdagen** ook niet — Tweede Paasdag, Koningsdag, Hemelvaart, "
             "Tweede Pinksterdag, Kerst en Nieuwjaar. Goede Vrijdag telt wél "
             "als werkdag, en Bevrijdingsdag alleen in lustrumjaren.\n")
    L.extend(_md_table(
        ["Venster", "Waarde"],
        [["Aangevraagd (ruw)", f"{w['raw_start'][:10]} t/m {w['raw_end'][:10]} "
                               f"({w['months']} maanden)"],
         ["Gebruikt (gesnapt op sprintgrenzen)",
          f"{w['start'][:10]} t/m {w['end'][:10]}"],
         ["Sprints meegenomen", w["sprints_kept"]],
         ["Sprints afgevallen (deels buiten venster of nog open)",
          w["sprints_dropped"]],
         ["Snapping", "aan" if w["snapped"] else f"uit — {w['snap_note']}"]]))
    L.append("")
    L.extend(_md_table(
        ["Issues", "Aantal"],
        [["Opgehaald", c["fetched"]],
         ["Afgerond binnen het venster", c["resolved_in_window"]],
         ["Geanalyseerd", c["analysed"]],
         ["Uitgesloten — statussen achteraf bijgewerkt (< 1 u)",
          c["excluded_backfilled"]],
         ["Nog onderhanden (WIP, niet in de gemiddelden)", c["in_flight_wip"]],
         ["Afgerond buiten elke sprintperiode", c["resolved_outside_sprints"]]]))
    L.append("")
    if report["in_flight_by_category"]:
        wip = ", ".join(f"{k}: {v}" for k, v in
                        sorted(report["in_flight_by_category"].items()))
        L.append(f"**Onderhanden werk nu** — {wip}. Deze issues hebben nog geen "
                 f"doorlooptijd en tellen daarom niet mee in de gemiddelden; "
                 f"de verdeling laat wel zien waar het werk zich ophoopt.\n")
    if report["unknown_statuses"]:
        L.append(f"⚠️ Statussen uit de changelog die niet in de huidige "
                 f"workflow van {project} voorkomen (hernoemd of verwijderd) en "
                 f"daarom als *{UNKNOWN_CATEGORY}* zijn geteld: "
                 f"{', '.join(report['unknown_statuses'])}.\n")
    if bulk["moments"]:
        L.append("**Bulk aangemaakte issues.** Deze momenten leverden elk "
                 f"{BULK_CREATE_MIN} of meer issues met dezelfde aanmaakminuut "
                 "op — het patroon van een backlog-import:\n")
        L.extend(_md_table(["Aanmaakmoment", "Issues"],
                           [[m["timestamp"].replace("T", " "), m["issues"]]
                            for m in bulk["moments"]]))
        L.append("")
        L.append("Voor deze issues meet de To Do-tijd hoe lang geleden de "
                 "backlog is ingeladen, niet hoe lang iemand op het werk heeft "
                 "gewacht. Ze staan in de cijfers hieronder, maar §2 splitst de "
                 "doorlooptijd apart uit zodat het effect zichtbaar is.\n")

    # §2 ─────────────────────────────────────────────────────────────────────
    L.append("## 2. Doorlooptijd en categorieën\n")
    L.append("_Werkdagen per issue. De mediaan is het typische geval — de helft "
             "van de issues zit eronder, de helft erboven — en p85 de staart "
             "waar de planning op stukloopt._\n")
    L.extend(_md_table(["Categorie", "n", "mediaan", "gemiddeld", "p85"],
                       _stat_rows(cats, ("To Do", "In Progress",
                                         UNKNOWN_CATEGORY))))
    L.append("")
    L.extend(_md_table(["Doorlooptijd totaal", "n", "mediaan", "p85"],
                       [["aanmaak → eindstatus", lt["n"], _n(lt["median"]),
                         _n(lt["p85"])]]))
    L.append("")
    L.append("De categorie *Done* staat hier niet: zodra een issue zijn "
             "eindstatus bereikt stopt de meting, dus een verblijfsduur in Done "
             "bestaat niet. Wat de Done-band in een cumulative flow diagram wél "
             "zegt, is hoeveel werk eruit komt — de doorvoer:\n")
    L.extend(_md_table(
        ["Afgerond werk", "Waarde"],
        [["Doorvoer per sprint (mediaan)", _n(tp["median"])],
         ["Doorvoer totaal in het venster", tp["total"]],
         ["Actief aandeel van de doorlooptijd (mediaan per issue)",
          _n(act["median"], "%")]]))
    L.append("")

    if bulk["moments"]:
        coh = report["lead_time_by_cohort"]
        L.append("### Doorlooptijd per cohort\n")
        L.extend(_md_table(
            ["Cohort", "n", "mediaan", "gemiddeld", "p85"],
            [[label, s["n"], _n(s["median"]), _n(s["mean"]), _n(s["p85"])]
             for label, s in (("In bulk aangemaakt (import)",
                               coh["bulk_created"]),
                              ("Los aangemaakt", coh["individually_created"]))]))
        L.append("")
        L.append("_Het tweede cohort is de eerlijkere maat voor het proces; het "
                 "eerste meet mede hoe lang de backlog al bestond._\n")

    hist = report["lead_time_histogram"]
    if hist:
        L.append("### Verdeling van de doorlooptijd\n")
        top = max((b["n"] for b in hist), default=1) or 1
        med = lt["median"]
        for b in hist:
            marker = ("  ← mediaan" if med is not None
                      and b["from"] <= med < b["to"] else "")
            bar = "█" * max(1, round(b["n"] / top * 24)) if b["n"] else ""
            L.append(f"    {b['from']:>5.0f}–{b['to']:<5.0f}d  {bar:<24} "
                     f"{b['n']:>3}{marker}")
        L.append("")
        L.append("_Eén kengetal verbergt of dit één piek is of twee. Twee "
                 "duidelijke groepen betekent twee soorten werk — dan is 'de' "
                 "typische doorlooptijd een gemiddelde van twee processen die "
                 "los van elkaar bekeken willen worden._\n")

    # §3 ─────────────────────────────────────────────────────────────────────
    L.append("## 3. Drill-down — welke statussen kosten de tijd\n")
    for cat in (*CATEGORIES, UNKNOWN_CATEGORY):
        names = [n for n, s in report["statuses"].items() if s["category"] == cat]
        if not names:
            continue
        L.append(f"### {cat}\n")
        L.extend(_md_table(
            ["Status", "n met verblijf", "mediaan", "gemiddeld", "p85",
             "% van categorie", "× eindstatus"],
            [[n, report["statuses"][n]["n"], _n(report["statuses"][n]["median"]),
              _n(report["statuses"][n]["mean"]), _n(report["statuses"][n]["p85"]),
              _n(report["statuses"][n]["share_of_category_pct"], "%"),
              report["statuses"][n]["times_terminal"]] for n in names]))
        L.append("")

    # §4 ─────────────────────────────────────────────────────────────────────
    L.append("## 4. Per sprint — drill-down en trend\n")
    sprints = report["sprints"]
    if not sprints:
        L.append("_Geen afgeronde sprints in het venster gevonden._\n")
    else:
        L.append("_Een issue telt bij de sprint waarin het is afgerond; "
                 "**doorvoer** is dus het aantal issues in die kolom. "
                 "'Spillover' = issues die tijdens hun leven van sprint zijn "
                 "gewisseld._\n")
        L.extend(_md_table(
            ["Sprint", "start", "eind", "doorvoer", "doorloop (med.)", "To Do",
             "In Progress", "spillover"],
            [[s["name"], s["start"], s["end"], s["n_completed"],
              _n(s["lead_time"]["median"]),
              _n(s["per_category"]["To Do"]["median"]),
              _n(s["per_category"]["In Progress"]["median"]),
              f"{s['n_spilled']} ({_n(s['spilled_pct'], '%')})"]
             for s in sprints]))
        L.append("")
        L.append("### Trend over de sprints\n")
        rows = []
        series_defs = (("Doorlooptijd", "lead_time", "werkdagen"),
                       ("To Do", "To Do", "werkdagen"),
                       ("In Progress", "In Progress", "werkdagen"),
                       ("Doorvoer", "throughput", "issues"))
        for label, key, unit in series_defs:
            if key == "throughput":
                series = [float(s["n_completed"]) for s in sprints]
            elif key == "lead_time":
                series = [s["lead_time"]["median"] for s in sprints]
            else:
                series = [s["per_category"][key]["median"] for s in sprints]
            t = report["trends"].get(key)
            rows.append([label, _sparkline(series),
                         t["direction"] if t else "—",
                         f"{t['slope_days_per_sprint']:+} {unit}" if t else "—"])
        L.extend(_md_table(
            ["Reeks", f"verloop ({len(sprints)} sprints)", "richting",
             "per sprint"], rows))
        L.append("")
        L.append("_De sparkline schaalt per rij tussen het eigen minimum en "
                 "maximum; hij toont de vórm van het verloop, niet het niveau. "
                 "De helling komt uit een kleinste-kwadratenfit over de "
                 "sprintindex. Een dalende doorlooptijd bij stijgende doorvoer "
                 "is de gewenste richting; stijgen ze samen, dan groeit het "
                 "onderhanden werk._\n")

    # §5 ─────────────────────────────────────────────────────────────────────
    L.append("## 5. Beperkingen\n")
    L.append("- **Tijd in de eindstatus telt niet mee.** Zodra een issue in "
             "zijn laatste status staat, stopt de meting: 'al 200 dagen "
             "Closed' is archieftijd, geen doorlooptijd. Daarom staat *Done* "
             "niet als verblijfsduur in §2, maar als doorvoer.")
    L.append("- **Bulk aangemaakte issues vertekenen de doorlooptijd.** Bij een "
             "backlog-import begint de klok bij de import; §2 splitst daarom "
             "per cohort. Detectie gaat op gelijke aanmaakminuut, dus een "
             "import die over meerdere minuten uitgesmeerd is wordt maar "
             "gedeeltelijk herkend.")
    L.append("- **Feestdagen zijn de landelijke Nederlandse.** Regionale of "
             "cao-specifieke vrije dagen, collectieve sluitingen en verlof "
             "zitten er niet in; Goede Vrijdag telt als werkdag en "
             "Bevrijdingsdag alleen in lustrumjaren.")
    L.append("- **Backfill.** Issues waarvan álle statusovergangen binnen een "
             "uur vielen zijn achteraf geadministreerd; hun tijdstempels "
             "beschrijven de administratie, niet het werk. Ze zijn geteld maar "
             "uitgesloten.")
    L.append("- **Hernoemde statussen.** De changelog bewaart de statusnaam "
             "zoals die tóen was; is een status later hernoemd, dan valt de "
             "oude naam buiten de workflow-kaart (zie §1).")
    L.append("- **Sprinttoewijzing.** Een issue hoort bij de sprint waarin het "
             "is afgerond, niet bij de sprint waarin het gepland stond. "
             "Sprintperioden zijn aaneengesloten gemaakt zodat er geen issues "
             "in gaten tussen sprints verdwijnen.")
    L.append("- **Onderhanden werk ontbreekt in de gemiddelden.** Loopt het "
             "werk juist nú vast, dan zie je dat pas als het afrondt; de "
             "WIP-verdeling in §1 is de tegenhanger.")
    L.append("- **Werkdagen, geen uren.** Er is geen urenregistratie; "
             "'In Progress' betekent dat het issue die status droeg, niet dat "
             "er die dagen fulltime aan gewerkt is.\n")
    return "\n".join(L)


# ── artefacten ───────────────────────────────────────────────────────────────


def write_flow_outputs(report: dict, project: str, out_dir: Path) -> list[Path]:
    out_dir = out_dir / re.sub(r"[^A-Za-z0-9_-]", "_", project)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"jira_flow_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    paths = []

    records = report["_records"]
    export = {k: v for k, v in report.items() if not k.startswith("_")}
    p = out_dir / f"{stem}.json"
    p.write_text(json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8")
    paths.append(p)

    p = out_dir / f"{stem}_report.md"
    p.write_text(render_flow_md(report, project), encoding="utf-8")
    paths.append(p)

    paths.append(_write_csv(
        out_dir / f"{stem}_issues.csv",
        ["key", "issuetype", "status", "created", "resolved", "sprint",
         "lead_time_days", *(f"days_{c}" for c in (*CATEGORIES, UNKNOWN_CATEGORY)),
         "in_flight", "backfilled", "bulk_created", "sprint_changes"],
        ([r["key"], r["issuetype"], r["status"], r["created"], r["resolved"] or "",
          r.get("sprint") or "", r["lead_time_days"],
          *(r["per_category"][c] for c in (*CATEGORIES, UNKNOWN_CATEGORY)),
          r["in_flight"], r["backfilled"], r["bulk_created"], r["sprint_changes"]]
         for r in records)))

    paths.append(_write_csv(
        out_dir / f"{stem}_statuses.csv",
        ["status", "category", "n", "median_days", "mean_days", "p85_days",
         "total_days", "share_of_category_pct", "times_terminal"],
        ([name, s["category"], s["n"], s["median"], s["mean"], s["p85"],
          s["total"], s["share_of_category_pct"], s["times_terminal"]]
         for name, s in report["statuses"].items())))

    paths.append(_write_csv(
        out_dir / f"{stem}_sprints.csv",
        ["sprint", "start", "end", "throughput", "lead_time_median",
         *(f"median_{c}" for c in CATEGORIES), "n_spilled", "spilled_pct"],
        ([s["name"], s["start"], s["end"], s["n_completed"],
          s["lead_time"]["median"],
          *(s["per_category"][c]["median"] for c in CATEGORIES),
          s["n_spilled"], s["spilled_pct"]]
         for s in report["sprints"])))

    return paths


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Flow-analyse van een Jira-project uit de changelog: "
                    "doorlooptijd per statuscategorie, per status en per sprint.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--jira-url", metavar="URL",
                     help="Jira-project-URL, bv. "
                          "https://jira.vitens.lan/jira/browse/MOD")
    src.add_argument("--project", metavar="KEY", help="Projectsleutel, bv. MOD")
    ap.add_argument("--months", type=int, default=None,
                    help="Venster in maanden (default 6; interactief wordt 12 "
                         "aangeboden)")
    ap.add_argument("--issue-types", default=None, metavar="A,B",
                    help="Alleen deze issuetypes, bv. 'Story,Bug' "
                         "(default: alles behalve subtaken)")
    ap.add_argument("--include-subtasks", action="store_true",
                    help="Neem subtaken mee (default: uit)")
    ap.add_argument("--no-sprint-snap", action="store_true",
                    help="Snap het venster NIET naar sprintgrenzen — reken op "
                         "het kalendervenster, inclusief deelsprints")
    ap.add_argument("--refresh", action="store_true",
                    help="Negeer de cache en haal live op (overschrijft de cache)")
    ap.add_argument("--flow-cache", default=None, metavar="PATH",
                    help="Cachebestand (default: output/<PROJECT>/"
                         "jira_flow_cache_<PROJECT>.json)")
    ap.add_argument("--creds", default=None,
                    help="Pad naar creds.yaml (default: zoekt in cwd, naast dit "
                         "script, en in fo_doc_gen)")
    ap.add_argument("--out-dir", default="output")
    args = ap.parse_args()

    project = _project_key(args.jira_url or args.project)
    months = args.months if args.months else _ask_months()

    creds_path = Path(args.creds) if args.creds else _find_creds()
    if not creds_path:
        raise SystemExit("Geen creds.yaml gevonden — geef --creds op. Verwacht "
                         "jira.{base_url,api_token}.")
    print(f"  creds: {creds_path}")
    jira = JiraClient(_load_creds(creds_path))
    out_dir = Path(args.out_dir)

    now = datetime.now()
    raw_start, raw_end = _months_ago(now, months), now

    print(f"→ Workflow van {project} …")
    status_map = build_status_map(jira, project)
    print(f"  {len(status_map)} statussen, "
          f"{Counter(status_map.values())}")

    sprint_field = find_sprint_field(jira)
    if not sprint_field:
        _warn("geen Sprint-veld gevonden — geen sprintanalyse, kalendervenster")

    print(f"→ Issues van {project} ({months} maanden) …")
    jql = build_jql(project, raw_start, args.issue_types, args.include_subtasks)
    issues = fetch_issues(jira, project, jql, sprint_field, out_dir=out_dir,
                          months=months, refresh=args.refresh,
                          cache_path=Path(args.flow_cache) if args.flow_cache
                          else None)
    if not issues:
        raise SystemExit(f"Geen issues gevonden voor {project} in dit venster.")
    print(f"  {len(issues)} issues")

    sprints = build_sprint_calendar(issues, sprint_field) if sprint_field else []
    snap = bool(sprints) and not args.no_sprint_snap
    if snap:
        kept, start, end = snap_window(sprints, raw_start, raw_end)
        if not kept:
            _warn("geen enkele sprint valt volledig binnen het venster — "
                  "terug naar het kalendervenster")
            snap, kept, start, end = False, [], raw_start, raw_end
        snap_note = ""
    else:
        kept, start, end = [], raw_start, raw_end
        snap_note = ("--no-sprint-snap" if args.no_sprint_snap
                     else "geen sprints gevonden")

    periods = sprint_periods(kept, end) if kept else (
        sprint_periods([s for s in sprints if s["start"] < end and s["end"] > start],
                       end) if sprints else [])
    window = {
        "months": months,
        "raw_start": raw_start.isoformat(timespec="seconds"),
        "raw_end": raw_end.isoformat(timespec="seconds"),
        "start": start.isoformat(timespec="seconds"),
        "end": end.isoformat(timespec="seconds"),
        "snapped": snap,
        "snap_note": snap_note,
        "sprints_kept": len(kept),
        "sprints_dropped": len(sprints) - len(kept),
    }
    if snap:
        print(f"  venster gesnapt op sprintgrenzen: {start.date()} t/m "
              f"{end.date()} — {len(kept)} sprints, "
              f"{len(sprints) - len(kept)} afgevallen")

    print("→ Analyse …")
    report = build_flow(issues, status_map, periods, window, now)

    paths = write_flow_outputs(report, project, out_dir)
    print("\n✅ Klaar:")
    for p in paths:
        print(f"   {p}")
    lt = report["lead_time"]
    cats = report["categories"]
    print(f"\n   {report['counts']['analysed']} issues · doorlooptijd mediaan "
          f"{_n(lt['median'])} werkdagen · doorvoer "
          f"{_n(report['throughput']['median'])}/sprint · "
          + " · ".join(f"{c} {_n((cats.get(c) or {}).get('median'))}"
                       for c in ("To Do", "In Progress")))
    if report["bulk_creation"]["moments"]:
        _warn(f"{report['bulk_creation']['n_bulk_created']} issues in bulk "
              f"aangemaakt — zie de cohortsplitsing in §2 van het rapport")


if __name__ == "__main__":
    main()
