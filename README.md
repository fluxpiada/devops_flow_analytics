# devops_flow — business case testautomatisering

Meet doorlooptijd, inspanning en flow-efficiëntie van ontwikkel- en testwerk op
basis van wat Jira en TestRail al registreren — géén urenregistratie nodig — en
zet dat om in een onderbouwd beslisrapport (Markdown + Word) en een
managementdeck (PowerPoint).

## De vraag, en het antwoord

**Vraag:** moeten we het (regressie)testen van het incassoproces automatiseren?

**Antwoord in drie zinnen.** Eén handmatige regressieronde kost tientallen
persoonstestdagen en beslaat weken, terwijl die uren nu nauwelijks gemaakt
worden — regressie draait zelden. Het team wil het proces refactoren en moet
daarvoor wekelijks kunnen regressietesten, wat handmatig fysiek onmogelijk is.
De business case is dus geen besparingscase op bestaande uren maar een
**enabler-case**: automatisering maakt de kwaliteitsborging mogelijk die de
verbouwing van het incassoproces vereist.

Elk getal in het rapport is herleidbaar tot Jira of TestRail, of expliciet als
aanname gelabeld. Het rapport (`_report.md` / `.docx`) is het hoofddocument; het
deck is de management-samenvatting.

## Begrippen (kort — het rapport definieert ze voluit, bron: ISTQB Glossary)

- **Regressietest** — opnieuw testen ná een wijziging om te bewaken dat wat
  wérkte blíjft werken.
- **Hertest / confirmatietest** — een gefaalde test opnieuw draaien ná de
  bugfix. Dit is géén regressietest.
- **Wijzigingstest (non-regressie)** — valideert dat nieuwe/gewijzigde
  functionaliteit werkt; bewijst niet dat het bestaande intact bleef.
- **De-facto regressietest** — eigen operationele term: een testgeval dat
  opnieuw is uitgevoerd terwijl het eerder slaagde (pass→rerun) —
  regressiegedrag zonder het label.
- **Persoonstestdag** — één tester, één werkdag testen. De rekeneenheid.
- **Flow-efficiëntie** — actieve tijd gedeeld door doorlooptijd (Lean/SAFe).

## Methode in het kort

De analyse is een keten; elke stap staat op zichzelf en draagt zijn eigen
verantwoording (rapport §11, `docs/technisch-ontwerp.md`):

1. **Koppeling** — de story wordt uit de `refs`/naam van de TestRail-run
   afgeleid; klopt een opgegeven `--jira` niet, dan stopt het script (anders is
   het resultaat consistent maar onjuist).
2. **Jira-levenscyclus** — statusovergangen van story + subtaken uit de
   changelog → tijd-per-status en fasegrenzen.
3. **TestRail-executie** — her-executies per test, first-pass-rate, en een
   effort-proxy uit de tijdstempels tussen resultaten (er zijn geen uren
   geregistreerd).
4. **Corpus + cache** — één suite-brede scan van alle runs (frequentie,
   automatiseringsgraad), gecachet zodat de analyse daarna offline draait.
5. **De-facto regressie** — cross-run pass→rerun-detectie: maakt de ongelabelde
   regressiepraktijk zichtbaar.
6. **Waardestroom** — per stap actieve tijd vs wachttijd → flow-efficiëntie, met
   een geautomatiseerd scenario ernaast.
7. **ROI-model** — gevoeligheidsbanden i.p.v. schijnprecisie; een doelcadans
   (wekelijks / per sprint) als beslissend scenario.

## Artefacten per run

Alles landt in **`output/<JIRA-KEY>/`** (één onderzoek = één map):

- `…_report.md` en `…_report.docx` — het beslisrapport (Word via pandoc, indien
  aanwezig).
- `…json` — alle cijfers, herbruikbaar.
- CSV's — `runs`, `defects`, `timeline`, `wsteps`, `devtest`, en (met corpus)
  `defacto_regression`.
- met `--deck`: `deck_content.md` (bewerkbaar checkpoint) +
  `testauto_businesscase_mgmt.pptx`.

## Gebruik

```bash
uv sync

# analyse van één testrun (snel, zonder historie-scan)
uv run python scripts/testauto_businesscase.py --run 26442 --skip-corpus

# volledig: frequentie-historie van de hele suite
# (~7 min de eerste keer; daarna seconden uit de corpus-cache)
uv run python scripts/testauto_businesscase.py --run 26442

# alles in één commando: data + rapport + Word + deck
uv run --with python-pptx python scripts/testauto_businesscase.py --run 26442 --deck

# managementdeck los uit de laatste analyse (bewerk-checkpoint → render)
uv run --with python-pptx python scripts/build_mgmt_deck.py --emit-content
uv run --with python-pptx python scripts/build_mgmt_deck.py --content output/<KEY>/deck_content.md
```

