Business case: manual → automated regression testing — data extraction & evaluation
Context
We want a data-backed business case for switching manual (regression) testing to
automation. The seed data is Jira story S34-2907 and TestRail run 26442
(both K&F / SAP "Klanten & Facturen"). This plan is a standalone data-extraction +
written-evaluation mini-project — not wired into the FO pipeline. No FO is generated.

I did a full read-only live probe of both APIs first. Key findings that shaped the plan:

Jira changelog is rich. expand=changelog gives every status transition with
timestamp + author. S34-2907 spent 45 days "In testing" (2026-01-19 → 03-05);
5 sprints (spillover), 3 Impediment flags, 20 story points.
Test stages live as subtasks (titles, not a structured field): Testvoorbereiding
Key Users, Bestaalstapel klant factuur (data prep), Testen 1 week (incl), Testen
verzamelklanten, testen P2P — each with its own transition dates.
TestRail re-execution is the manual cost signal. Run 26442: 108 results / 35
tests = 3.1 executions/test (max 9), 12 failed + 4 retest, 4 testers, 17 execution
days. defects field links results → 10 Jira bugs, mean 6.3 days to resolve.
Automation baseline = 0%. custom_automation_type options are 0=None / 1=Ranorex;
all 250 cases in suite 496 are 0. Ranorex is the sanctioned tool → greenfield.
Run frequency (the ROI multiplier): 250 runs all on suite 496 — 76 (2024), 98
(2025), 76 (2026-to-July) ≈ ~100–130 runs/year.
No explicit effort field. Jira worklogs total:0, timespent null on story +
all 7 subtasks, no Tempo plugin, TestRail elapsed on 1/108 results (0/311 across
40 runs), estimate on 0/250 cases.
BUT effort is recoverable from result timestamps (user's insight — probed & confirmed).
Each TestRail result carries created_on + created_by. Sorting a tester's results and
taking in-session gaps (consecutive submissions, capped at 60 min to drop breaks)
yields hands-on execution time: run 26442 heavy testers show median ~7.5–8.3 min,
avg 12 min between results. So per-execution minutes is data-anchored, with the
assumption band reserved for sensitivity — not a blind guess.
Infra note: working Jira base is https://jira.vitens.lan/jira (the /jira
context path). creds.yaml has base_url: https://jira.vitens.lan/ without
/jira — the extractor must append it (or normalise), or every call 404s.
User decisions (locked)
Effort baseline: proxy metrics + sensitivity bands over a per-test-minutes assumption.
Regression corpus: runs in suite 496 that contain regression-titled tests
(titles starting Regressie / matching the W0..→W... process-flow pattern) — a
test-level definition that catches run 26442 and the real practice. Report the qualifying count.
Fallback (user): if that filter proves too thin to be credible, broaden to the
whole testset/run and treat regression as a subset — i.e. report the full suite
as the denominator with the regression-titled slice as a labeled subset, rather than
discarding non-regression runs. The script computes both so the report can show
regression-as-share-of-total.
W-codes are subjects, not just flow steps (user). W010, W040, W100 denote
different subject/process areas (e.g. W040 ≠ W010). Metrics that group by W-code must
treat each code as a distinct subject dimension — break executions / failures /
defects down per W-code, don't collapse them into one "process flow" bucket.
Deliverable: raw data extract (JSON + CSV) plus a written Markdown evaluation
with the ROI model, assumptions, recommendation, and clarifying questions.
Approach
One new standalone script, scripts/testauto_businesscase.py, following the repo's
established build → render → write shape (mirrors scripts/trace_audit.py /
scripts/compare_fo.py), plus JSON and CSV output. Read-only; no writes to Jira/TestRail.

Reuse (do not reinvent)
Creds loading: copy scripts/docaudit.py:_load_creds style (yaml.safe_load,
default _ROOT/"creds.yaml"). Normalise Jira base to include /jira.
Jira client: Bearer header pattern from scripts/adapters/jira.py:102-111 /
source_analyzer._fetch_jira (verify=False, timeout). For changelog use
GET /rest/api/2/issue/{key}?expand=changelog. For batches reuse the
jira_onepager/jira_client.py:_search_issues pattern (issuekey in (...) + per-key
fallback) — but write a proper changelog histories[].items[] walker, which does
not exist anywhere yet (jira_client._item_to_story only grabs last_modified_by).
TestRail client: Basic auth + verify_ssl pattern from
source_analyzer._fetch_testrail / _testrail_section_map. Endpoints:
get_run/{id}, get_tests/{id}, get_results_for_run/{id} (new to the repo — no
code calls get_results*), get_statuses, get_sections/{proj}?suite_id=,
get_runs/{proj}?suite_id= (paginate; DC returns {runs:[...]} or a bare list —
handle both, as the probes did).
Output writers: three-function split like trace_audit.py (build_* → render_md → write_*); add a csv.writer step alongside the JSON.
Metrics the script computes
A. Jira lifecycle (per story + subtasks), from changelog

Status-transition timeline; time-in-status per state (esp. "In testing", "In Progress").
Test-stage durations inferred from subtask titles + their transition dates.
Spillover signal: sprint-change count; Impediment/Flagged periods; story points.
B. TestRail execution (the manual-cost core), per qualifying run

