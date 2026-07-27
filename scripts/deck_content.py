#!/usr/bin/env python3
"""Tussenstap tussen analyse-JSON en PowerPoint: feiten afleiden → tekst → checkpoint.

Waarom deze module bestaat: de dektekst stond eerder hard in build_mgmt_deck.py.
Bij het renderen van een ándere run bleven de oude cijfers staan, zodat het deck
zelfverzekerd getallen toonde die nergens uit volgden. Alles wat het deck beweert
komt nu uit `facts()`; wat níét uit Jira/TestRail af te leiden is staat expliciet
in ASSUMPTIONS en wordt in het deck als aanname gelabeld.

    build_mgmt_deck.py --emit-content   # → output/deck_content.md  (bewerk vrij)
    build_mgmt_deck.py --content <md>   # → .pptx uit die tekst
"""

from __future__ import annotations

import re
from datetime import date, datetime

# Waarden die NIET uit Jira/TestRail volgen. Redactionele keuzes en schattingen —
# pas ze hier aan, of bewerk ze in het gegenereerde deck_content.md.
ASSUMPTIONS = {
    "saved_days_per_round": 13,      # bandbreedte 7–26; niet gemeten
    "saved_days_band": "7–26",
    "payback_rounds": 5,
    "freed_capacity": "1 tester",
    "bug_cost_weeks": 2,             # ±1 week fixen + ±1 week wachten op hertest
    # get_users geeft 403; rollen zijn niet uit de data af te leiden.
    "tester_role": "systeemtesters (aanname; BAT/key-usertests niet in TestRail)",
}

_NL_MONTHS = ("jan", "feb", "mrt", "apr", "mei", "jun",
              "jul", "aug", "sep", "okt", "nov", "dec")


def _r(x) -> int:
    return int(round(x or 0))


def _period_label(first: str | None, last: str | None) -> str:
    """'jan–feb 2026' / 'dec 2025' uit de eerste en laatste resultaatdatum."""
    if not first or not last:
        return "periode onbekend"
    a, b = datetime.fromisoformat(first), datetime.fromisoformat(last)
    ma, mb = _NL_MONTHS[a.month - 1], _NL_MONTHS[b.month - 1]
    if a.year != b.year:
        return f"{ma} {a.year}–{mb} {b.year}"
    return f"{ma}–{mb} {b.year}" if ma != mb else f"{ma} {b.year}"


def _workday_span(a: datetime, b: datetime) -> float:
    """Aantal werkdagen (ma–vr) dat het venster [a, b] beslaat, beide einddagen
    meegeteld. Bewust een KALENDER-telling voor het tijdlijnlabel, NIET de
    fractionele actieve-werkdag-maat van de engine (_workdays daar) — vandaar
    een eigen naam."""
    days, cur = 0, a.date()
    while cur <= b.date():
        if cur.weekday() < 5:
            days += 1
        cur = date.fromordinal(cur.toordinal() + 1)
    return float(days)


def _rows_to_pipe(rows: list[list]) -> str:
    """Tabelrijen (lijst-van-lijsten) → pipe-tekst voor het checkpoint."""
    return "\n".join("|".join(str(c) for c in row) for row in rows)


def _clean_step(name: str) -> str:
    """Bloklabel voor de tijdlijn: verwijder de verduidelijkende staarten."""
    return name.replace(" (development)", "").replace(" / oplevering", "")


def _vsm_rows(steps: list[dict]) -> str:
    """Waardestroom-stappen → pipe-rijen voor het checkpoint, één stap per rij:
    naam | actieve dagen | wachtdagen | ca_pct (of -) | aanname-marker (of leeg).
    Zo staat élk cijfer en label op de tijdlijndia in deck_content.md."""
    rows = []
    for s in steps:
        ca = str(s["ca_pct"]) if s.get("ca_pct") is not None else "-"
        marker = "*" if "aanname" in (s.get("basis") or "").lower() else ""
        rows.append([_clean_step(s["step"]), _r(s["active_days"]),
                     _r(s["wait_days"]), ca, marker])
    return _rows_to_pipe(rows)