### Andere dataset dan het incassoproces

De tool is niet aan de incasso-seed gebonden:

| Wat je wilt | Optie |
|---|---|
| Andere story/run | `--jira KEY --run ID` (of alleen `--run`, story uit de refs) |
| Andere workflow-statusnamen | `--status-dev "In Progress" --status-test "In testing"` |
| Andere projecten voor wijzigingsdruk | `--jql-projects "S34, KFDO"` (default: prefix van de story) |

De W-code-herkenning voor processtappen is incasso-specifiek; voor een ander
domein blijven die tabellen leeg en staat de rest gewoon.

### Handige opties

| Wat je wilt | Optie |
|---|---|
| Historie-scan overslaan | `--skip-corpus` |
| Corpus-cache negeren en vers scannen | `--refresh-corpus` |
| Ander cachebestand | `--corpus-cache PATH` |
| Drempel "terugkerende case" (de-facto) | `--recurrence-min 3` |
| Portfolio-analyse via een epic | `--epic KFDO-123` |
| Historie-scan beperken | `--max-runs 20` |
| Ander pad naar credentials | `--creds ../fo_doc_gen/creds.yaml` |
| Doorgaan zonder Jira-koppeling | `--allow-unlinked` |

De corpus-cache is suite-gebonden (`output/corpus_cache_p<project>_s<suite>.json`)
en wordt door elke story op die suite gedeeld. Word-export vraagt `pandoc`;
ontbreekt dat, dan print het script het handmatige commando
(`pandoc <report>.md --from gfm -o <report>.docx`) en gaat door.

Het deck komt volledig uit `deck_content.md`: élke tekst, tabel en tijdlijnstap
staat als bewerkbare regel in dat checkpoint. Bewerk het en render met
`--content`; niets zit meer hardcoded in de renderer.

## Flow-analyse per project

Naast de business case per story zit er een **projectbrede flow-analyse** in de
repo: hoe lang blijft werk in een Jira-project hangen in *To Do*, *In Progress*
en *Done*, welke losse statussen kosten die tijd, en verbetert dat per sprint?
Een cumulative-flow-diagram-vraag, beantwoord uit de changelog — read-only en
zonder urenregistratie.

```bash
# venster is standaard 6 maanden; interactief biedt hij 12 aan
uv run python scripts/jira_flow_analysis.py \
    --jira-url https://jira.vitens.lan/jira/browse/MOD

# niet-interactief, expliciet venster, verse fetch
uv run python scripts/jira_flow_analysis.py --project MOD --months 12 --refresh
```

Het venster wordt **naar sprintgrenzen gesnapt**: alleen afgeronde sprints die
volledig binnen de gevraagde periode vallen tellen mee. Bij een sprint die aan
het eind van het venster wordt afgekapt tellen namelijk alleen de issues mee die
er vóór de knip al klaar waren; het tragere werk dat erna afrondde valt buiten
beeld en trekt de gemeten doorlooptijd van die randperiode omlaag. Vandaar dat
het venster krimpt naar de echte sprintgrenzen. Het rapport toont zowel het
gevraagde als het gebruikte venster.

Alles is in **werkdagen** — weekenden én Nederlandse landelijke feestdagen
tellen niet mee (op MOD scheelt dat ruim 2 dagen per issue). De kop is de
**mediaan**: de helft van de issues zit eronder, de helft erboven. Naast dat ene
getal staat een **verdeling**, want een mediaan verbergt of er één soort werk is
of twee.

Drie dingen die het rapport expliciet apart houdt:

- **Doorvoer in plaats van "tijd in Done".** Zodra een issue zijn eindstatus
  bereikt stopt de meting, dus een verblijfsduur in Done bestaat niet. Wat de
  Done-band in een cumulative flow diagram wél zegt is hoevéél werk eruit komt —
  dat staat er als doorvoer per sprint.
- **Bulk aangemaakte issues.** Bij een backlog-import krijgen tientallen issues
  dezelfde `created`, en dan meet hun To Do-tijd hoe lang geleden de backlog is
  ingeladen in plaats van hoe lang iemand op het werk wachtte. Het rapport
  benoemt de importmomenten en splitst de doorlooptijd in twee cohorten. Op MOD
  is dat 86 werkdagen voor de geïmporteerde issues tegen 43 voor los aangemaakte
  — precies het dubbele, dus het onderscheid is geen detail.
