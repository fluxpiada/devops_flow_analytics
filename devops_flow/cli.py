"""devops-flow <PROJECT|URL> — flow- en sprintmetrics van een Jira-project naar Excel."""

from __future__ import annotations

import argparse
import calendar
import re
from datetime import datetime
from pathlib import Path

from . import excel, jira, metrics


def project_key(arg: str) -> str:
    """Sleutel uit .../browse/MOD, .../browse/MOD-123, .../projects/MOD of MOD."""
    tail = arg.strip().rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    m = re.match(r"[A-Z][A-Z0-9_]+", tail.upper())
    if not m:
        raise SystemExit(f"Kan geen projectsleutel afleiden uit {arg!r} — "
                         f"verwacht bv. MOD of https://jira.vitens.lan/jira/browse/MOD.")
    return m.group(0)


def months_ago(now: datetime, months: int) -> datetime:
    """Zelfde dag, `months` maanden terug; klemt op de maandlengte."""
    year, month = divmod(now.year * 12 + now.month - 1 - months, 12)
    last_day = calendar.monthrange(year, month + 1)[1]
    return now.replace(year=year, month=month + 1, day=min(now.day, last_day))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project", help="Projectsleutel of Jira-URL, bv. MOD")
    ap.add_argument("--months", type=int, default=6, help="Venster (default 6)")
    ap.add_argument("--refresh", action="store_true", help="Negeer de cache")
    ap.add_argument("--board", type=int, help="Scrumboard-id (default: het eerste)")
    ap.add_argument("--creds", help="Pad naar creds.yaml")
    ap.add_argument("--out-dir", default="output")
    args = ap.parse_args()

    project = project_key(args.project)
    now = datetime.now()
    since = months_ago(now, args.months)
    out = Path(args.out_dir) / project
    client = jira.JiraClient(jira.load_creds(args.creds))

    print(f"→ {project}, {args.months} maanden (vanaf {since:%Y-%m-%d})")
    wf = metrics.Workflow(jira.statuses(client, project))
    issues = jira.fetch_issues(client, project, since, out / "cache.json", args.refresh)
    wf.learn_order(issues)
    board, sprints = jira.closed_sprints(client, project, since, args.board)
    reports = [jira.sprint_report(client, board, s["id"]) for s in sprints]
    if sprints:
        print(f"  board {board}: {len(sprints)} afgesloten sprints in het venster")

    items, tis = metrics.items_table(issues, wf, now)
    daily = metrics.daily_table(issues, wf, since.date(), now)
    sprint_rows = metrics.sprint_table(sprints, reports, items)
    stream = metrics.value_stream(tis, wf, skip={r["key"] for r in items if r["backfilled"]})
    if wf.unknown:
        jira.warn(f"onbekende status-ids (tellen als To Do): {', '.join(sorted(wf.unknown))}")

    out.mkdir(parents=True, exist_ok=True)
    paths = [
        excel.write_csv(out / "items.csv", *excel.as_rows(items)),
        excel.write_csv(out / "time_in_status.csv", *excel.as_rows(tis)),
        excel.write_csv(out / "daily.csv", *daily),
        excel.write_csv(out / "value_stream.csv", *excel.as_rows(stream[0])),
    ]
    if sprint_rows:
        paths.append(excel.write_csv(out / "sprints.csv", *excel.as_rows(sprint_rows)))
    paths.append(excel.write_workbook(out / f"dashboard_{project}.xlsx", project, items,
                                      tis, daily, sprint_rows, since.date(), stream))

    done = [r for r in items if r["done"] and not r["backfilled"]]
    print(f"\n✓ {len(items)} issues ({len(done)} afgerond), "
          f"{len(sprint_rows)} sprints → {out}")
    for p in paths:
        print(f"  {p.name}")


if __name__ == "__main__":
    main()