def _tester_table(per_tester: list[dict], tot_res: int) -> list[list]:
    """Geanonimiseerde werkverdeling; staart wordt samengevoegd tot één rij."""
    rows: list[list] = [["Tester", "Testdagen", "Aandeel"]]
    for lbl, v in zip("AB", per_tester[:2]):
        rows.append([lbl, v["active_days"],
                     f"{_r(100 * v['results'] / tot_res)}% van de uitvoeringen"])
    rest = per_tester[2:]
    if rest:
        label = " + ".join("CDEFGH"[i] for i in range(len(rest))) if len(rest) < 7 \
            else f"overige {len(rest)}"
        rows.append([label, sum(v["active_days"] for v in rest),
                     f"{_r(100 * sum(v['results'] for v in rest) / tot_res)}%"])
    return rows


def facts(data: dict) -> dict:
    """Elk getal dat het deck noemt, afgeleid uit de analyse-JSON."""
    rm = data["testrail_run"]
    ep = rm["effort_proxy"]
    vs = data["value_stream"]
    tot, auto = vs["totals"], vs["automated_scenario"]
    corpus = data.get("corpus") or {}
    cp = data.get("change_pressure") or {}
    roi = data.get("roi_model") or {}
    link = data.get("source_link") or {}

    per_tester = sorted(ep["per_tester"].values(), key=lambda v: -v["results"])
    tot_res = sum(v["results"] for v in per_tester) or 1
    # active_test_days wordt door de engine afgeleid; oudere JSONs missen het.
    testdagen = ep.get("active_test_days")
    if testdagen is None:
        testdagen = sum(v["active_days"] for v in per_tester)

    window_wd = 0.0
    if rm.get("first_result") and rm.get("last_result"):
        window_wd = _workday_span(datetime.fromisoformat(rm["first_result"]),
                                  datetime.fromisoformat(rm["last_result"]))

    exec_step = next((s for s in vs["steps"] if s["step"] == "Testuitvoering"), {})

    # Regressie-uitvoeringen per jaar vs wijzigingstests, uit de wijzigingsdruk.
    nr = cp.get("non_regression_by_year") or {}
    non_regr = [v["non_regression_executed"] for v in nr.values()] or [0]
    regr = [v["regression_executed"] for v in nr.values()] or [0]

    steps = cp.get("per_step") or {}
    hot = sorted(steps.items(), key=lambda kv: -kv[1].get("jira_issues", 0))[:3]

    n_cases = corpus.get("cases_regression_titled") or 0
    bands = ((roi.get("assumptions") or {}).get("build_hours_per_case_bands")
             or [2, 4, 8])

    # Een ronde van een paar dagen in "0 weken" uitdrukken leest als een fout;
    # onder de twee weken telt het deck in werkdagen.
    wd = _r(window_wd)
    if window_wd >= 10:
        window_label = f"{_r(window_wd / 5)} weken"
        window_sub = f"doorlooptijd ({wd} werkdagen)"
    else:
        window_label = f"{wd} werkdag" + ("en" if wd != 1 else "")
        window_sub = "doorlooptijd (eerste → laatste resultaat)"

    # De werkverdeling is alleen een verhaal als er meer dan één tester was.
    # "Systeemtester" is een aanname (zie ASSUMPTIONS.tester_role): rollen zijn
    # niet opvraagbaar en business-acceptatietests zitten niet in TestRail.
    n_testers = ep["testers"]
    top2 = _r(100 * sum(v["results"] for v in per_tester[:2]) / tot_res)
    if n_testers <= 1:
        split_sentence = "Eén systeemtester deed alle uitvoeringen — geen team."
    elif n_testers == 2:
        split_sentence = f"Twee systeemtesters deelden het werk ({top2}% samen)."
    else:
        split_sentence = (f"Geen team van {n_testers} systeemtesters: twee "
                          f"mensen deden {top2}% van de uitvoeringen.")

    # De-facto regressie (cross-run pass→rerun-analyse); ontbreekt in oudere
    # analyse-JSONs — dan blijft de dektekst ongewijzigd.
    dfr = corpus.get("defacto_regression") or {}

    return {
        # koppeling
        "story_key": link.get("story_key") or data["jira_lifecycle"].get("key", "?"),
        "run_id": rm["run_id"],
        "run_name": rm.get("name") or "",
        "linked": link.get("linked", None),
        # de ronde
        "tests": rm["tests"],
        "results": rm["results"],
        "exec_per_test": rm["executions_per_test"]["mean"],
        "first_pass_pct": _r(100 * rm["first_pass_rate"]),
        "testers": ep["testers"],
        "testdagen": _r(testdagen),
        "exec_days": rm["execution_days"],
        "defects": rm["defect_resolution_days"]["count"],
        "defect_days": rm["defect_resolution_days"]["mean"],
        "period": _period_label(rm.get("first_result"), rm.get("last_result")),
        "window_workdays": wd,
        "window_label": window_label,
        "window_sub": window_sub,
        "idle_days": _r(exec_step.get("wait_days", 0)),
        "split_sentence": split_sentence,
        "tester_table": _tester_table(per_tester, tot_res),
        # waardestroom
        "lead_time": _r(tot["lead_time_days"]),
        "wait_days": _r(tot["wait_days"]),
        "flow_pct": tot["flow_efficiency_pct"],
        "auto_lead_time": _r(auto["lead_time_days"]),
        "vsm_rows_nu": _vsm_rows(vs["steps"]),
        "vsm_rows_straks": _vsm_rows(auto["steps"]),
        "vsm_has_assumption": any("aanname" in (s.get("basis") or "").lower()
                                  for s in vs["steps"]),
        # suite / historie
        "cases_total": corpus.get("cases_total"),
        "cases_automated": corpus.get("cases_automated"),
        "cases_regression": n_cases,
        "cases_defacto": dfr.get("cases_defacto"),
        "defacto_overlap": dfr.get("overlap_titled_defacto"),
        "non_regr_min": min(non_regr), "non_regr_max": max(non_regr),
        "regr_min": min(regr), "regr_max": max(regr),
        "years_scanned": len(nr),
        # wijzigingsdruk
        "missing_steps": cp.get("steps_missing_from_case_study_run") or [],
        "steps_total": len(steps),
        "hotspots": [k for k, _ in hot],
        # automatiseren
        "build_days_low": _r(n_cases * bands[1] / 8) if n_cases else None,
        "build_days_high": _r(n_cases * bands[-1] / 8) if n_cases else None,
        **{f"a_{k}": v for k, v in ASSUMPTIONS.items()},
    }