- **Actief aandeel**: de tijd in een In Progress-status gedeeld door de
  doorlooptijd. Let op dat dit géén flow-efficiëntie is in de zin van de
  waardestroom (§7 van het technisch ontwerp) — een issue dat een weekend in
  "Test" staat telt hier als actief.

| Wat je wilt | Optie |
|---|---|
| Ander venster | `--months 12` |
| Alleen bepaalde issuetypes | `--issue-types "Story,Bug"` |
| Subtaken meenemen | `--include-subtasks` |
| Kalendervenster i.p.v. sprintgrenzen | `--no-sprint-snap` |
| Cache negeren en live ophalen | `--refresh` |
| Ander cachebestand | `--flow-cache PATH` |

Artefacten landen in **`output/<PROJECT>/`**: `…_report.md` (het hoofddocument),
`…json`, en CSV's `_issues` (per issue de dagen per categorie), `_statuses` en
`_sprints`. De opgehaalde issues worden gecachet in
`output/<PROJECT>/jira_flow_cache_<PROJECT>.json`, zodat een tweede analyse geen
volledige changelog-fetch meer kost.

**Statuscategorieën komen uit Jira zelf** (`statusCategory` uit de workflow van
het project), niet uit een hardgecodeerde lijst statusnamen — dit script deelt
dus niet de `--status-dev/--status-test`-beperking van de business case.

### Zelftest

Het rekenwerk waar een fout stil doorwerkt in het rapport — feestdagen,
werkdagenduur, percentielen, het parsen van sprintstrings, bulk-detectie — staat
onder een offline zelftest. Geen netwerk, geen creds, geen cache:

```bash
uv run python scripts/selftest_flow.py        # stil bij succes
uv run python scripts/selftest_flow.py -v     # toont elke check
```

Draai hem na elke wijziging in `jira_core.py` of `jira_flow_analysis.py`.
Exitcode 0 = alles goed, 1 = er faalde iets.

## Credentials

Zet een `creds.yaml` in de repo (gitignored) of laat het script terugvallen op
dat van fo_doc_gen — het zoekt in de werkdirectory, naast het script, en als
laatste in `~/github_repos/fo_doc_gen/`. Zie `creds.yaml.example`.

Jira draait op Data Center en gebruikt een Personal Access Token (Bearer, geen
Basic auth); het `/jira`-contextpad wordt automatisch gedetecteerd. TestRail
gebruikt Basic auth met een API-key.

## Cases

- `cases/incasso_2026/` — business case testautomatisering incassoproces:
  rapport, managementdeck en brondata.

## Beperkingen en aannames

Bewust expliciet, want ze bepalen de interpretatie. Het rapport (§11.5) geeft per
aanname de **basis**: industriereferentie, lokale inschatting (te vervangen door
pilotmeting), of organisatieconventie. De meeste modelparameters zijn géén
industrienorm — dat staat er ook zo.

- **Uren worden nergens geregistreerd** (geen worklogs, geen estimates, TestRail
  `elapsed` vrijwel leeg). Inspanning is afgeleid uit timestamps en is een
  **ondergrens**; het ROI-model rekent met expliciete aannamebanden.
- **De waardestroom leest twee workflow-statussen** (default `In Progress` /
  `In testing`, override met `--status-dev/--status-test`). Stories die de
  teststatus niet doorlopen geven een onvolledige tijdlijn — zelf een bevinding.
- **De W-code-herkenning is incasso-specifiek.**
- **Alle TestRail-testers gelden als systeemtesters (aanname).** `get_users`
  geeft 403. **Business-acceptatietests (BAT/key-usertests) zitten níet in de
  TestRail-data** en vallen buiten elke meting.
- **De de-facto-regressiedetectie leest eindstatussen per run** (in-run
  fail→pass leest als "passed") en ziet geen runs bínnen testplannen — de
  volumes zijn ondergrenzen.

## Verantwoording

[`docs/technisch-ontwerp.md`](docs/technisch-ontwerp.md) beschrijft de keten in
volgorde: welke call, welk veld, welke afleiding, welke aanname — inclusief een
tabel die per grootheid aangeeft of hij **gemeten**, **afgeleid** of
**aangenomen** is, en waaróm elke stap zo werkt.
