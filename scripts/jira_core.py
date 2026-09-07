#!/usr/bin/env python3
"""Gedeelde primitieven voor de Jira-analyses.

Deze module bevat wat `testauto_businesscase.py` (één story + één TestRail-run)
en `jira_flow_analysis.py` (flow van een heel project) allebei nodig hebben:
het vinden en lezen van creds, de Jira Data Center-client, het parsen van
changelog-statusovergangen, werkdagenrekenwerk en de uitvoerhelpers.

Niets hierin doet netwerkverkeer bij import; de client wordt expliciet
geconstrueerd.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

import requests
import urllib3
import yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_HERE = Path(__file__).resolve().parent

# Waar creds.yaml gezocht wordt als --creds niet is opgegeven. De laatste
# entry deelt het secret met fo_doc_gen zodat het niet gedupliceerd hoeft.
_CREDS_CANDIDATES = (
    Path.cwd() / "creds.yaml",
    _HERE / "creds.yaml",
    _HERE.parent / "creds.yaml",
    Path.home() / "github_repos" / "fo_doc_gen" / "creds.yaml",
)

WORKDAY_HOURS = 8.0

# ≈1 h: een issue waarvan álle statusovergangen binnen dit venster vallen is
# achteraf bijgewerkt (bulkmigratie, administratie na afloop) — de tijdstempels
# beschrijven dan de administratie, niet het werk.
BACKFILL_THRESHOLD_D = 0.04


# ── creds ────────────────────────────────────────────────────────────────────


def _find_creds() -> Path | None:
    for cand in _CREDS_CANDIDATES:
        if cand.exists():
            return cand
    return None


def _load_creds(path: Path | None) -> dict:
    if path and path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


# ── Jira-client ──────────────────────────────────────────────────────────────


class JiraClient:
    """Minimal Jira Data Center client (Bearer PAT, self-signed cert)."""

    def __init__(self, creds: dict):
        j = creds.get("jira") or {}
        self.headers = {"Authorization": f"Bearer {j.get('api_token', '')}"}
        self.base = self._resolve_base(j.get("base_url", "https://jira.vitens.lan"))

    def _resolve_base(self, configured: str) -> str:
        # creds.yaml carries the host without the servlet context path; the
        # working REST root on this instance is https://<host>/jira.
        root = configured.rstrip("/")
        for cand in (root, f"{root}/jira"):
            try:
                r = requests.get(f"{cand}/rest/api/2/serverInfo",
                                 headers=self.headers, verify=False, timeout=15)
                if r.status_code == 200:
                    return cand
            except requests.RequestException:
                continue
        return root

    def _get(self, path: str, params: dict | None = None, timeout: int = 60):
        r = requests.get(f"{self.base}{path}", params=params or None,
                         headers=self.headers, verify=False, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def issue(self, key: str, expand: str = "changelog") -> dict:
        return self._get(f"/rest/api/2/issue/{key}",
                         {"expand": expand} if expand else None)

    def search(self, jql: str, fields: str, max_results: int = 100,
               expand: str = "") -> list[dict]:
        """Eén pagina. Voor volledige resultaatsets: search_all()."""
        params = {"jql": jql, "fields": fields, "maxResults": max_results}
        if expand:
            params["expand"] = expand
        return self._get("/rest/api/2/search", params).get("issues", [])

    def search_all(self, jql: str, fields: str, expand: str = "",
                   page_size: int = 100, cap: int = 0,
                   progress: bool = False) -> list[dict]:
        """Alle issues van een JQL, via startAt-paginering.

        `search()` doet één request en verliest stil alles boven maxResults —
        voor een projectbrede analyse is dat het verschil tussen "de eerste 100
        issues" en "het project". `cap` (0 = geen cap) begrenst het totaal.
        """
        out: list[dict] = []
        start, total = 0, None
        while True:
            params = {"jql": jql, "fields": fields, "maxResults": page_size,
                      "startAt": start}
            if expand:
                params["expand"] = expand
            page = self._get("/rest/api/2/search", params, timeout=120)
            issues = page.get("issues") or []
            total = page.get("total", len(issues))
            out.extend(issues)
            if progress:
                print(f"    … {len(out)}/{total} issues", flush=True)
            start += len(issues)
            if not issues or start >= total or (cap and len(out) >= cap):
                break
        return out[:cap] if cap else out

    def project_statuses(self, project_key: str) -> list[dict]:
        """Per issuetype de toegestane statussen, mét statusCategory."""
        return self._get(f"/rest/api/2/project/{project_key}/statuses")

    def fields(self) -> list[dict]:
        """Alle velddefinities — nodig om het Sprint-customfield te vinden."""
        return self._get("/rest/api/2/field")


# ── tijd ─────────────────────────────────────────────────────────────────────


def _dt(value) -> datetime:
    """Jira ISO string or TestRail unix timestamp → naive local datetime."""
    if isinstance(value, str):
        return datetime.fromisoformat(value).replace(tzinfo=None)
    return datetime.fromtimestamp(value)


def _workdays(start: datetime, end: datetime) -> float:
    """Werkdagen (ma–vr) tussen twee momenten, met fractie van de laatste dag.

    Let op: de startdag telt hier ALTIJD als hele dag — dit is een
    fase-lengte in dagen, geen duur. Voor een echte duur (waarin tien minuten
    ook tien minuten zijn): `_workdays_elapsed`.
    """
    if end <= start:
        return 0.0
    days, cur = 0.0, start.date()
    while cur < end.date():
        if cur.weekday() < 5:
            days += 1
        cur += timedelta(days=1)
    if end.date().weekday() < 5:
        days += min((end - datetime.combine(end.date(), datetime.min.time()))
                    .total_seconds() / (WORKDAY_HOURS * 3600), 1.0)
    return round(days, 1)


def _count_weekdays(first: date, last: date) -> int:
    """Aantal ma–vr in [first, last), zonder per dag te itereren."""
    if last <= first:
        return 0
    weeks, rem = divmod((last - first).days, 7)
    return weeks * 5 + sum(1 for i in range(rem)
                           if (first + timedelta(days=i)).weekday() < 5)


def _workdays_elapsed(start: datetime, end: datetime) -> float:
    """Verstreken tijd in werkdagen (ma–vr): weekenden tellen niet mee.

    Anders dan `_workdays` is dit een ÉCHTE duur — een status die tien minuten
    duurde is 0,0 dagen en niet 1. Een deel van een dag telt naar rato van het
    etmaal: er is nergens urenregistratie, dus een kantoorurenvenster (09–17)
    zou een precisie suggereren die de data niet heeft.
    """
    if end <= start:
        return 0.0
    s_day, e_day = start.date(), end.date()
    if s_day == e_day:
        return ((end - start).total_seconds() / 86400
                if start.weekday() < 5 else 0.0)
    total = 0.0
    if start.weekday() < 5:  # restant van de startdag
        total += (datetime.combine(s_day + timedelta(days=1), time.min)
                  - start).total_seconds() / 86400
    total += _count_weekdays(s_day + timedelta(days=1), e_day)
    if end.weekday() < 5:  # aanloop van de einddag
        total += (end - datetime.combine(e_day, time.min)).total_seconds() / 86400
    return total


# ── changelog ────────────────────────────────────────────────────────────────


def _status_transitions(issue: dict) -> list[dict]:
    out = []
    for hist in (issue.get("changelog") or {}).get("histories") or []:
        for item in hist.get("items") or []:
            if item.get("field") == "status":
                out.append({
                    "ts": hist["created"],
                    "author": (hist.get("author") or {}).get("displayName", ""),
                    "from": item.get("fromString"),
                    "to": item.get("toString"),
                })
    out.sort(key=lambda t: t["ts"])
    return out


def _status_spans(issue: dict, transitions: list[dict]) -> list[tuple]:
    """(status, start, eind) per aaneengesloten verblijf in één status.

    De gedeelde kern onder `_time_in_status` en zijn werkdagenvariant: één
    plek waar de aanname leeft dat een issue vanaf `created` in de
    from-status van de eerste overgang zat, en tot resolutie (of laatste
    wijziging) in de laatste to-status.
    """
    created = _dt(issue["fields"]["created"])
    end = _dt(issue["fields"].get("resolutiondate")
              or issue["fields"].get("updated") or issue["fields"]["created"])
    spans, cursor = [], created
    status = (transitions[0]["from"] if transitions
              else issue["fields"]["status"]["name"])
    for tr in transitions:
        ts = _dt(tr["ts"])
        spans.append((status or "?", cursor, ts))
        cursor, status = ts, tr["to"]
    if end > cursor:
        spans.append((status or "?", cursor, end))
    return spans


def _time_in_status(issue: dict, transitions: list[dict]) -> dict[str, float]:
    """Kalenderdagen per status, van created tot resolutie (of laatste update)."""
    days: dict[str, float] = defaultdict(float)
    for status, start, end in _status_spans(issue, transitions):
        days[status] += (end - start).total_seconds() / 86400
    return {k: round(v, 1) for k, v in days.items()}


def _time_in_status_workdays(issue: dict,
                             transitions: list[dict]) -> dict[str, float]:
    """Idem, maar in WERKDAGEN (ma–vr) — de eenheid van de flow-analyse.

    Weekenden waarin niets kón gebeuren tellen anders mee als doorlooptijd en
    maken elke status ~40% duurder dan hij is.
    """
    days: dict[str, float] = defaultdict(float)
    for status, start, end in _status_spans(issue, transitions):
        days[status] += _workdays_elapsed(start, end)
    return {k: round(v, 1) for k, v in days.items()}


def _is_backfilled(transitions: list[dict]) -> bool:
    """Alle statusovergangen binnen ~1 uur ⇒ achteraf-administratie."""
    return bool(transitions) and (
        (_dt(transitions[-1]["ts"]) - _dt(transitions[0]["ts"])).total_seconds()
        / 86400 < BACKFILL_THRESHOLD_D)


# ── uitvoer ──────────────────────────────────────────────────────────────────


def _md_table(headers: list, rows) -> list[str]:
    """Markdown pipe-tabel: kopregel + scheidingsregel (breedte volgt uit de
    headers) + één regel per rij. Vervangt het handmatige `|---|`-ceremonieel."""
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return out


def _write_csv(path: Path, header: list, rows) -> Path:
    """Eén CSV met UTF-8 + `newline=""` (de invarianten die anders per blok
    herhaald werden)."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def _warn(msg: str) -> None:
    print(f"  ⚠️ {msg}", file=sys.stderr)
