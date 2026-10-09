"""Alles wat Jira raakt: creds, client, ophalen en de issue-cache.

Jira Data Center: Bearer-PAT (geen Basic auth), self-signed certificaat, en het
REST-pad onder `/jira` wordt automatisch gevonden.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import requests
import urllib3
import yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CACHE_VERSION = 2

# Jira's eigen statusCategory-sleutels → de drie banden van een CFD.
CATEGORY_BY_KEY = {"new": "To Do", "indeterminate": "In Progress", "done": "Done"}

# Waar creds.yaml gezocht wordt als --creds niet is opgegeven. De laatste
# entry deelt het secret met fo_doc_gen zodat het niet gedupliceerd hoeft.
_CREDS_CANDIDATES = (
    Path.cwd() / "creds.yaml",
    Path(__file__).resolve().parent.parent / "creds.yaml",
    Path.home() / "github_repos" / "fo_doc_gen" / "creds.yaml",
)


def warn(msg: str) -> None:
    print(f"  ⚠️ {msg}", file=sys.stderr)


def load_creds(path: str | None) -> dict:
    found = Path(path) if path else next(
        (p for p in _CREDS_CANDIDATES if p.exists()), None)
    if not found or not found.exists():
        raise SystemExit("Geen creds.yaml gevonden — geef --creds op. "
                         "Verwacht jira.{base_url,api_token}.")
    print(f"  creds: {found}")
    return yaml.safe_load(found.read_text(encoding="utf-8")) or {}


class JiraClient:
    """Minimale Jira Data Center-client (Bearer PAT, self-signed cert)."""

    def __init__(self, creds: dict):
        j = creds.get("jira") or {}
        self.headers = {"Authorization": f"Bearer {j.get('api_token', '')}"}
        self.base = self._resolve_base(j.get("base_url", "https://jira.vitens.lan"))

    def _resolve_base(self, configured: str) -> str:
        # creds.yaml bevat de host zonder servlet-contextpad; op deze instance
        # zit de REST-root onder https://<host>/jira.
        root = configured.rstrip("/")
        for cand in (root, f"{root}/jira"):
            try:
                r = requests.get(f"{cand}/rest/api/2/serverInfo",
                                 headers=self.headers, verify=False, timeout=30)
                if r.status_code == 200:
                    return cand
            except requests.RequestException:
                continue
        # Niet stil terugvallen: dan volgt een 404 die op een vertypt project lijkt.
        raise SystemExit(f"Jira niet bereikbaar op {root} (of {root}/jira) — "
                         f"VPN aan, en klopt jira.base_url in creds.yaml?")

    def get(self, path: str, params: dict | None = None, timeout: int = 120):
        r = requests.get(f"{self.base}{path}", params=params,
                         headers=self.headers, verify=False, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def search_all(self, jql: str, fields: str) -> list[dict]:
        """Alle issues van een JQL mét changelog, via startAt-paginering."""
        out: list[dict] = []
        while True:
            page = self.get("/rest/api/2/search", {
                "jql": jql, "fields": fields, "expand": "changelog",
                "maxResults": 100, "startAt": len(out)})
            issues = page.get("issues") or []
            out.extend(issues)
            print(f"    … {len(out)}/{page.get('total', len(out))} issues", flush=True)
            if not issues or len(out) >= page.get("total", 0):
                return out

    def _agile_pages(self, path: str, params: dict) -> list[dict]:
        out: list[dict] = []
        while True:
            page = self.get(path, {**params, "startAt": len(out)})
            out.extend(page.get("values") or [])
            if page.get("isLast", True) or not page.get("values"):
                return out


# ── workflow ─────────────────────────────────────────────────────────────────


def statuses(jira: JiraClient, project: str) -> dict[str, tuple[str, str]]:
    """{status-id: (naam, categorie)}: eerst de workflow van het project (dat
    bepaalt de volgorde), dan alle andere statussen van de instance — de
    changelog verwijst ook naar statussen uit vroegere workflows."""
    try:
        itypes = jira.get(f"/rest/api/2/project/{project}/statuses")
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else None
        if code == 404:
            raise SystemExit(f"Jira kent geen project {project!r} (404) — het is "
                             f"het prefix vóór het issuenummer, dus MOD in "
                             f"MOD-123.") from exc
        if code in (401, 403):
            raise SystemExit(f"Geen toegang tot project {project} ({code}): het "
                             f"token heeft geen leesrechten, of is verlopen.") from exc
        raise
    out: dict[str, tuple[str, str]] = {}
    for st in [s for t in itypes for s in t.get("statuses") or []] + jira.get(
            "/rest/api/2/status"):
        key = (st.get("statusCategory") or {}).get("key", "")
        out.setdefault(st["id"], (st["name"], CATEGORY_BY_KEY.get(key, "To Do")))
    return out


def story_points_field(jira: JiraClient) -> str | None:
    for f in jira.get("/rest/api/2/field"):
        if (f.get("name") or "").strip().lower() in ("story points",
                                                     "story point estimate"):
            return f["id"]
    return None


# ── issues + cache ───────────────────────────────────────────────────────────


def fetch_issues(jira: JiraClient, project: str, since: datetime,
                 cache: Path, refresh: bool) -> list[dict]:
    """Alle issues die in het venster afrondden of nog open staan.

    Open werk zit er volledig in (ook als het lang niet is aangeraakt): zonder
    dat kloppen WIP en de To Do-band van de CFD niet. Epics en subtaken zijn
    geen flow-items en vallen af.
    """
    jql = (f'project = "{project}" AND issuetype NOT IN subTaskIssueTypes() '
           f'AND issuetype != Epic AND (resolutiondate >= '
           f'"{since:%Y-%m-%d}" OR resolution IS EMPTY) ORDER BY key ASC')
    fingerprint = {"cache_version": CACHE_VERSION, "jql": jql}

    if cache.exists() and not refresh:
        try:
            raw = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if {k: raw.get(k) for k in fingerprint} == fingerprint:
            age = (datetime.now() - datetime.fromisoformat(raw["generated"])).days
            print(f"  {len(raw['issues'])} issues uit cache ({age} dagen oud; "
                  f"--refresh voor een verse fetch)")
            if age > 7:
                warn(f"cache is {age} dagen oud — overweeg --refresh")
            return raw["issues"]

    sp = story_points_field(jira)
    fields = "summary,issuetype,status,created,resolutiondate" + (f",{sp}" if sp else "")
    print(f"  JQL: {jql}")
    issues = jira.search_all(jql, fields)
    for issue in issues:  # normaliseer het customfield naar een vaste naam
        issue["fields"]["story_points"] = issue["fields"].pop(sp, None) if sp else None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({**fingerprint, "generated": datetime.now()
                                 .isoformat(timespec="seconds"), "issues": issues},
                                ensure_ascii=False), encoding="utf-8")
    return issues


# ── sprints ──────────────────────────────────────────────────────────────────


def closed_sprints(jira: JiraClient, project: str, since: datetime,
                   board: int | None) -> tuple[int | None, list[dict]]:
    """(board-id, afgesloten sprints sinds `since` die op dat board ontstonden).

    Een sprint verschijnt op elk board dat zijn issues toont — ook op kopieën en
    proefboards. Zonder --board telt daarom het board waar de meeste sprints van
    het project hun oorsprong hebben.
    """
    try:
        boards = [board] if board else [b["id"] for b in jira._agile_pages(
            "/rest/agile/1.0/board", {"projectKeyOrId": project, "type": "scrum"})]
        own = {b: [s for s in jira._agile_pages(f"/rest/agile/1.0/board/{b}/sprint",
                                                {"state": "closed"})
                   if s.get("originBoardId", b) == b] for b in boards}
    except requests.RequestException as exc:
        warn(f"sprints niet op te halen ({exc}) — geen sprintmetrics")
        return board, []
    if not own:
        warn(f"{project} heeft geen scrumboard — geen sprintmetrics")
        return None, []
    board = max(own, key=lambda b: len(own[b]))
    since_s = since.strftime("%Y-%m-%d")
    return board, sorted((s for s in own[board]
                          if (s.get("completeDate") or "") >= since_s),
                         key=lambda s: s["completeDate"])


def sprint_report(jira: JiraClient, board: int, sprint_id: int) -> dict | None:
    """De inhoud van Jira's eigen Sprint Report — dezelfde cijfers als in de UI."""
    try:
        return jira.get("/rest/greenhopper/1.0/rapid/charts/sprintreport",
                        {"rapidViewId": board, "sprintId": sprint_id})["contents"]
    except (requests.RequestException, KeyError) as exc:
        warn(f"sprintrapport {sprint_id} niet op te halen ({exc})")
        return None
