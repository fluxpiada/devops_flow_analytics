#!/usr/bin/env python3
"""Business-case data extraction: manual vs automated (regression) testing.

Standalone — NOT wired into the FO pipeline. Read-only against Jira Data Center
and TestRail; produces a JSON extract, CSV tables, a cross-system event timeline
and a written Markdown evaluation with an assumption-banded ROI model.

Usage:
    uv run python scripts/testauto_businesscase.py --jira S34-2907 --run 26442
    ... [--suite 496] [--project 58] [--creds creds.yaml] [--out-dir output/]
    ... [--max-runs 0] [--skip-corpus]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
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

# Gaps between a tester's consecutive result submissions larger than this are
# treated as a break/new session, not hands-on time on one test.
SESSION_GAP_CAP_S = 60 * 60

_W_CODE_RE = re.compile(r"\bW\d{3}\b")
_REGRESSION_TITLE_RE = re.compile(r"regress|W\d{3}\s*->\s*W\d{3}", re.IGNORECASE)
_JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


def _run_jira_keys(run: dict) -> tuple[list[str], list[str]]:
    """Jira keys a TestRail run declares, from `refs` (authoritative) and `name`."""
    refs = _JIRA_KEY_RE.findall(run.get("refs") or "")
    name = [k for k in _JIRA_KEY_RE.findall(run.get("name") or "") if k not in refs]
    return refs, name


def resolve_story_key(run: dict, requested: str | None,
                      allow_unlinked: bool = False) -> str:
    """Resolve --jira against the run's own references; abort on a mismatch.

    The analysis splices ONE story's Jira lifecycle onto ONE run's execution
    data. If the two are unrelated the output is still internally consistent,
    and therefore silently wrong — so the link is established from the data
    rather than assumed from the CLI arguments.
    """
    refs, name = _run_jira_keys(run)
    declared = refs + name
    run_id = run.get("id")

    if not requested:
        if not declared:
            raise SystemExit(
                f"TestRail-run {run_id} verwijst naar geen enkele Jira-issue "
                f"(refs en naam zijn leeg) — geef expliciet --jira KEY op, of "
                f"--allow-unlinked om zonder Jira-koppeling door te gaan.")
        chosen = declared[0]
        where = "refs" if refs else "runnaam"
        if len(declared) > 1:
            print(f"  ℹ run {run_id} verwijst naar {', '.join(declared)} — "
                  f"gekozen: {chosen} (eerste uit {where}); override met --jira")
        else:
            print(f"  ✓ koppeling uit {where}: run {run_id} → {chosen}")
        return chosen

    if requested in declared:
        print(f"  ✓ koppeling bevestigd: run {run_id} → {requested}")
        return requested

    msg = (f"TestRail-run {run_id} verwijst niet naar {requested}. "
           f"De run noemt: {', '.join(declared) or '(niets)'}.")
    if allow_unlinked:
        print(f"  ⚠️ {msg} — doorgegaan op eigen risico (--allow-unlinked); de "
              f"waardestroom koppelt dan niet-gerelateerde data.", file=sys.stderr)
        return requested
    raise SystemExit(
        f"{msg}\nDe analyse plakt de Jira-levenscyclus van één story op de "
        f"uitvoeringsdata van één run; zonder koppeling is het resultaat wel "
        f"consistent maar onjuist.\nGebruik --jira "
        f"{declared[0] if declared else '<KEY>'}, of --allow-unlinked als je "
        f"zeker weet dat de koppeling klopt.")

# ── clients ──────────────────────────────────────────────────────────────────


def _find_creds() -> Path | None:
    for cand in _CREDS_CANDIDATES:
        if cand.exists():
            return cand
    return None


def _load_creds(path: Path | None) -> dict:
    if path and path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


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

    def issue(self, key: str, expand: str = "changelog") -> dict:
        r = requests.get(f"{self.base}/rest/api/2/issue/{key}",
                         params={"expand": expand} if expand else None,
                         headers=self.headers, verify=False, timeout=60)
        r.raise_for_status()
        return r.json()

    def search(self, jql: str, fields: str, max_results: int = 100,
               expand: str = "") -> list[dict]:
        params = {"jql": jql, "fields": fields, "maxResults": max_results}
        if expand:
            params["expand"] = expand
        r = requests.get(f"{self.base}/rest/api/2/search", params=params,
                         headers=self.headers, verify=False, timeout=60)
        r.raise_for_status()
        return r.json().get("issues", [])


class TestRailClient:
    """Minimal TestRail client (Basic auth). Handles both DC response shapes."""

    def __init__(self, creds: dict):
        t = creds.get("testrail") or {}
        self.base = t.get("base_url", "").rstrip("/")
        self.auth = (t.get("email", ""), t.get("api_key", ""))
        self.verify = t.get("verify_ssl", False)
        self.project_id = t.get("project_id")

    def get(self, endpoint: str, **params) -> dict | list:
        r = requests.get(f"{self.base}/index.php?/api/v2/{endpoint}",
                         auth=self.auth, verify=self.verify, timeout=90,
                         params=params or None)
        r.raise_for_status()
        return r.json()

    def get_all(self, endpoint: str, key: str, max_pages: int = 40,
                **params) -> list[dict]:
        """Offset-paginate; newer DC wraps lists as {key: [...]}, older returns bare.

        Some endpoints on this TestRail version ignore ``offset`` (notably
        get_tests) and return the same first page forever — detect a
        non-advancing page and stop, plus an absolute page cap.
        """
        out: list[dict] = []
        offset, prev_first = 0, None
        for _ in range(max_pages):
            page = self.get(endpoint, limit=250, offset=offset, **params)
            items = page.get(key, page) if isinstance(page, dict) else page
            if not isinstance(items, list) or not items:
                break
            first = items[0].get("id") if isinstance(items[0], dict) else None
            if first is not None and first == prev_first:
                break  # server ignored offset; same page again
            prev_first = first
            out.extend(items)
            if len(items) < 250:
                break
            offset += 250
        else:
            print(f"    ⚠️ {endpoint}: page cap {max_pages} hit "
                  f"({len(out)} items kept)", file=sys.stderr)
        return out


def _dt(value) -> datetime:
    """Jira ISO string or TestRail unix timestamp → naive local datetime."""
    if isinstance(value, str):
        return datetime.fromisoformat(value).replace(tzinfo=None)
    return datetime.fromtimestamp(value)


# ── A. Jira lifecycle ────────────────────────────────────────────────────────


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


def _time_in_status(issue: dict, transitions: list[dict]) -> dict[str, float]:
    """Days spent in each status, from created to resolution (or last update)."""
    created = _dt(issue["fields"]["created"])
    end = _dt(issue["fields"].get("resolutiondate")
              or issue["fields"].get("updated") or issue["fields"]["created"])
    days: dict[str, float] = defaultdict(float)
    cursor, status = created, (transitions[0]["from"] if transitions
                               else issue["fields"]["status"]["name"])
    for tr in transitions:
        ts = _dt(tr["ts"])
        days[status or "?"] += (ts - cursor).total_seconds() / 86400
        cursor, status = ts, tr["to"]
    if end > cursor:
        days[status or "?"] += (end - cursor).total_seconds() / 86400
    return {k: round(v, 1) for k, v in days.items()}


def build_jira_lifecycle(jira: JiraClient, story_key: str) -> dict:
    story = jira.issue(story_key)
    f = story["fields"]
    transitions = _status_transitions(story)

    sprint_changes = flag_changes = 0
    story_points = epic = None
    for hist in (story.get("changelog") or {}).get("histories") or []:
        for item in hist.get("items") or []:
            if item.get("field") == "Sprint":
                sprint_changes += 1
            elif item.get("field") == "Flagged" and item.get("toString"):
                flag_changes += 1
            elif item.get("field") == "Story Points":
                story_points = item.get("toString")
            elif item.get("field") == "Epic Link" and item.get("toString"):
                epic = item.get("toString")

    subtasks = []
    for sub in f.get("subtasks") or []:
        try:
            si = jira.issue(sub["key"])
        except requests.RequestException as exc:
            print(f"  ⚠️ subtask {sub['key']} fetch failed: {exc}", file=sys.stderr)
            continue
        sf = si["fields"]
        subtasks.append({
            "key": sub["key"],
            "summary": sf["summary"],
            "issuetype": sf["issuetype"]["name"],
            "assignee": (sf.get("assignee") or {}).get("displayName"),
            "created": sf["created"],
            "resolved": sf.get("resolutiondate"),
            "transitions": _status_transitions(si),
            "time_in_status_days": _time_in_status(si, _status_transitions(si)),
        })

    return {
        "key": story_key,
        "summary": f["summary"],
        "issuetype": f["issuetype"]["name"],
        "epic": epic,
        "status": f["status"]["name"],
        "created": f["created"],
        "updated": f.get("updated"),
        "resolutiondate": f.get("resolutiondate"),
        "story_points": story_points,
        "sprint_changes": sprint_changes,
        "impediment_flags": flag_changes,
        "transitions": transitions,
        "time_in_status_days": _time_in_status(story, transitions),
        "subtasks": subtasks,
        "issuelinks": [
            {
                "relation": (lnk["type"]["outward"] if lnk.get("outwardIssue")
                             else lnk["type"]["inward"]),
                "key": (lnk.get("outwardIssue") or lnk.get("inwardIssue") or {}).get("key"),
                "issuetype": ((lnk.get("outwardIssue") or lnk.get("inwardIssue") or {})
                              .get("fields", {}).get("issuetype", {}).get("name")),
            }
            for lnk in f.get("issuelinks") or []
        ],
    }


# ── B. TestRail execution ────────────────────────────────────────────────────


def _session_gap_effort(results: list[dict]) -> dict:
    """Per-tester in-session gaps between consecutive result submissions."""
    by_tester: dict[int, list[int]] = defaultdict(list)
    for r in results:
        by_tester[r["created_by"]].append(r["created_on"])
    gaps_all: list[float] = []
    per_tester = {}
    for tester, ts in by_tester.items():
        ts.sort()
        gaps = [b - a for a, b in zip(ts, ts[1:]) if 0 < b - a <= SESSION_GAP_CAP_S]
        gaps_all.extend(gaps)
        per_tester[str(tester)] = {
            "results": len(ts),
            "active_days": len({datetime.fromtimestamp(x).date() for x in ts}),
            "in_session_gaps": len(gaps),
            "median_gap_min": round(statistics.median(gaps) / 60, 1) if gaps else None,
            "net_active_hours": round(sum(gaps) / 3600, 2),
        }
    return {
        "per_tester": per_tester,
        "testers": len(by_tester),
        "pooled_median_gap_min": (round(statistics.median(gaps_all) / 60, 1)
                                  if gaps_all else None),
        "pooled_mean_gap_min": (round(statistics.mean(gaps_all) / 60, 1)
                                if gaps_all else None),
        "net_active_hours": round(sum(gaps_all) / 3600, 2),
    }


def build_run_metrics(tr: TestRailClient, jira: JiraClient, run_id: int) -> dict:
    run = tr.get(f"get_run/{run_id}")
    tests = tr.get_all(f"get_tests/{run_id}", "tests")
    results = tr.get_all(f"get_results_for_run/{run_id}", "results")
    statuses = tr.get("get_statuses")
    status_names = {s["id"]: s["name"]
                    for s in (statuses.get("statuses", statuses)
                              if isinstance(statuses, dict) else statuses)}

    per_test = Counter(r["test_id"] for r in results)
    execs = sorted(per_test.values())
    result_status = Counter(status_names.get(r["status_id"], str(r["status_id"]))
                            for r in results if r.get("status_id"))

    # First-pass rate: earliest meaningful-status result per test is 'passed'.
    first_status: dict[int, str] = {}
    for r in sorted(results, key=lambda x: x["created_on"]):
        if r.get("status_id") and r["test_id"] not in first_status:
            first_status[r["test_id"]] = status_names.get(r["status_id"], "?")
    first_pass = sum(1 for s in first_status.values() if s == "passed")

    # Per-W-code subject breakdown (a test spanning W010->W100 counts for both).
    test_codes = {t["id"]: _W_CODE_RE.findall(t.get("title") or "") for t in tests}
    w_codes: dict[str, dict] = defaultdict(lambda: {"tests": 0, "executions": 0,
                                                    "failed": 0, "defects": set()})
    for t in tests:
        for code in set(test_codes[t["id"]]):
            w_codes[code]["tests"] += 1
    for r in results:
        for code in set(test_codes.get(r["test_id"], [])):
            w_codes[code]["executions"] += 1
            if status_names.get(r.get("status_id")) == "failed":
                w_codes[code]["failed"] += 1
            for d in re.split(r"[,\s]+", r.get("defects") or ""):
                if d:
                    w_codes[code]["defects"].add(d)

    defect_keys = sorted({d for r in results
                          for d in re.split(r"[,\s]+", r.get("defects") or "") if d})
    defects = []
    if defect_keys:
        try:
            issues = jira.search(f"issuekey in ({','.join(defect_keys)})",
                                 "summary,issuetype,status,created,resolutiondate,assignee",
                                 max_results=len(defect_keys) + 5)
            for i in issues:
                fi = i["fields"]
                res_days = None
                if fi.get("resolutiondate"):
                    res_days = round((_dt(fi["resolutiondate"]) -
                                      _dt(fi["created"])).total_seconds() / 86400, 1)
                defects.append({
                    "key": i["key"],
                    "summary": fi["summary"],
                    "issuetype": fi["issuetype"]["name"].strip(),
                    "status": fi["status"]["name"],
                    "created": fi["created"],
                    "resolved": fi.get("resolutiondate"),
                    "resolution_days": res_days,
                })
        except requests.RequestException as exc:
            print(f"  ⚠️ defect lookup failed: {exc}", file=sys.stderr)
    res_times = [d["resolution_days"] for d in defects if d["resolution_days"] is not None]

    result_dates = sorted(datetime.fromtimestamp(r["created_on"]) for r in results)
    return {
        "run_id": run_id,
        "name": run.get("name"),
        "suite_id": run.get("suite_id"),
        "project_id": run.get("project_id"),
        "created_on": run["created_on"],
        "completed_on": run.get("completed_on"),
        "is_completed": run.get("is_completed"),
        "tests": len(tests),
        "results": len(results),
        "executions_per_test": {
            "mean": round(len(results) / max(len(per_test), 1), 1),
            "median": execs[len(execs) // 2] if execs else 0,
            "max": execs[-1] if execs else 0,
        },
        "result_status_spread": dict(result_status),
        "first_pass_rate": round(first_pass / max(len(first_status), 1), 2),
        "first_result": result_dates[0].isoformat() if result_dates else None,
        "last_result": result_dates[-1].isoformat() if result_dates else None,
        "execution_days": len({d.date() for d in result_dates}),
        "effort_proxy": _session_gap_effort(results),
        "w_codes": {k: {**v, "defects": sorted(v["defects"])}
                    for k, v in sorted(w_codes.items())},
        "defects": defects,
        "defect_resolution_days": {
            "count": len(defects),
            "mean": round(statistics.mean(res_times), 1) if res_times else None,
            "median": round(statistics.median(res_times), 1) if res_times else None,
        },
        "_results_raw": results,       # consumed by the timeline builder, not exported
        "_status_names": status_names,
    }


# ── C. Corpus / frequency ────────────────────────────────────────────────────


def build_corpus(tr: TestRailClient, project_id: int, suite_id: int,
                 max_runs: int = 0) -> dict:
    runs = tr.get_all(f"get_runs/{project_id}", "runs", suite_id=suite_id)
    if max_runs:
        runs = runs[:max_runs]
    print(f"  corpus: scanning {len(runs)} runs on suite {suite_id} …")

    per_run = []
    for i, run in enumerate(runs, 1):
        if i % 25 == 0:
            print(f"    … {i}/{len(runs)}")
        total = sum(run.get(k, 0) or 0 for k in
                    ("passed_count", "failed_count", "blocked_count", "retest_count",
                     "untested_count", "custom_status1_count", "custom_status2_count",
                     "custom_status3_count", "custom_status4_count",
                     "custom_status5_count", "custom_status6_count",
                     "custom_status7_count"))
        executed = total - (run.get("untested_count", 0) or 0)
        regr = regr_exec = 0
        try:
            tests = tr.get_all(f"get_tests/{run['id']}", "tests")
            total = len(tests)
            # status_id 3 = TestRail system status 'untested'; a test still on
            # it was instantiated but never run — count executions, not intent.
            executed = sum(1 for t in tests if t.get("status_id") != 3)
            for t in tests:
                if _REGRESSION_TITLE_RE.search(t.get("title") or ""):
                    regr += 1
                    if t.get("status_id") != 3:
                        regr_exec += 1
        except requests.RequestException as exc:
            print(f"    ⚠️ get_tests/{run['id']} failed ({exc}); using run counts",
                  file=sys.stderr)
        per_run.append({
            "run_id": run["id"],
            "name": run.get("name"),
            "created_on": run["created_on"],
            "year": datetime.fromtimestamp(run["created_on"]).year,
            "is_completed": run.get("is_completed"),
            "tests": total,
            "tests_executed": executed,
            "regression_tests": regr,
            "regression_executed": regr_exec,
            "is_regression": regr > 0,
            "passed": run.get("passed_count", 0),
            "failed": run.get("failed_count", 0),
        })

    by_year: dict[int, dict] = defaultdict(lambda: {
        "runs": 0, "tests": 0, "tests_executed": 0,
        "regr_runs": 0, "regr_tests": 0, "regr_executed": 0})
    for r in per_run:
        y = by_year[r["year"]]
        y["runs"] += 1
        y["tests"] += r["tests"]
        y["tests_executed"] += r["tests_executed"]
        if r["is_regression"]:
            y["regr_runs"] += 1
            y["regr_tests"] += r["regression_tests"]
            y["regr_executed"] += r["regression_executed"]

    cases = tr.get_all(f"get_cases/{project_id}", "cases", suite_id=suite_id)
    automated = sum(1 for c in cases if c.get("custom_automation_type") == 1)
    regr_cases = sum(1 for c in cases
                     if _REGRESSION_TITLE_RE.search(c.get("title") or ""))
    # W-step inventory over ALL case titles (normalise W70 → W070).
    w_step_cases: Counter = Counter()
    for c_ in cases:
        for code in re.findall(r"\bW\d{2,3}\b", c_.get("title") or ""):
            w_step_cases[f"W{int(code[1:]):03d}"] += 1

    return {
        "w_step_cases": dict(w_step_cases.most_common()),
        "suite_id": suite_id,
        "project_id": project_id,
        "runs_total": len(per_run),
        "runs_regression": sum(1 for r in per_run if r["is_regression"]),
        "by_year": {str(k): v for k, v in sorted(by_year.items())},
        "cases_total": len(cases),
        "cases_regression_titled": regr_cases,
        "cases_automated": automated,
        "automation_adoption_pct": round(100 * automated / max(len(cases), 1), 1),
        "per_run": per_run,
    }


# ── F. Non-regression volume & change pressure per W-step ───────────────────


def build_change_pressure(jira: JiraClient, corpus: dict | None, run_metrics: dict,
                          projects: str = "S34, KFDO") -> dict:
    """How often each incasso W-step is touched by change (stories/bugs) —
    the driver for regression-suite maintenance (tweak + re-test per change)."""
    inventory = (corpus or {}).get("w_step_cases") or {}
    covered = set(run_metrics.get("w_codes") or {})
    steps = sorted(set(inventory) | covered)

    per_step: dict[str, dict] = {
        s: {"cases_in_suite": inventory.get(s, 0),
            "in_case_study_run": s in covered,
            "jira_issues": 0, "stories": 0, "bugs": 0, "by_year": {},
            "examples": []}
        for s in steps}

    if steps:
        clauses = " OR ".join(f'summary ~ "{s}"' for s in steps)
        jql = f"project in ({projects}) AND ({clauses}) ORDER BY created DESC"
        try:
            issues = jira.search(
                jql, "summary,issuetype,status,created,resolutiondate",
                max_results=200)
        except requests.RequestException as exc:
            print(f"  ⚠️ W-step change-pressure search failed: {exc}",
                  file=sys.stderr)
            issues = []
        for i in issues:
            fi = i["fields"]
            year = str(fi["created"][:4])
            itype = fi["issuetype"]["name"].strip()
            for code in {f"W{int(c[1:]):03d}"
                         for c in re.findall(r"\bW\d{2,3}\b", fi["summary"])}:
                if code not in per_step:
                    continue
                st = per_step[code]
                st["jira_issues"] += 1
                st["by_year"][year] = st["by_year"].get(year, 0) + 1
                if "bug" in itype.lower():
                    st["bugs"] += 1
                else:
                    st["stories"] += 1
                if len(st["examples"]) < 3:
                    st["examples"].append(f"{i['key']} ({itype}): "
                                          f"{fi['summary'][:60]}")

    by_year = {}
    if corpus:
        for year, agg in corpus["by_year"].items():
            by_year[year] = {
                "non_regression_executed":
                    agg["tests_executed"] - agg["regr_executed"],
                "regression_executed": agg["regr_executed"],
            }
    return {
        "jira_projects_scanned": projects,
        "per_step": per_step,
        "steps_missing_from_case_study_run":
            [s for s in steps if not per_step[s]["in_case_study_run"]],
        "non_regression_by_year": by_year,
    }


# ── G. Dev vs test effort (calendar proxy) ───────────────────────────────────

_BACKFILL_THRESHOLD_D = 0.04  # ≈1 h: all transitions inside this = admin backfill


def _phase_days(tis: dict) -> tuple[float, float]:
    dev = sum(v for k, v in tis.items() if k == "In Progress")
    test = sum(v for k, v in tis.items() if k == "In testing")
    return round(dev, 1), round(test, 1)


def build_dev_test_ratio(jira: JiraClient, lifecycle: dict,
                         run_metrics: dict, epic_key: str | None) -> dict:
    """Dev vs test effort as a CALENDAR proxy (In Progress vs In testing days).
    No hours are recorded anywhere; statuses are sometimes backfilled after the
    fact — such issues are flagged and excluded from the aggregate ratio."""
    entries = []

    def add_entry(key, itype, summary, transitions, tis, created, resolved):
        dev, test = _phase_days(tis)
        span = ((_dt(resolved) - _dt(created)).total_seconds() / 86400
                if created and resolved else None)
        backfilled = bool(transitions) and (
            (_dt(transitions[-1]["ts"]) - _dt(transitions[0]["ts"]))
            .total_seconds() / 86400 < _BACKFILL_THRESHOLD_D)
        entries.append({
            "key": key, "issuetype": itype, "summary": summary[:70],
            "dev_days_in_progress": dev, "test_days_in_testing": test,
            "calendar_days": round(span, 1) if span is not None else None,
            "ratio_test_vs_dev": round(test / dev, 2) if dev > 0.1 else None,
            "status_backfilled": backfilled,
        })

    add_entry(lifecycle["key"], lifecycle["issuetype"], lifecycle["summary"],
              lifecycle["transitions"], lifecycle["time_in_status_days"],
              lifecycle["created"], lifecycle["resolutiondate"])

    # The run's defects: Jira fix cycle + TestRail failed→passed retest gap.
    defect_keys = [d["key"] for d in run_metrics["defects"]]
    if defect_keys:
        try:
            for i in jira.search(f"issuekey in ({','.join(defect_keys)})",
                                 "summary,issuetype,status,created,resolutiondate",
                                 max_results=50, expand="changelog"):
                trans = _status_transitions(i)
                add_entry(i["key"], i["fields"]["issuetype"]["name"].strip(),
                          i["fields"]["summary"], trans,
                          _time_in_status(i, trans), i["fields"]["created"],
                          i["fields"].get("resolutiondate"))
        except requests.RequestException as exc:
            print(f"  ⚠️ defect changelog fetch failed: {exc}", file=sys.stderr)

    retest_gaps = []
    results = sorted(run_metrics.get("_results_raw") or [],
                     key=lambda r: r["created_on"])
    for idx, r in enumerate(results):
        if not r.get("defects"):
            continue
        for later in results[idx + 1:]:
            if later["test_id"] == r["test_id"] and later.get("status_id") == 1:
                retest_gaps.append({
                    "defects": r["defects"],
                    "failed_at": datetime.fromtimestamp(r["created_on"]).isoformat(),
                    "passed_at": datetime.fromtimestamp(later["created_on"]).isoformat(),
                    "gap_days": round((later["created_on"] - r["created_on"]) / 86400, 1),
                })
                break

    epic_children = []
    if epic_key:
        try:
            for i in jira.search(f'"Epic Link" = {epic_key} ORDER BY key ASC',
                                 "summary,issuetype,status,created,resolutiondate",
                                 max_results=100, expand="changelog"):
                trans = _status_transitions(i)
                dev, test = _phase_days(_time_in_status(i, trans))
                backfilled = bool(trans) and (
                    (_dt(trans[-1]["ts"]) - _dt(trans[0]["ts"]))
                    .total_seconds() / 86400 < _BACKFILL_THRESHOLD_D)
                epic_children.append({
                    "key": i["key"],
                    "issuetype": i["fields"]["issuetype"]["name"].strip(),
                    "status": i["fields"]["status"]["name"],
                    "summary": i["fields"]["summary"][:70],
                    "dev_days_in_progress": dev,
                    "test_days_in_testing": test,
                    "ratio_test_vs_dev": (round(test / dev, 2)
                                          if dev > 0.1 else None),
                    "status_backfilled": backfilled,
                })
        except requests.RequestException as exc:
            print(f"  ⚠️ epic children fetch failed: {exc}", file=sys.stderr)

    # Aggregate ratio only over issues where BOTH phases were actually
    # tracked (>0.1 d), deduped by key; a resolved story that never entered
    # "In testing" is reported separately — testing untracked at story level.
    seen: set[str] = set()
    valid, untracked_testing = [], 0
    for e in entries + epic_children:
        if e["key"] in seen or e["status_backfilled"]:
            continue
        seen.add(e["key"])
        if e["dev_days_in_progress"] > 0.1 and e["test_days_in_testing"] > 0.1:
            valid.append(e["ratio_test_vs_dev"])
        elif (e["dev_days_in_progress"] > 0.1
              and e["test_days_in_testing"] <= 0.1
              and e.get("status") in ("Resolved", "Done", None)):
            untracked_testing += 1
    gap_days = [g["gap_days"] for g in retest_gaps]
    return {
        "method": ("Kalenderproxy: dagen 'In Progress' (dev) vs 'In testing' "
                   "(test) uit de Jira-changelog. Geen urenregistratie aanwezig; "
                   "administratief teruggeboekte statussen (alle transities "
                   "binnen ~1 uur) zijn gemarkeerd en uitgesloten."),
        "entries": entries,
        "epic_key": epic_key,
        "epic_children": epic_children,
        "retest_gaps": retest_gaps,
        "retest_gap_days": {
            "count": len(gap_days),
            "mean": round(statistics.mean(gap_days), 1) if gap_days else None,
            "median": round(statistics.median(gap_days), 1) if gap_days else None,
        },
        "ratio_summary": {
            "n_valid": len(valid),
            "median_test_vs_dev": (round(statistics.median(valid), 2)
                                   if valid else None),
            "mean_test_vs_dev": (round(statistics.mean(valid), 2)
                                 if valid else None),
            "n_resolved_without_testing_phase": untracked_testing,
        },
    }


# ── V. Value stream map (SAFe-style: active / wait / %C&A per step) ─────────

WORKDAY_HOURS = 8.0
FTE_FACTOR = 0.8  # 40 u/wk bij 0,8 FTE — de rekeneenheid die de business hanteert


def _workdays(start: datetime, end: datetime) -> float:
    """Werkdagen (ma–vr) tussen twee momenten, met fractie van de laatste dag."""
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


def build_value_stream(lifecycle: dict, run_metrics: dict, dev_test: dict) -> dict:
    """Waardestroom van idee tot afronding, per stap: actieve tijd (werk),
    wachttijd (stilstand) en %C&A (first-time-right). Alles in WERKDAGEN."""
    trans = {t["to"]: _dt(t["ts"]) for t in lifecycle["transitions"]}
    created = _dt(lifecycle["created"])
    in_progress = trans.get("In Progress")
    in_testing = trans.get("In testing")
    first_res = _dt(run_metrics["first_result"]) if run_metrics["first_result"] else None
    last_res = _dt(run_metrics["last_result"]) if run_metrics["last_result"] else None
    resolved = (_dt(lifecycle["resolutiondate"]) if lifecycle["resolutiondate"]
                else None)

    ep = run_metrics["effort_proxy"]
    active_test_days = sum(v["active_days"] for v in ep["per_tester"].values())
    exec_window_wd = _workdays(first_res, last_res) if first_res and last_res else 0.0
    # Stilstand binnen het executievenster: werkdagen zonder enig resultaat.
    result_days = {datetime.fromtimestamp(r["created_on"]).date()
                   for r in run_metrics.get("_results_raw") or []}
    idle_wd = max(exec_window_wd - len([d for d in result_days
                                        if d.weekday() < 5]), 0)

    # Testvoorbereiding: subtaken die expliciet voorbereiding/data betreffen.
    prep_keys = [s for s in lifecycle["subtasks"]
                 if any(w in s["summary"].lower()
                        for w in ("voorbereid", "bestaalstapel", "testdata"))]
    prep_active = sum(s["time_in_status_days"].get("In Progress", 0)
                      + s["time_in_status_days"].get("In testing", 0)
                      for s in prep_keys)

    fp = run_metrics["first_pass_rate"]
    # Bouwvenster in werkdagen; actieve inzet daarbinnen is niet geregistreerd —
    # geschat op 0,8 FTE van het venster (expliciete aanname, zie rapport).
    build_wd = _workdays(in_progress, in_testing) if in_progress and in_testing else 0.0
    build_active = round(build_wd * FTE_FACTOR, 1)
    prep_wd = _workdays(in_testing, first_res) if in_testing and first_res else 0.0
    prep_active_est = min(round(prep_active * 0.2, 1) if prep_active else 3.0,
                          max(prep_wd, 1.0))

    steps = [
        {"step": "Bouw (development)",
         "active_days": build_active,
         "wait_days": round(build_wd - build_active, 1),
         "ca_pct": None,
         "note": "start bouw → overdracht naar test"},
        {"step": "Testvoorbereiding",
         "active_days": prep_active_est,
         "wait_days": round(max(prep_wd - prep_active_est, 0), 1),
         "ca_pct": None,
         "note": "Key Users + testdata klaarzetten"},
        {"step": "Testuitvoering",
         "active_days": float(active_test_days),
         "wait_days": round(idle_wd, 1),
         "ca_pct": round(fp * 100),
         "note": f"{run_metrics['results']} uitvoeringen door "
                 f"{ep['testers']} testers"},
        {"step": "Bugfix + hertest",
         "active_days": round(dev_test["retest_gap_days"]["count"] * 0.5, 1),
         "wait_days": round(dev_test["retest_gap_days"]["median"] or 0, 1),
         "ca_pct": 100,
         "note": f"{len(run_metrics['defects'])} bugs; mediaan "
                 f"{dev_test['retest_gap_days']['median']} d wachten per bug"},
        {"step": "Afronding / oplevering",
         "active_days": 1.0,
         "wait_days": round(_workdays(last_res, resolved)
                            if last_res and resolved else 0.0, 1),
         "ca_pct": 100,
         "note": "laatste test → story Resolved"},
    ]

    total_active = sum(s["active_days"] for s in steps)
    total_wait = sum(s["wait_days"] for s in steps)
    lead = total_active + total_wait
    ca_vals = [s["ca_pct"] / 100 for s in steps if s["ca_pct"] is not None]
    rolled_ca = 1.0
    for v in ca_vals:
        rolled_ca *= v

    # Geautomatiseerd scenario: uitvoering en hertest vallen weg als handwerk.
    auto_steps = []
    for s in steps:
        if s["step"] == "Testuitvoering":
            # Draaien is geautomatiseerd; er blijft één dag over voor het
            # beoordelen van de uitslag en het oppakken van echte fouten.
            auto_steps.append({**s, "active_days": 1.0, "wait_days": 0.0,
                               "ca_pct": s["ca_pct"]})
        elif s["step"] == "Bugfix + hertest":
            auto_steps.append({**s, "active_days": s["active_days"],
                               "wait_days": 1.0})
        else:
            auto_steps.append(s)
    auto_active = sum(s["active_days"] for s in auto_steps)
    auto_wait = sum(s["wait_days"] for s in auto_steps)

    return {
        "unit": "werkdagen (ma–vr); actief = werk, wacht = stilstand",
        "fte_factor": FTE_FACTOR,
        "scope": "start bouw → story opgeleverd (backlog-wachttijd uitgesloten)",
        "backlog_wait_days": (_workdays(created, in_progress)
                              if in_progress else None),
        "steps": steps,
        "totals": {
            "active_days": round(total_active, 1),
            "wait_days": round(total_wait, 1),
            "lead_time_days": round(lead, 1),
            "flow_efficiency_pct": round(100 * total_active / lead) if lead else None,
            "rolled_first_pass_pct": round(rolled_ca * 100),
        },
        "automated_scenario": {
            "steps": auto_steps,
            "active_days": round(auto_active, 1),
            "wait_days": round(auto_wait, 1),
            "lead_time_days": round(auto_active + auto_wait, 1),
            "flow_efficiency_pct": (round(100 * auto_active /
                                          (auto_active + auto_wait))
                                    if (auto_active + auto_wait) else None),
        },
    }


# ── E. Cross-system lifecycle timeline ───────────────────────────────────────


def build_timeline(lifecycle: dict, run_metrics: dict) -> dict:
    events: list[dict] = []

    def add(ts, system, entity, event, detail=""):
        events.append({"ts": _dt(ts).isoformat(), "system": system,
                       "entity": entity, "event": event, "detail": detail})

    add(lifecycle["created"], "jira", lifecycle["key"], "created",
        lifecycle["summary"][:60])
    for tr_ in lifecycle["transitions"]:
        add(tr_["ts"], "jira", lifecycle["key"], f"status → {tr_['to']}", tr_["author"])
    for sub in lifecycle["subtasks"]:
        add(sub["created"], "jira", sub["key"], "created", sub["summary"][:60])
        for tr_ in sub["transitions"]:
            add(tr_["ts"], "jira", sub["key"], f"status → {tr_['to']}",
                sub["summary"][:40])

    status_names = run_metrics["_status_names"]
    for r in run_metrics["_results_raw"]:
        status = status_names.get(r.get("status_id"), "note")
        detail = f"test {r['test_id']}" + (f" defect {r['defects']}"
                                           if r.get("defects") else "")
        add(r["created_on"], "testrail", f"run {run_metrics['run_id']}",
            f"result {status}", detail)

    for d in run_metrics["defects"]:
        add(d["created"], "jira-bug", d["key"], "opened", d["summary"][:60])
        if d["resolved"]:
            add(d["resolved"], "jira-bug", d["key"], "resolved", d["summary"][:60])

    events.sort(key=lambda e: e["ts"])

    # Phase boundaries.
    def _first_to(status: str):
        for tr_ in lifecycle["transitions"]:
            if tr_["to"] == status:
                return _dt(tr_["ts"])
        return None

    in_progress = _first_to("In Progress")
    resolved = _first_to("Resolved") or (
        _dt(lifecycle["resolutiondate"]) if lifecycle["resolutiondate"] else None)
    first_res = (_dt(run_metrics["first_result"])
                 if run_metrics["first_result"] else None)
    last_res = _dt(run_metrics["last_result"]) if run_metrics["last_result"] else None

    for e in events:
        ts = datetime.fromisoformat(e["ts"])
        if e["system"] == "jira-bug":
            e["phase"] = "defect_loop"
        elif first_res and ts < first_res:
            e["phase"] = "prep" if (in_progress and ts >= in_progress) else "backlog"
        elif last_res and ts <= last_res:
            e["phase"] = "execution"
        else:
            e["phase"] = "closure"

    def _days(a, b):
        return round((b - a).total_seconds() / 86400, 1) if a and b else None

    net_hours = run_metrics["effort_proxy"]["net_active_hours"]
    calendar_days = _days(in_progress, resolved)
    phases = {
        "prep_days": _days(in_progress, first_res),
        "execution_days": _days(first_res, last_res),
        "closure_days": _days(last_res, resolved),
        "calendar_days_in_progress_to_resolved": calendar_days,
        "in_testing_days": lifecycle["time_in_status_days"].get("In testing"),
        "net_active_person_hours": net_hours,
        "testers": run_metrics["effort_proxy"]["testers"],
        "active_vs_calendar_pct": (
            round(100 * net_hours / (calendar_days * 8), 1)
            if calendar_days else None),  # share of an 8h/day working calendar
    }
    return {"events": events, "phases": phases}


# ── D. Effort / ROI model ────────────────────────────────────────────────────


def build_roi_model(run_metrics: dict, corpus: dict | None) -> dict:
    anchor = run_metrics["effort_proxy"]["pooled_median_gap_min"] or 10.0
    reexec = run_metrics["executions_per_test"]["mean"] or 1.0

    # Annual volume: mean tests/year over observed years (2026 annualised),
    # regression subset AND whole suite (user fallback: regression as subset).
    scopes = {}
    if corpus:
        now = datetime.now()
        year_frac = max((now.timetuple().tm_yday) / 365, 0.1)
        for scope, key in (("regression_subset", "regr_executed"),
                           ("whole_suite", "tests_executed")):
            per_year = []
            for year, agg in corpus["by_year"].items():
                n = agg[key]
                if int(year) == now.year:
                    n = n / year_frac
                per_year.append(n)
            tests_year = statistics.mean(per_year) if per_year else 0
            scopes[scope] = round(tests_year * reexec)

    bands = {"low": round(anchor * 0.75, 1), "mid": round(anchor * 1.5, 1),
             "high": round(anchor * 2.0, 1)}
    assumptions = {
        "minutes_per_execution_anchor": anchor,
        "minutes_bands": bands,
        "reexecution_factor": reexec,
        "build_hours_per_case_bands": [2, 4, 8],
        "maintenance_pct_of_build_per_year": 0.20,
        "automation_residual_effort": 0.10,  # triage/supervision left after automating
        "note": ("Anchor = pooled median in-session gap between result submissions "
                 "(lower bound: misses setup/analysis). Bands are sensitivity, "
                 "not measurements. Confirm all inputs with Key Users."),
    }

    cases = (corpus or {}).get("cases_regression_titled") or run_metrics["tests"]
    residual = assumptions["automation_residual_effort"]
    maint_pct = assumptions["maintenance_pct_of_build_per_year"]

    scenarios = []
    for scope, execs_year in scopes.items():
        for band, minutes in bands.items():
            manual_hours = execs_year * minutes / 60
            saving = manual_hours * (1 - residual)
            for bh in assumptions["build_hours_per_case_bands"]:
                build = cases * bh
                maint = build * maint_pct
                net = saving - maint
                scenarios.append({
                    "scope": scope,
                    "effort_band": band,
                    "minutes_per_execution": minutes,
                    "annual_executions": execs_year,
                    "annual_manual_hours": round(manual_hours),
                    "build_hours_per_case": bh,
                    "build_hours_total": build,
                    "annual_maintenance_hours": round(maint),
                    "annual_net_saving_hours": round(net),
                    "payback_years": round(build / net, 1) if net > 0 else None,
                })

    # Target cadence: the team intends weekly or per-sprint regression of the
    # full incassoproces (refactoring/robustness programme, simplified business
    # rules). One execution per case per run (defect re-runs excluded); build
    # at the middle band (4 h/case).
    build_mid = cases * 4
    maint_mid = build_mid * maint_pct
    target_scenarios = []
    for label, runs_per_year in (("wekelijks", 52), ("per sprint (3 wk)", 17)):
        for band, minutes in bands.items():
            manual = cases * runs_per_year * minutes / 60
            net = manual * (1 - residual) - maint_mid
            target_scenarios.append({
                "cadence": label,
                "runs_per_year": runs_per_year,
                "effort_band": band,
                "minutes_per_execution": minutes,
                "annual_manual_hours": round(manual),
                "build_hours_total": build_mid,
                "annual_net_saving_hours": round(net),
                "payback_years": round(build_mid / net, 1) if net > 0 else None,
            })

    return {"assumptions": assumptions, "annual_executions_by_scope": scopes,
            "automatable_cases": cases, "scenarios": scenarios,
            "target_cadence_scenarios": target_scenarios}


# ── render ───────────────────────────────────────────────────────────────────


def _doelcadans_md(roi: dict) -> list[str]:
    """Target-cadence conclusion: weekly / per-sprint incassoproces regression."""
    rows = roi.get("target_cadence_scenarios") or []
    if not rows:
        return []
    cases = roi["automatable_cases"]
    build = rows[0]["build_hours_total"]
    L: list[str] = []
    L.append("### Doelcadans: wekelijkse of per-sprint regressie van het "
             "incassoproces\n")
    L.append(f"Het team wil het volledige incassoproces **1×/week of 1×/sprint "
             f"(3 weken)** kunnen regressietesten, omdat het proces verbeterd, "
             f"robuust gemaakt (gerefactord) en qua business rules vereenvoudigd "
             f"gaat worden. Dat is de cadans waarop de business case beoordeeld "
             f"moet worden — niet de historische (4–37 uitgevoerde "
             f"regressietests/jaar). Model: {cases} cases × 1 executie per run "
             f"(defect-herexecuties niet meegerekend), bouw {build} uur "
             f"(middenband 4 u/case), onderhoud "
             f"{round(roi['assumptions']['maintenance_pct_of_build_per_year'] * 100)}"
             f"%/jaar.\n")
    L.append("| Cadans | Runs/jr | Band | Min/exec | Handmatig equivalent (u/jr) "
             "| Netto besparing/jr | Terugverdientijd |")
    L.append("|---|---|---|---|---|---|---|")
    for s in rows:
        pay = f"{s['payback_years']} jr" if s["payback_years"] else "n.v.t."
        L.append(f"| {s['cadence']} | {s['runs_per_year']} | {s['effort_band']} | "
                 f"{s['minutes_per_execution']} | {s['annual_manual_hours']} | "
                 f"{s['annual_net_saving_hours']} | {pay} |")
    L.append("")
    weekly_mid = next(s for s in rows
                      if s["runs_per_year"] == 52 and s["effort_band"] == "mid")
    L.append(f"**Conclusie:** handmatig kost de wekelijkse doelcadans "
             f"~{weekly_mid['annual_manual_hours']} uur/jaar (middenband) — "
             f"≈ {round(weekly_mid['annual_manual_hours'] / 1600, 1)} FTE, niet "
             f"realistisch naast het huidige werk (historisch worden "
             f"regressieruns wél aangemaakt maar amper uitgevoerd). "
             f"Geautomatiseerd is dezelfde cadans na een bouwinvestering van "
             f"{build} uur haalbaar, met terugverdientijd "
             f"{min(s['payback_years'] for s in rows if s['payback_years'])}"
             f"–{max(s['payback_years'] for s in rows if s['payback_years'])} "
             f"jaar afhankelijk van cadans en effortband. De businesscase is "
             f"dus geen efficiency-case op bestaande uren, maar een "
             f"**enabler-case**: de gewenste kwaliteitsborging rond de "
             f"incasso-refactoring is zonder automatisering praktisch "
             f"onhaalbaar.\n")
    return L


def _verantwoording_md(report: dict) -> list[str]:
    """Section 9: functional + technical design of the analysis itself."""
    rm = report["testrail_run"]
    tl = report["timeline"]["phases"]
    corpus = report.get("corpus")
    dd = rm["defect_resolution_days"]
    a = report["roi_model"]["assumptions"]
    n_events = len(report["timeline"]["events"])
    L: list[str] = []

    L.append("## 11. Verantwoording — functioneel & technisch ontwerp\n")
    L.append("### 11.1 Functionele stappen\n")
    L.append("| # | Stap | Doel | Resultaat |")
    L.append("|---|---|---|---|")
    L.append("| 1 | Bronverkenning | Vaststellen welke meetdata bestaat | "
             "Jira-changelog ✓ · worklogs ✗ (0) · TestRail `elapsed` ✗ (~0%) · "
             "estimates ✗ |")
    L.append(f"| 2 | Jira-levenscyclus | Statusovergangen van story + subtaken | "
             f"Fasen {tl['prep_days']}d prep / {tl['execution_days']}d executie / "
             f"{tl['closure_days']}d afronding; {tl['in_testing_days']}d In testing |")
    L.append(f"| 3 | TestRail-executie | Resultaathistorie van de run | "
             f"{rm['results']} resultaten / {rm['tests']} tests; "
             f"{rm['executions_per_test']['mean']}× her-executie; first-pass "
             f"{round(rm['first_pass_rate'] * 100)}% |")
    L.append(f"| 4 | Defect-koppeling | TestRail `defects`-veld → Jira-bugs | "
             f"{dd['count']} bugs, oplostijd gem. {dd['mean']} d |")
    L.append(f"| 5 | Effort-proxy | Uren nergens geregistreerd → sessie-gap-methode "
             f"| Anker {a['minutes_per_execution_anchor']} min/executie; "
             f"{tl['net_active_person_hours']} netto uren |")
    if corpus:
        L.append(f"| 6 | Corpus-scan | Frequentie + automatiseringsgraad | "
                 f"{corpus['runs_total']} runs, {corpus['cases_total']} cases, "
                 f"{corpus['automation_adoption_pct']}% geautomatiseerd |")
    L.append(f"| 7 | Tijdlijn | Cross-systeem event-stroom | {n_events} events; "
             f"defect-loop zichtbaar (bug → failed → retest → passed → resolved) |")
    L.append("| 8 | ROI-model | Gevoeligheidsanalyse i.p.v. schijnprecisie | "
             "2 scopes × 3 effortbanden × 3 bouwbanden = 18 scenario's + "
             "doelcadans |")
    L.append("| 9 | Wijzigingsdruk per W-stap | Onderhoudslast regressieset "
             "onderbouwen | W-inventaris uit case-titels + Jira-search op "
             "W-codes (§7) |")
    L.append("| 10 | Dev:test-kalenderproxy | Verhouding test- vs dev-inspanning "
             "| In Progress- vs In testing-dagen, story + bugs + epic-children "
             "(§8) |")
    L.append("| 11 | Rapportage | JSON + CSV's (runs/defects/tijdlijn/wsteps/"
             "devtest) + dit rapport | reproduceerbaar via één CLI-run |")
    L.append("")

    L.append("### 11.2 Technisch ontwerp — bronnen en velden\n")
    L.append("**Jira Data Center** (Bearer PAT uit `creds.yaml`; REST-basis "
             "autogedetecteerd incl. `/jira`-contextpad):\n")
    L.append("| Endpoint | Gebruikte velden | Gebruikt voor |")
    L.append("|---|---|---|")
    L.append("| `GET /rest/api/2/issue/{key}?expand=changelog` (story én per "
             "subtaak) | `created`, `updated`, `resolutiondate`, `status`, "
             "`issuetype`, `summary`, `subtasks`, `issuelinks`; "
             "`changelog.histories[].items[]` met field = `status` / `Sprint` / "
             "`Flagged` / `Story Points` | Statusovergangen, tijd-per-status, "
             "fasegrenzen, teststadia, sprint-spillover, impediments |")
    L.append("| `GET /rest/api/2/search` (`issuekey in (…)`, ook met "
             "`expand=changelog`) | `summary`, `issuetype`, `status`, `created`, "
             "`resolutiondate` (+ changelog voor bugs/epic-children) | "
             "Defect-oplostijden; dev:test-fasen per issue |")
    L.append("| `GET /rest/api/2/search` (`project in (S34, KFDO) AND summary ~ "
             "\"Wxxx\"`) | `summary`, `issuetype`, `created` | Wijzigingsdruk "
             "per W-stap |")
    L.append("| `GET /rest/api/2/search` (`\"Epic Link\" = <epic>`) | idem + "
             "changelog | Epic-brede dev:test-verhouding |")
    L.append("")
    L.append("**TestRail** (Basic auth):\n")
    L.append("| Endpoint | Gebruikte velden | Gebruikt voor |")
    L.append("|---|---|---|")
    L.append("| `get_run/{id}` | `name`, `suite_id`, `project_id`, `created_on`, "
             "status-counts, `untested_count` | Runmetadata; fallback-telling |")
    L.append("| `get_tests/{run_id}` | `title`, `status_id`, "
             "`custom_automation_type` | W-codes, regressiedetectie (titel-regex), "
             "uitgevoerd-filter (`status_id ≠ 3`) |")
    L.append("| `get_results_for_run/{run_id}` | `test_id`, `status_id`, "
             "`created_on`, `created_by`, `defects` (`elapsed` bleek leeg) | "
             "Her-executies, first-pass-rate, effort-proxy, defect-koppeling, "
             "tijdlijn |")
    L.append("| `get_statuses` | `id`, `name` | Statuslabels |")
    L.append("| `get_runs/{project_id}?suite_id=` | `id`, `name`, `created_on`, "
             "counts | Corpus/frequentie |")
    L.append("| `get_cases/{project_id}?suite_id=` | `title`, "
             "`custom_automation_type` | Automatiseringsgraad, regressie-cases |")
    L.append("")

    L.append("### 11.3 Afgeleide metrieken\n")
    L.append("| Metriek | Berekening |")
    L.append("|---|---|")
    L.append("| Tijd per status | changelog-transities chronologisch; "
             "created → … → resolutiondate |")
    L.append("| Fasen | prep = In Progress → 1e TestRail-resultaat; executie = "
             "1e → laatste resultaat; afronding = laatste resultaat → Resolved |")
    L.append(f"| Netto actieve tijd | som van gaps ≤ {SESSION_GAP_CAP_S // 60} min "
             "tussen opeenvolgende result-submits per tester (ondergrens) |")
    L.append("| Anker min/executie | mediaan van diezelfde gaps |")
    L.append("| First-pass-rate | eerste betekenisvolle resultaat per test = "
             "passed |")
    L.append("| Uitgevoerd (corpus) | `status_id ≠ 3` (untested) — nooit-gedraaide "
             "runs vallen zo weg |")
    L.append("| Regressiedetectie | test-**titel**-regex (`regress` of "
             "`W### -> W###`); run-naam is onbetrouwbaar |")
    L.append(f"| Jaarvolume | gem. uitgevoerde tests/jaar (lopend jaar "
             f"geannualiseerd) × her-executiefactor {a['reexecution_factor']} |")
    L.append(f"| ROI | besparing = handm. uren × "
             f"{round((1 - a['automation_residual_effort']) * 100)}%; onderhoud = "
             f"{round(a['maintenance_pct_of_build_per_year'] * 100)}% van bouw/jr; "
             "terugverdientijd = bouw / netto besparing |")
    L.append("")

    L.append("### 11.4 Datakwaliteitsbeslissingen\n")
    L.append("| Bevinding | Beslissing |")
    L.append("|---|---|")
    L.append("| 0 worklogs, 0 estimates, `elapsed` ~0% | Effort via "
             "sessie-gap-proxy + aannamebanden i.p.v. schijnprecisie |")
    L.append("| Volledige-suite-runs 100% untested (phantom-intent) | Uitgesloten "
             "via uitgevoerd-filter |")
    L.append("| TestRail negeert `offset` op `get_tests` | Paginatie met "
             "stall-detectie + paginacap |")
    L.append("| `creds.yaml` mist `/jira`-contextpad | Base-URL-autodetectie via "
             "serverInfo-probe |")
    L.append("| Run-naam ≠ betrouwbare regressie-marker | Detectie op test-titel "
             "i.p.v. run-naam |")
    L.append("| Bug-statussen deels achteraf geboekt (alle transities < 1 u) | "
             "Backfill-detectie; uitgesloten uit dev:test-aggregaat |")
    L.append("")
    L.extend(_verdieping_md())
    return L


def _verdieping_md() -> list[str]:
    """Section 12: suggested scope extensions for pipeline-wide insight."""
    L: list[str] = []
    L.append("## 12. Verdiepingssuggesties — voortbrengingsketen\n")
    L.append("Wat deze analyse (nog) níet ziet, en hoe dat inzicht wél te "
             "krijgen is:\n")
    L.append("| # | Suggestie | Waarom / wat het oplevert | Bron |")
    L.append("|---|---|---|---|")
    L.append("| 1 | **SAP-transportdata koppelen** (ChaRM/Solution Manager, of "
             "de 'Change'/'Standard Change'-issues in Jira zoals ITS-304898) | "
             "Echte dev-inspanning en release-cadans; Jira's dev-status-API "
             "toont 0 commits/PR's — het werk zit in transports, niet in git | "
             "SolMan-export of ITS-Change-issues |")
    L.append("| 2 | **Defect-escape-rate** meten: bugs gevonden in test (S34-"
             "bugs) vs incidenten in productie (ITS-incidents, bv. ITS-303099 "
             "dat door S34-2907 werd opgelost) per W-stap | Monetariseert "
             "defect-preventie — de batenregel die nu bewust buiten de case "
             "blijft | Jira JQL over ITS + issuelinks |")
    L.append("| 3 | **Flow-metrics over het hele epic/portfolio** (alle "
             "S34/KFDO-stories: cycle time, flow-efficiency = actieve dagen / "
             "kalenderdagen, wachttijd per status) | Laat zien waar de keten "
             "écht wacht (deze case: 1,1% actief); automation verkort maar één "
             "schakel | Jira changelog batch-scan (deze scripts herbruikbaar) |")
    L.append("| 4 | **TestRail-milestones/plans gebruiken** en `elapsed` één "
             "cyclus registreren + `custom_automation_type` bijhouden bij elke "
             "geautomatiseerde case | Maakt de volgende versie van deze case "
             "gemeten i.p.v. proxy-gebaseerd; sluit aan op KFDO-715 "
             "(herinrichting TestRail) | TestRail |")
    L.append("| 5 | **Onderhouds-baseline uit de wijzigingsdruk** (§7): per "
             "W-stap-wijziging de werkelijke tweak-uren van de Ranorex-set "
             "loggen zodra de pilot draait | Vervangt de aanname 20%/jaar door "
             "een gemeten onderhoudsfactor | Ranorex-pilot + Jira |")
    L.append("| 6 | **Doorlooptijd-baten apart modelleren**: kortere "
             "feedback-lus (bug binnen een dag i.p.v. mediaan ~8 d hertest-gap) "
             "versnelt de refactoring zelf | De enabler-waarde van §10 wordt "
             "kwantificeerbaar in refactor-sprintcapaciteit | deze extractie, "
             "per sprint herhaald |")
    L.append("")
    return L


def render_report_md(report: dict) -> str:
    lc = report["jira_lifecycle"]
    rm = report["testrail_run"]
    tl = report["timeline"]["phases"]
    corpus = report.get("corpus")
    roi = report["roi_model"]
    L: list[str] = []

    L.append("# Business case data: manual → geautomatiseerd (regressie)testen\n")
    L.append(f"_Extractie {report['generated']} · Jira **{lc['key']}** · "
             f"TestRail run **{rm['run_id']}** · suite {rm['suite_id']}_\n")

    vs0 = report.get("value_stream")
    if vs0:
        t0 = vs0["totals"]
        a0 = vs0["automated_scenario"]
        ep0 = rm["effort_proxy"]
        testdagen = sum(v["active_days"] for v in ep0["per_tester"].values())
        L.append("## 0. De kern — in testdagen\n")
        L.append("| Vraag | Antwoord |")
        L.append("|---|---|")
        exec_step = next((s for s in vs0["steps"]
                          if s["step"] == "Testuitvoering"), {})
        # Alles hieronder wordt afgeleid; alleen expliciet gelabelde aannames
        # zijn dat niet. Hardcoded cijfers uit één run maakten dit blok
        # onbruikbaar voor elke andere story.
        n_testers = ep0["testers"]
        first, last = rm.get("first_result"), rm.get("last_result")
        win_wd = (_workdays(_dt(first), _dt(last)) if first and last else 0.0)
        window = (f"**{win_wd / 5:.0f} weken** ({win_wd:.0f} werkdagen)"
                  if win_wd >= 10 else f"**{win_wd:.0f} werkdagen**")
        n_cases = (corpus or {}).get("cases_regression_titled") or 0
        bands = roi["assumptions"].get("build_hours_per_case_bands") or [2, 4, 8]
        build = (f"eenmalig **{n_cases * bands[1] / 8:.0f}–"
                 f"{n_cases * bands[-1] / 8:.0f} dagen** bouwen "
                 f"({n_cases} testgevallen)" if n_cases else
                 "eenmalig **bouwen** (aantal testgevallen onbekend)")

        L.append(f"| Wat kost één handmatige regressieronde? | "
                 f"**{testdagen:.0f} persoonstestdagen** inzet, verspreid over "
                 f"{window} testvenster |")
        L.append(f"| Hoeveel daarvan ligt het stil? | "
                 f"**{exec_step.get('wait_days', 0):.0f} werkdagen** binnen het "
                 f"testvenster zonder enige testactiviteit (wachten op "
                 f"bugfixes) |")
        L.append(f"| En de hele story, van bouw tot oplevering? | "
                 f"**{t0['lead_time_days']:.0f} werkdagen**, waarvan "
                 f"{t0['wait_days']:.0f} wachten — flow-efficiëntie "
                 f"{t0['flow_efficiency_pct']}% (zie §6b) |")
        L.append("| Hoe vaak willen we een ronde? | elke week, of minimaal elke "
                 "sprint (3 weken) — nodig voor de incasso-refactoring |")
        # Ook het oordeel zelf moet uit de meting volgen: een ronde die binnen
        # een week past, kán wekelijks — dan is de vraag of hij de volledige
        # regressie dekt, niet of hij past.
        if 0 < win_wd <= 5:
            verdict = (f"Deze ronde wél ({window}, {n_testers} tester(s)) — maar "
                       f"hij dekt {rm['tests']} testgevallen, geen volledige "
                       f"regressie van het proces")
        else:
            verdict = (f"Nee. Eén ronde beslaat {window} en {n_testers} "
                       f"tester(s); wekelijks is fysiek onmogelijk")
        L.append(f"| Kan dat handmatig? | {verdict} |")
        L.append(f"| Wat kost automatiseren? | {build} + onderhoud bij "
                 f"proceswijzigingen |")
        L.append(f"| Wat levert het per ronde op? | doorlooptijd terug naar "
                 f"**{a0['lead_time_days']:.0f} werkdagen**; bespaarde testdagen "
                 f"is een aanname (zie §5) |")
        L.append("| Wanneer terugverdiend? | zie de terugverdientabel in §5 — "
                 "afhankelijk van de gekozen cadans |")
        L.append("")
        L.append("**Conclusie:** dit is geen besparingscase op bestaande uren "
                 "(die worden nauwelijks gemaakt), maar een **enabler-case**: "
                 "automatisering maakt de wekelijkse regressie mogelijk die de "
                 "refactoring van het incassoproces vereist.\n")
        L.append("_De hoofdstukken hierna onderbouwen deze zeven regels; "
                 "hoofdstuk 11 verantwoordt de methode._\n")

    L.append("## 1. Kernbevindingen\n")
    L.append(f"- **Kalenderdoorlooptijd** (In Progress → Resolved): "
             f"**{tl['calendar_days_in_progress_to_resolved']} dagen**, waarvan "
             f"{tl['in_testing_days']} dagen in status *In testing*.")
    L.append(f"- **Netto actieve testtijd**: **{tl['net_active_person_hours']} "
             f"persoonsuren** verdeeld over {tl['testers']} testers — "
             f"≈ **{tl['active_vs_calendar_pct']}%** van een 8-uurs werkkalender. "
             f"De rest is wachttijd (dataprep, bugfixes, hertests).")
    L.append(f"- **Her-executie-belasting**: {rm['results']} resultaten op "
             f"{rm['tests']} tests = gem. {rm['executions_per_test']['mean']}× per "
             f"test (max {rm['executions_per_test']['max']}); first-pass-rate "
             f"{round(rm['first_pass_rate'] * 100)}%.")
    dd = rm["defect_resolution_days"]
    L.append(f"- **Defects**: {dd['count']} bugs uit deze run; gemiddelde "
             f"oplostijd {dd['mean']} dagen (mediaan {dd['median']}).")
    if corpus:
        L.append(f"- **Frequentie**: {corpus['runs_total']} runs op suite "
                 f"{corpus['suite_id']}; {corpus['runs_regression']} bevatten "
                 f"regressie-getitelde tests. Automatiseringsgraad: "
                 f"**{corpus['automation_adoption_pct']}%** van "
                 f"{corpus['cases_total']} cases (veld `custom_automation_type`, "
                 f"opties: None/Ranorex).")
    L.append("")

    L.append("## 2. Levenscyclus-tijdlijn (Jira → TestRail → Jira)\n")
    L.append("| Fase | Duur |")
    L.append("|---|---|")
    L.append(f"| Voorbereiding (In Progress → eerste testresultaat) | "
             f"{tl['prep_days']} dagen |")
    L.append(f"| Executievenster (eerste → laatste resultaat) | "
             f"{tl['execution_days']} dagen ({rm['execution_days']} actieve dagen) |")
    L.append(f"| Afronding (laatste resultaat → story Resolved) | "
             f"{tl['closure_days']} dagen |")
    L.append(f"| **Totaal kalender** | "
             f"**{tl['calendar_days_in_progress_to_resolved']} dagen** |")
    L.append(f"| **Netto actief (timestamp-proxy)** | "
             f"**{tl['net_active_person_hours']} uur** |")
    L.append("")
    L.append("Teststadia (Jira-subtaken):\n")
    L.append("| Subtaak | Omschrijving | Aangemaakt | Opgelost |")
    L.append("|---|---|---|---|")
    for s in lc["subtasks"]:
        L.append(f"| {s['key']} | {s['summary'][:50]} | {s['created'][:10]} | "
                 f"{(s['resolved'] or '—')[:10]} |")
    L.append("")

    L.append("## 3. Onderwerpen (W-codes)\n")
    L.append("| W-code | Tests | Executies | Failed | Defects |")
    L.append("|---|---|---|---|---|")
    for code, v in rm["w_codes"].items():
        L.append(f"| {code} | {v['tests']} | {v['executions']} | {v['failed']} | "
                 f"{', '.join(v['defects']) or '—'} |")
    L.append("")

    L.append("## 4. Defects uit deze run\n")
    L.append("| Key | Type | Status | Aangemaakt | Opgelost | Dagen |")
    L.append("|---|---|---|---|---|---|")
    for d in rm["defects"]:
        L.append(f"| {d['key']} | {d['issuetype']} | {d['status']} | "
                 f"{d['created'][:10]} | {(d['resolved'] or '—')[:10]} | "
                 f"{d['resolution_days'] if d['resolution_days'] is not None else '—'} |")
    L.append("")

    if corpus:
        L.append("## 5. Corpus en frequentie (suite {})\n".format(corpus["suite_id"]))
        L.append("| Jaar | Runs | Tests (aangemaakt) | Tests (uitgevoerd) | "
                 "Regressie-runs | Regressie uitgevoerd |")
        L.append("|---|---|---|---|---|---|")
        for year, agg in corpus["by_year"].items():
            L.append(f"| {year} | {agg['runs']} | {agg['tests']} | "
                     f"{agg['tests_executed']} | {agg['regr_runs']} | "
                     f"{agg['regr_executed']} |")
        L.append("")
        L.append("_Alleen **uitgevoerde** tests tellen mee in het ROI-model; "
                 "aangemaakte-maar-nooit-gedraaide suite-runs (bv. 3× een "
                 "2868-tests selectie, 100% untested) zijn uitgesloten._")
        share = round(100 * corpus["runs_regression"] / max(corpus["runs_total"], 1))
        L.append("")
        L.append(f"Regressie als deelverzameling: {corpus['runs_regression']} van "
                 f"{corpus['runs_total']} runs ({share}%) bevat regressie-getitelde "
                 f"tests. Het ROI-model rekent daarom **beide scopes** door "
                 f"(regressie-subset én hele suite).\n")

    L.append("## 6. ROI-model (aannames + gevoeligheid)\n")
    a = roi["assumptions"]
    L.append(f"Anker: **{a['minutes_per_execution_anchor']} min/executie** "
             f"(mediane in-sessie-tijd tussen resultaat-submits, run {rm['run_id']}). "
             f"Banden: {a['minutes_bands']}. Her-executiefactor "
             f"{a['reexecution_factor']}×. Bouw: {a['build_hours_per_case_bands']} "
             f"uur/case over {roi['automatable_cases']} cases; onderhoud "
             f"{round(a['maintenance_pct_of_build_per_year'] * 100)}%/jaar; restinspanning "
             f"na automatisering {round(a['automation_residual_effort'] * 100)}%.\n")
    L.append(f"Jaarlijkse executies per scope: {roi['annual_executions_by_scope']}\n")
    L.append("| Scope | Band | Min/exec | Handm. uren/jr | Bouw u/case | "
             "Bouw totaal | Netto besparing/jr | Terugverdientijd |")
    L.append("|---|---|---|---|---|---|---|---|")
    for s in roi["scenarios"]:
        pay = f"{s['payback_years']} jr" if s["payback_years"] else "n.v.t."
        L.append(f"| {s['scope']} | {s['effort_band']} | "
                 f"{s['minutes_per_execution']} | {s['annual_manual_hours']} | "
                 f"{s['build_hours_per_case']} | {s['build_hours_total']} | "
                 f"{s['annual_net_saving_hours']} | {pay} |")
    L.append("")
    L.extend(_doelcadans_md(roi))

    vs = report.get("value_stream")
    if vs:
        t = vs["totals"]
        auto = vs["automated_scenario"]
        L.append("## 6b. Waardestroom: waar gaat de doorlooptijd heen?\n")
        L.append(f"_Scope: {vs['scope']}. Eenheid: {vs['unit']}. "
                 f"Actieve bouwtijd geschat op {vs['fte_factor']} FTE "
                 f"(40 u/week); testinzet is gemeten._\n")
        L.append("| Stap | Actieve tijd | Wachttijd | First-time-right | "
                 "Toelichting |")
        L.append("|---|---|---|---|---|")
        for s in vs["steps"]:
            ca = f"{s['ca_pct']}%" if s["ca_pct"] is not None else "—"
            L.append(f"| {s['step']} | {s['active_days']} d | {s['wait_days']} d "
                     f"| {ca} | {s['note']} |")
        L.append(f"| **Totaal** | **{t['active_days']} d** | "
                 f"**{t['wait_days']} d** | — | doorlooptijd "
                 f"**{t['lead_time_days']} werkdagen** |")
        L.append("")
        L.append(f"**Flow-efficiëntie: {t['flow_efficiency_pct']}%** — van de "
                 f"{t['lead_time_days']} werkdagen doorlooptijd wordt er "
                 f"{t['active_days']} dagen daadwerkelijk gewerkt; de rest is "
                 f"wachten (op testcapaciteit, op bugfixes, op hertestslots).\n")
        L.append(f"Met geautomatiseerde regressie: **{auto['lead_time_days']} "
                 f"werkdagen** doorlooptijd ({auto['active_days']} d actief, "
                 f"{auto['wait_days']} d wachten) — flow-efficiëntie "
                 f"**{auto['flow_efficiency_pct']}%**. De testuitvoering verdwijnt "
                 f"als handwerk en de hertestlus krimpt van dagen naar uren.\n")
        if vs.get("backlog_wait_days"):
            L.append(f"_Buiten scope maar wel relevant: de story stond hiervóór "
                     f"nog {vs['backlog_wait_days']:.0f} werkdagen in de backlog._\n")

    cp = report.get("change_pressure")
    if cp:
        L.append("## 7. Non-regressie en wijzigingsdruk (W-stappen)\n")
        L.append("Naast regressie draait de suite vooral **story-/changetests** — "
                 "en elke wijziging aan een W-stap dwingt straks een tweak + "
                 "her-run van de geautomatiseerde regressieset af. Dit is de "
                 "onderhoudskant van de business case.\n")
        if cp["non_regression_by_year"]:
            L.append("| Jaar | Non-regressie uitgevoerd | Regressie uitgevoerd |")
            L.append("|---|---|---|")
            for year, v in cp["non_regression_by_year"].items():
                L.append(f"| {year} | {v['non_regression_executed']} | "
                         f"{v['regression_executed']} |")
            L.append("")
        L.append("Wijzigingsdruk per W-stap (Jira-issues met de stap in de "
                 f"titel, projecten {cp['jira_projects_scanned']}):\n")
        L.append("| W-stap | Cases in suite | In case-study-run | Jira-issues | "
                 "Stories | Bugs | Voorbeeld |")
        L.append("|---|---|---|---|---|---|---|")
        for step, v in cp["per_step"].items():
            ex = v["examples"][0] if v["examples"] else "—"
            L.append(f"| {step} | {v['cases_in_suite']} | "
                     f"{'✓' if v['in_case_study_run'] else '**✗**'} | "
                     f"{v['jira_issues']} | {v['stories']} | {v['bugs']} | {ex} |")
        L.append("")
        missing = cp["steps_missing_from_case_study_run"]
        if missing:
            L.append(f"⚠️ **Antwoord op 'vergeet ik stappen?': ja** — de suite "
                     f"kent ook {', '.join(missing)}, die in de onderzochte "
                     f"regressierun níet zaten. Neem ze mee in de scope van de "
                     f"te automatiseren set (of onderbouw expliciet waarom niet).\n")

    dt = report.get("dev_test")
    if dt:
        L.append("## 8. Dev- vs testinspanning (kalenderproxy)\n")
        L.append(f"_{dt['method']}_\n")
        L.append("| Issue | Type | Dev (In Progress, d) | Test (In testing, d) | "
                 "Ratio test:dev | Backfilled |")
        L.append("|---|---|---|---|---|---|")
        for e in dt["entries"]:
            L.append(f"| {e['key']} | {e['issuetype']} | "
                     f"{e['dev_days_in_progress']} | {e['test_days_in_testing']} | "
                     f"{e['ratio_test_vs_dev'] if e['ratio_test_vs_dev'] is not None else '—'} | "
                     f"{'⚠️' if e['status_backfilled'] else ''} |")
        L.append("")
        if dt["epic_children"]:
            L.append(f"Epic-breed ({dt['epic_key']}, "
                     f"{len(dt['epic_children'])} children):\n")
            L.append("| Issue | Type | Status | Dev (d) | Test (d) | Ratio | "
                     "Backfilled |")
            L.append("|---|---|---|---|---|---|---|")
            for e in dt["epic_children"]:
                L.append(f"| {e['key']} | {e['issuetype']} | {e['status']} | "
                         f"{e['dev_days_in_progress']} | "
                         f"{e['test_days_in_testing']} | "
                         f"{e['ratio_test_vs_dev'] if e['ratio_test_vs_dev'] is not None else '—'} | "
                         f"{'⚠️' if e['status_backfilled'] else ''} |")
            L.append("")
        rs = dt["ratio_summary"]
        rg = dt["retest_gap_days"]
        L.append(f"**Samenvatting:** mediaan test:dev-ratio "
                 f"**{rs['median_test_vs_dev']}** (gem. {rs['mean_test_vs_dev']}, "
                 f"n={rs['n_valid']} issues waar béide fasen zijn geregistreerd). "
                 f"Bugfix-lus: failed→passed hertest-gap mediaan "
                 f"**{rg['median']} d** (gem. {rg['mean']}, n={rg['count']}) — "
                 f"de tijd die de testkant per defect wacht op dev-fix + "
                 f"hertestslot; de bug-oplostijd zelf (§4, gem. 6,3 d) is de "
                 f"dev-kant van diezelfde lus.\n")
        if rs["n_resolved_without_testing_phase"]:
            L.append(f"⚠️ Datakwaliteit: **{rs['n_resolved_without_testing_phase']} "
                     f"afgeronde issues doorliepen nooit de status 'In testing'** "
                     f"— testinspanning wordt op story-niveau vaak niet "
                     f"geregistreerd (of zit in subtaken). De werkelijke "
                     f"test:dev-verhouding ligt dus eerder hóger dan hier "
                     f"gemeten.\n")

    L.append("## 9. Kanttekeningen (eerlijk)\n")
    L.append("- Netto actieve tijd is een **ondergrens**: de gap-methode mist "
             "losse resultaten, setup, analyse en overleg.")
    L.append("- Kalenderduren zijn **wandkloktijd** en bevatten niet-testgebonden "
             "wachttijd. Besparing op executie-uren en verkorte doorlooptijd zijn "
             "**aparte** batenregels — niet optellen.")
    L.append("- Nergens zijn uren geregistreerd (0 worklogs, 0 estimates, "
             "TestRail `elapsed` vrijwel leeg); het anker moet door Key Users "
             "worden gevalideerd.")
    L.append("- De dev:test-ratio is een **kalender**verhouding (In Progress- vs "
             "In testing-dagen), geen uren-verhouding; statussen worden soms "
             "achteraf geboekt (gemarkeerd ⚠️ en uitgesloten uit het aggregaat).")
    L.append("")

    L.append("## 10. Openstaande vragen\n")
    L.append(f"1. Klopt ±{a['minutes_per_execution_anchor']} min hands-on per "
             "test-executie met het gevoel van de Key Users, of ligt de echte tijd "
             "(incl. setup/analyse) wezenlijk hoger?")
    L.append("2. Ranorex: bouwuren per case en verwacht jaarlijks onderhoud — is er "
             "een pilot-datapunt?")
    L.append("3. Is de huidige run-frequentie representatief voor de toekomst, of "
             "was 2024–2025 opgeblazen door de SAP-migratie?")
    L.append("4. Moet defect-preventie (eerder vangen van bugs) worden "
             "gemonetariseerd, of blijft de case puur op executie-inspanning?")
    L.append("5. Aanbeveling los van de business case: registreer TestRail "
             "`elapsed` één regressiecyclus lang en vul `custom_automation_type` "
             "bij elke geautomatiseerde case — gratis meetbaarheid.")
    L.append("")
    L.extend(_verantwoording_md(report))
    return "\n".join(L)


# ── write ────────────────────────────────────────────────────────────────────


def write_outputs(report: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"testauto_businesscase_{ts}"
    paths = []

    export = {k: v for k, v in report.items() if k != "timeline"}
    export["timeline_phases"] = report["timeline"]["phases"]
    export["testrail_run"] = {k: v for k, v in report["testrail_run"].items()
                              if not k.startswith("_")}
    p = out_dir / f"{stem}.json"
    p.write_text(json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8")
    paths.append(p)

    if report.get("corpus"):
        p = out_dir / f"{stem}_runs.csv"
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["run_id", "date", "year", "name", "tests", "tests_executed",
                        "regression_tests", "regression_executed", "is_regression",
                        "passed", "failed"])
            for r in report["corpus"]["per_run"]:
                w.writerow([r["run_id"],
                            datetime.fromtimestamp(r["created_on"]).date(),
                            r["year"], r["name"], r["tests"], r["tests_executed"],
                            r["regression_tests"], r["regression_executed"],
                            r["is_regression"], r["passed"], r["failed"]])
        paths.append(p)

    p = out_dir / f"{stem}_defects.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "issuetype", "status", "created", "resolved",
                    "resolution_days", "summary"])
        for d in report["testrail_run"]["defects"]:
            w.writerow([d["key"], d["issuetype"], d["status"], d["created"][:10],
                        (d["resolved"] or "")[:10], d["resolution_days"], d["summary"]])
    paths.append(p)

    cp = report.get("change_pressure")
    if cp and cp["per_step"]:
        p = out_dir / f"{stem}_wsteps.csv"
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["w_step", "cases_in_suite", "in_case_study_run",
                        "jira_issues", "stories", "bugs", "example"])
            for step, v in cp["per_step"].items():
                w.writerow([step, v["cases_in_suite"], v["in_case_study_run"],
                            v["jira_issues"], v["stories"], v["bugs"],
                            v["examples"][0] if v["examples"] else ""])
        paths.append(p)

    dt = report.get("dev_test")
    if dt:
        p = out_dir / f"{stem}_devtest.csv"
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["key", "scope", "issuetype", "status", "dev_days",
                        "test_days", "ratio_test_vs_dev", "backfilled",
                        "summary"])
            for e in dt["entries"]:
                w.writerow([e["key"], "case_study", e["issuetype"], "",
                            e["dev_days_in_progress"], e["test_days_in_testing"],
                            e["ratio_test_vs_dev"], e["status_backfilled"],
                            e["summary"]])
            for e in dt["epic_children"]:
                w.writerow([e["key"], "epic", e["issuetype"], e["status"],
                            e["dev_days_in_progress"], e["test_days_in_testing"],
                            e["ratio_test_vs_dev"], e["status_backfilled"],
                            e["summary"]])
        paths.append(p)

    p = out_dir / f"{stem}_timeline.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ts", "system", "entity", "event", "phase", "detail"])
        for e in report["timeline"]["events"]:
            w.writerow([e["ts"], e["system"], e["entity"], e["event"],
                        e["phase"], e["detail"]])
    paths.append(p)

    p = out_dir / f"{stem}_report.md"
    p.write_text(render_report_md(report), encoding="utf-8")
    paths.append(p)
    return paths


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Extract Jira/TestRail data for a test-automation business case.")
    ap.add_argument("--jira", default=None, metavar="KEY",
                    help="Jira story key, e.g. S34-2907 (default: afgeleid uit "
                         "de refs/naam van de TestRail-run)")
    ap.add_argument("--run", required=True, type=int, metavar="ID",
                    help="TestRail run id, e.g. 26442")
    ap.add_argument("--allow-unlinked", action="store_true",
                    help="Ga door ook als de run niet naar de opgegeven Jira-issue "
                         "verwijst (levert een consistent maar onjuist rapport op)")
    ap.add_argument("--suite", type=int, default=None,
                    help="TestRail suite id (default: from the run)")
    ap.add_argument("--project", type=int, default=None,
                    help="TestRail project id (default: from the run)")
    ap.add_argument("--creds", default=None,
                    help="Pad naar creds.yaml (default: zoekt in cwd, naast dit "
                         "script, en in fo_doc_gen)")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--max-runs", type=int, default=0,
                    help="Cap the corpus scan (0 = all runs)")
    ap.add_argument("--epic", default=None, metavar="KEY",
                    help="Epic for the portfolio dev:test scan "
                         "(default: Epic Link from the story's changelog)")
    ap.add_argument("--jql-projects", default="S34, KFDO",
                    help="Jira projects scanned for W-step change pressure")
    ap.add_argument("--skip-corpus", action="store_true",
                    help="Skip the suite-wide run scan (faster)")
    args = ap.parse_args()

    creds_path = Path(args.creds) if args.creds else _find_creds()
    if not creds_path:
        raise SystemExit("Geen creds.yaml gevonden — geef --creds op. Verwacht "
                         "jira.{base_url,api_token} en testrail.{base_url,email,"
                         "api_key,verify_ssl}.")
    print(f"  creds: {creds_path}")
    creds = _load_creds(creds_path)
    jira = JiraClient(creds)
    tr = TestRailClient(creds)
    report: dict = {"generated": datetime.now().isoformat(timespec="seconds")}

    # Establish the Jira↔TestRail link BEFORE anything is analysed: every
    # downstream figure (value stream, dev:test ratio) assumes the story and the
    # run describe the same piece of work.
    print(f"→ Koppeling controleren (run {args.run}) …")
    run_head = tr.get(f"get_run/{args.run}")
    story_key = resolve_story_key(run_head, args.jira, args.allow_unlinked)
    refs, name_keys = _run_jira_keys(run_head)
    report["source_link"] = {
        "run_id": args.run,
        "story_key": story_key,
        "run_refs": refs,
        "keys_in_run_name": name_keys,
        "linked": story_key in (refs + name_keys),
        "allow_unlinked": bool(args.allow_unlinked),
    }

    print(f"→ Jira lifecycle {story_key} …")
    report["jira_lifecycle"] = build_jira_lifecycle(jira, story_key)

    print(f"→ TestRail run {args.run} …")
    report["testrail_run"] = build_run_metrics(tr, jira, args.run)

    if args.skip_corpus:
        report["corpus"] = None
    else:
        project = args.project or report["testrail_run"]["project_id"]
        suite = args.suite or report["testrail_run"]["suite_id"]
        try:
            report["corpus"] = build_corpus(tr, project, suite, args.max_runs)
        except requests.RequestException as exc:
            print(f"⚠️ corpus scan failed, continuing without: {exc}", file=sys.stderr)
            report["corpus"] = None

    print("→ Timeline + ROI model …")
    report["timeline"] = build_timeline(report["jira_lifecycle"],
                                        report["testrail_run"])
    report["roi_model"] = build_roi_model(report["testrail_run"], report["corpus"])

    print("→ Wijzigingsdruk per W-stap + dev:test-ratio …")
    report["change_pressure"] = build_change_pressure(
        jira, report["corpus"], report["testrail_run"], args.jql_projects)
    epic = args.epic or report["jira_lifecycle"].get("epic")
    report["dev_test"] = build_dev_test_ratio(
        jira, report["jira_lifecycle"], report["testrail_run"], epic)

    print("→ Waardestroom (actieve tijd / wachttijd / flow-efficiëntie) …")
    report["value_stream"] = build_value_stream(
        report["jira_lifecycle"], report["testrail_run"], report["dev_test"])

    paths = write_outputs(report, Path(args.out_dir))
    tl = report["timeline"]["phases"]
    print(f"\n✓ {len(paths)} artefacts:")
    for p in paths:
        print(f"  {p.name}")
    print(f"\n  kalender {tl['calendar_days_in_progress_to_resolved']}d · "
          f"netto actief {tl['net_active_person_hours']}h / {tl['testers']} testers "
          f"({tl['active_vs_calendar_pct']}% van 8h/dag) · "
          f"{report['testrail_run']['results']} resultaten / "
          f"{report['testrail_run']['tests']} tests")


if __name__ == "__main__":
    main()