def default_content(f: dict) -> dict[str, str]:
    """Standaard dektekst, volledig opgebouwd uit `facts`."""
    suite = ("" if not f["cases_total"] else
             f"  - Van de {f['cases_total']:,} testgevallen is er "
             f"{f['cases_automated']} geautomatiseerd.\n".replace(",", "."))
    hist = ("" if not f["years_scanned"] else
            f"  - In {f['years_scanned']} jaar testhistorie zijn er per jaar "
            f"{f['regr_min']}–{f['regr_max']} regressietests écht uitgevoerd.\n"
            + (f"  - Daarnaast functioneerden {f['cases_defacto']} testgevallen "
               f"de facto als regressietest (opnieuw uitgevoerd na eerder "
               f"slagen) — zonder dat label.\n"
               if f.get("cases_defacto") else ""))
    hist_note = (f"+ {f['years_scanned']} jaar testhistorie" if f["years_scanned"]
                 else "zonder historie-scan (--skip-corpus)")
    build = ("40–80" if f["build_days_low"] is None else
             f"{f['build_days_low']}–{f['build_days_high']}")
    miss = ", ".join(f["missing_steps"])
    hot = ", ".join(f["hotspots"])

    return {
        "titel.kop": "Regressietesten automatiseren — incassoproces",
        "titel.sub": "Beslisvoorstel, onderbouwd met gemeten test- en Jira-data",
        "titel.voet": (f"Gemeten: run {f['run_id']} ({f['story_key']}, "
                       f"{f['period']}) {hist_note}"),

        "situatie.kop": "De situatie",
        "situatie.bullets":
            "- **We gaan het incassoproces vernieuwen en vereenvoudigen.**\n"
            "  - Om veilig te kunnen wijzigen willen we elke week (of elke sprint) "
            "een volledige regressietest draaien.\n"
            f"- **Eén handmatige regressieronde kostte {f['testdagen']} testdagen "
            f"en besloeg {f['window_label']}.**\n"
            f"  - Gemeten aan {f['story_key']}: {f['tests']} testgevallen, "
            f"{f['testers']} systeemtester(s), {f['period']}.\n"
            "- **Wekelijks handmatig testen kan dus simpelweg niet.**\n"
            + hist + suite,

        "tijdlijn.kop": "Tijdlijn: waar gaat de tijd heen?",
        "tijdlijn.sub": "Blauw = werk · rood klokje = wachten · alles in werkdagen",
        "tijdlijn.nu": "NU — handmatig testen",
        "tijdlijn.straks": "STRAKS — met geautomatiseerde regressie",
        # Elke tijdlijnstap staat hier als rij (naam|werk|wacht|ca%|*): bewerk
        # ze en het deck volgt. Marker * = deels aanname (zie rapport §6b).
        "tijdlijn.rijen_nu": f["vsm_rows_nu"],
        "tijdlijn.rijen_straks": f["vsm_rows_straks"],
        "tijdlijn.voet": ("* deels een aanname — zie het rapport §6b (kolom Basis)"
                          if f["vsm_has_assumption"] else ""),
        "tijdlijn.bullets":
            f"- **Nu: {f['lead_time']} werkdagen van bouw tot oplevering — "
            f"{f['wait_days']} daarvan is wachten. Straks: {f['auto_lead_time']} "
            f"werkdagen.**\n"
            "- De grootste winst zit in de testuitvoering en de hertestlus: van "
            "dagen wachten naar uren.\n",

        "ronde.kop": "Wat kost één handmatige regressieronde?",
        "ronde.sub": (f"Gemeten: {f['story_key']} / run {f['run_id']} — "
                      f"{f['tests']} testgevallen, {f['results']} uitvoeringen, "
                      f"{f['period']}"),
        "ronde.kpi1": f"{f['window_label']}|{f['window_sub']}",
        "ronde.kpi2": f"{f['testdagen']} testdagen|totale inzet — "
                      f"{f['testers']} systeemtester(s)",
        "ronde.kpi3": f"{f['idle_days']} werkdagen|alles stil: wachten op bugfixes",
        "ronde.kpi4": (f"{f['defects']} bugs|gevonden"
                       + (f"; gemiddeld {f['defect_days']} dagen open"
                          if f["defect_days"] else "")),
        "ronde.tabelkop": "Werkverdeling (geanonimiseerd):",
        # De werkverdelingstabel als bewerkbare pipe-rijen (kop + testers), zodat
        # óók deze cijfers via het checkpoint lopen i.p.v. live uit de JSON.
        "ronde.tabel": _rows_to_pipe(f["tester_table"]),
        "ronde.bullets":
            f"- **{f['split_sentence']}**\n"
            f"- Elke test is gemiddeld {f['exec_per_test']}× uitgevoerd "
            f"(falen → bugfix → opnieuw); {f['first_pass_pct']}% was in één keer goed.\n"
            f"- Testen zelf is snel; het meeste van {f['window_label']} is "
            "wachten en coördineren.\n",

        "rekensom.kop": "De rekensom op één A4",
        "rekensom.sub": "Alles in testdagen — aannames staan gemarkeerd",
        "rekensom.kopregel": "|Vraag|Antwoord",
        "rekensom.rows":
            f"1|Wat kost één ronde handmatig?|{f['testdagen']} testdagen werk en "
            f"{f['window_label']} doorlooptijd (gemeten)\n"
            "2|Hoe vaak willen we een ronde?|elke week — of minimaal elke sprint "
            "(3 weken)\n"
            f"3|Wat kost automatiseren (eenmalig)?|{build} dagen bouwen "
            f"({f['cases_regression']} testgevallen), plus onderhoud\n"
            f"4|Wat levert elke ronde dan op?|±{f['a_saved_days_per_round']} "
            f"testdagen bespaard (aanname, band {f['a_saved_days_band']})\n"
            f"5|Wanneer terugverdiend?|na ±{f['a_payback_rounds']} rondes "
            f"(aanname) — bij wekelijks draaien binnen een kwartaal\n",
        "rekensom.kpi1": "binnen 1 kwartaal|terugverdiend bij wekelijks draaien "
                         "(aanname)",
        "rekensom.kpi2": f"{f['a_freed_capacity']} vrijgespeeld|elke ronde — voor "
                         f"het verbeterwerk zelf (aanname)",
        "rekensom.voet":
            "Let op: automatiseren van alléén de huidige praktijk loont niet — er "
            "wordt nu nauwelijks geregresseerd. De winst zit in wat het mogelijk "
            "maakt. Regels 4 en 5 zijn aannames, geen metingen.",

        "waarom.kop": "Waarom nu beslissen?",
        "waarom.bullets":
            "- **Het proces wijzigt continu — en juist dan is een vangnet nodig.**\n"
            f"  - Per jaar draaien er {f['non_regr_min']} tot {f['non_regr_max']} "
            "tests voor wijzigingen; een regressie-vangnet daaromheen ontbreekt.\n"
            + (f"- **Bugs zijn nu traag en duur.**\n"
               f"  - De {f['defects']} bugs uit deze ronde stonden gemiddeld "
               f"{f['defect_days']} dagen open. Geautomatiseerd is de hertest er "
               f"binnen een dag.\n" if f["defects"] else "")
            + (f"- **De gemeten ronde dekte niet alles.**\n"
               f"  - {len(f['missing_steps'])} van de {f['steps_total']} "
               f"processtappen ({miss}) zaten er niet in — het vangnet heeft nu "
               f"al gaten.\n" if miss else "")
            + (f"- **De drukste stappen zijn bekend: {hot}.**\n"
               "  - Daar zitten de meeste wijzigingen én de meeste bugs — dáár "
               "begint de pilot.\n" if hot else ""),

        "besluit.kop": "Gevraagd besluit",
        "besluit.bullets":
            f"- **1.  Start een automatiseringspilot op de drukste processtappen "
            f"({hot}).**\n"
            "  - Meet in de pilot de echte bouw- en onderhoudsdagen — dat vervangt "
            "de aannames in de rekensom.\n"
            "- **2.  Kies de testcadans: elke week of elke sprint.**\n"
            "  - Dit bepaalt de terugverdientijd (kwartaal vs. jaar).\n"
            "- **3.  Registreer voortaan de testtijd in TestRail.**\n"
            "  - Kost niets, en maakt de volgende beslissing meetbaar in plaats "
            "van geschat.\n",
        "besluit.voet": ("Bijlage beschikbaar: volledige data-analyse (rapport + "
                         "cijfers), reproduceerbaar uit Jira en TestRail. "
                         "Business-acceptatietests (key users) zitten niet in "
                         "de TestRail-data en vallen buiten deze metingen."),
    }