Tests, total results, executions-per-test (mean/max/distribution) = re-run tax.
Status spread (passed/failed/retest/blocked), first-pass rate (% tests green on
first result), rework loops.
Testers involved, distinct execution days, calendar span.
Per-W-code subject breakdown (parse W\d+ from titles): executions, failures and
linked defects per subject area, so heavy/fragile subjects are visible.
Effort proxy from result timestamps (user's method). Per tester, sort created_on,
take in-session gaps (consecutive results, cap 60 min) → median/avg minutes-per-execution
total hands-on hours for the run. Report the derived per-execution minutes as the
data anchor for the effort model below (run 26442 ≈ 7.5–12 min median). Also expose
run created_on/completed_on/updated_on as calendar bounds.
Defects: defects refs → Jira; count, and mean/median resolution time from Jira
changelog (created → resolutiondate).
C. Corpus / frequency (regression-titled-test runs in suite 496)

Qualifying run count + runs/year; aggregate tests executed; total manual
executions/year (the multiplier); automation adoption = share of cases with
custom_automation_type == 1 (currently 0%).
E. Cross-system lifecycle timeline (user's framing — PoC validated)
Weave Jira status transitions (story + subtasks), TestRail result timestamps, and bug
open/resolve events into one chronological event stream, then decompose into phases.
The value narrative is the gap between calendar duration (mostly waiting) and net
active person-time. Validated on S34-2907/26442:

Phase decomposition (each with a start→end duration):
Planning / test-data prep — subtask "In Progress" (e.g. Testvoorbereiding Key
Users, Bestaalstapel klant factuur) → first TestRail result. ≈41 days here.
Execution — first→last TestRail result window. ≈31 days. Net active time via
the (B) session-gap method.
Defect loop — per failed result: linked bug opened → resolved → retest result
passes. Interleaved in the stream; this is what stretches the tail (a bug open
19 days blocks closure).
Closure — last passing result / final subtask Resolved → story Resolved.
Calendar vs active: report end-to-end calendar span (≈78 days In Progress→Resolved)
beside net active person-hours (≈7h across 4 testers) and the ratio (~1% of an
8h/day calendar) — the headline waste/lead-time signal automation attacks.
"Finish" semantics (user): a test's finish = timestamp its final result flips to
passed; the story's finish = In testing → Resolved. Compute both.
Testers × time: distinct tester count per phase + summed active time, so "net
testing effort" is person-hours, not wall-clock.
Honest caveat carried into the report: net active time is a lower bound (gap
method misses isolated results and setup/analysis); calendar durations are wall-clock
and include non-testing waits. Automation's modelled saving spans both — execution
hours and compressed lead time — stated as separate lines, not conflated.
Output: an ordered events CSV/JSON (ts · system · entity · event · phase) so the
timeline can be charted, plus the phase-duration summary table in the report.
D. Effort model (timestamp-anchored + sensitivity) — no explicit hours field, but the
result-timestamp proxy (B) supplies an empirical per-execution minutes anchor:

annual_manual_effort = total_executions/year × minutes_per_execution, where
minutes_per_execution is centred on the timestamp-derived value (~8–12 min from
run 26442) and swept over a band (e.g. anchor ×0.75 / ×1.5 / ×2, to cover think-time and
setup the gap method understates) → low/mid/high hours. Band is sensitivity, not a guess.
Automation: one-time build (cases × build-min/case band) + annual maintenance (%/yr band).
Output break-even runs & payback period as a table across the bands — never a
single fabricated number. Clearly label every assumption as an input to confirm.
Files
New: scripts/testauto_businesscase.py (extractor + evaluator; argparse CLI:
--jira S34-2907 --run 26442 --suite 496 --project 58 --out-dir output/).
New outputs: output/testauto_businesscase_<ts>.json,
output/testauto_businesscase_<ts>.csv (per-run + per-defect tables),
output/testauto_businesscase_<ts>_timeline.csv (ordered cross-system event stream:
ts · system · entity · event · phase — chartable),
output/testauto_businesscase_<ts>_report.md (written evaluation +
recommendations + open questions).
No changes to existing pipeline files. Optionally note the /jira base-URL
quirk in creds.yaml.example, but only if the user wants it.
Verification (end-to-end, live)
uv run python scripts/testauto_businesscase.py --jira S34-2907 --run 26442 and
confirm it writes the 3 artifacts without error.
Spot-check against the probed ground truth: story "In testing" = 45 days; run 26442 =
108 results / 35 tests, 12 failed, 10 defects, mean defect resolution 6.3 days;
automation adoption 0%.
Confirm the corpus step reports a sane qualifying-run count for suite 496 and a
runs/year figure near ~100–130. If the regression-titled count is too thin to be
credible, apply the fallback: report whole-suite totals with the regression slice as
a labeled subset (script computes both) — do not narrow the case to a handful of runs.
Confirm the timestamp effort proxy reproduces the probed anchor (run 26442 median
~7.5–8.3 min between results) and that the ROI band is centred on it.
Confirm per-W-code breakdown separates subjects (W010/W040/W100 as distinct rows).
5b. Confirm the lifecycle timeline reproduces the PoC phases: ≈41d prep, ≈31d execution,
≈78d In-Progress→Resolved calendar span, ≈7 net person-hours / 4 testers, and the
defect-loop events interleave (bug opened→resolved→retest) in the ordered stream.
Sanity-check the CSV opens as a table and the Markdown ROI bands render.
Confirm graceful degradation: a bad key / offline TestRail warns and continues
(mirrors the repo's best-effort fetch convention).
Open questions to raise in the report (for the user / stakeholders)
Per-execution manual minutes — the result-timestamp proxy says ~8–12 min hands-on; does
that match Key Users' felt experience, or does real per-test time (incl. setup/analysis
the gap method can't see) run materially higher? This validates the model's central input.
Ranorex build effort per case & expected annual maintenance % — do we have a pilot data point?
Is suite 496's ~100–130 runs/yr representative of the go-forward regression cadence,
or was 2024–25 inflated by the SAP migration?
Should defect-prevention value (bugs caught earlier by automation) be monetised, or
keep the case purely on execution-effort savings?