# ── checkpoint-formaat ───────────────────────────────────────────────────────


def to_md(content: dict[str, str], f: dict) -> str:
    head = [
        "<!-- Bewerkbaar tussenbestand voor het managementdeck.",
        f"     Bron: {f['story_key']} / TestRail-run {f['run_id']} ({f['period']}).",
        "     Elke '## sleutel' hoort bij één tekstblok in het deck.",
        "     Renderen:  build_mgmt_deck.py --content <dit bestand>",
        "     Opnieuw genereren (overschrijft je bewerkingen):  --emit-content -->",
        "",
    ]
    for key, val in content.items():
        head.append(f"## {key}")
        head.append(val.rstrip("\n"))
        head.append("")
    return "\n".join(head) + "\n"


def parse_md(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    key, buf = None, []
    for line in text.splitlines():
        m = re.match(r"^## ([\w.]+)\s*$", line)
        if m:
            if key:
                out[key] = "\n".join(buf).strip("\n")
            key, buf = m.group(1), []
        elif key is not None:
            buf.append(line)
    if key:
        out[key] = "\n".join(buf).strip("\n")
    return out


def bullets(block: str) -> list[tuple[int, str, bool]]:
    """'- **vet**' → niveau 0 vet · '  - tekst' → niveau 1 · '- tekst' → niveau 0."""
    items = []
    for line in block.splitlines():
        if not line.strip():
            continue
        level = 1 if line.startswith(("  -", "\t-")) else 0
        txt = line.strip().lstrip("-").strip()
        bold = txt.startswith("**") and txt.endswith("**")
        items.append((level, txt.strip("*").strip(), bold))
    return items


def pipe_rows(block: str) -> list[list[str]]:
    return [[c.strip() for c in ln.split("|")]
            for ln in block.splitlines() if ln.strip()]
