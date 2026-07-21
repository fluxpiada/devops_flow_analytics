# Business case data: manual → geautomatiseerd (regressie)testen

_Extractie 2026-07-21T10:28:46 · Jira **S34-2908** · TestRail run **26119** · suite 496_

## 0. De kern — in testdagen

| Vraag | Antwoord |
|---|---|
| Wat kost één handmatige regressieronde? | **2 persoonstestdagen** inzet, verspreid over **5 weken** (25 werkdagen) testvenster |
| Hoeveel daarvan ligt het stil? | **0 werkdagen** binnen het testvenster zonder enige testactiviteit (wachten op bugfixes) |
| En de hele story, van bouw tot oplevering? | **26 werkdagen**, waarvan 6 wachten — flow-efficiëntie 75% (zie §6b) |
| Hoe vaak willen we een ronde? | elke week, of minimaal elke sprint (3 weken) — nodig voor de incasso-refactoring |
| Kan dat handmatig? | Nee. Eén ronde beslaat 5 weken en ±1 tester; wekelijks is fysiek onmogelijk |
| Wat kost automatiseren? | eenmalig **40–80 dagen** bouwen (80 testgevallen) + onderhoud bij proceswijzigingen |
| Wat levert het per ronde op? | ±13 testdagen bespaard en doorlooptijd terug naar **26 werkdagen** |
| Wanneer terugverdiend? | na **±5 rondes** — bij wekelijks draaien binnen een kwartaal |

**Conclusie:** dit is geen besparingscase op bestaande uren (die worden nauwelijks gemaakt), maar een **enabler-case**: automatisering maakt de wekelijkse regressie mogelijk die de refactoring van het incassoproces vereist.

_De hoofdstukken hierna onderbouwen deze zeven regels; hoofdstuk 11 verantwoordt de methode._

## 1. Kernbevindingen

- **Kalenderdoorlooptijd** (In Progress → Resolved): **29.0 dagen**, waarvan 6.8 dagen in status *In testing*.
- **Netto actieve testtijd**: **3.06 persoonsuren** verdeeld over 1 testers — ≈ **1.3%** van een 8-uurs werkkalender. De rest is wachttijd (dataprep, bugfixes, hertests).
- **Her-executie-belasting**: 14 resultaten op 14 tests = gem. 1.0× per test (max 1); first-pass-rate 100%.
- **Defects**: 0 bugs uit deze run; gemiddelde oplostijd None dagen (mediaan None).

## 2. Levenscyclus-tijdlijn (Jira → TestRail → Jira)

| Fase | Duur |
|---|---|
| Voorbereiding (In Progress → eerste testresultaat) | 26.1 dagen |
| Executievenster (eerste → laatste resultaat) | 1.2 dagen (2 actieve dagen) |
| Afronding (laatste resultaat → story Resolved) | 1.7 dagen |
| **Totaal kalender** | **29.0 dagen** |
| **Netto actief (timestamp-proxy)** | **3.06 uur** |

Teststadia (Jira-subtaken):

| Subtaak | Omschrijving | Aangemaakt | Opgelost |
|---|---|---|---|

## 3. Onderwerpen (W-codes)

| W-code | Tests | Executies | Failed | Defects |
|---|---|---|---|---|
| W010 | 6 | 6 | 0 | — |
| W020 | 3 | 3 | 0 | — |
| W040 | 2 | 2 | 0 | — |
| W060 | 1 | 1 | 0 | — |
| W070 | 1 | 1 | 0 | — |
| W080 | 1 | 1 | 0 | — |
| W090 | 1 | 1 | 0 | — |
| W100 | 13 | 13 | 0 | — |

## 4. Defects uit deze run

| Key | Type | Status | Aangemaakt | Opgelost | Dagen |
|---|---|---|---|---|---|

## 6. ROI-model (aannames + gevoeligheid)

Anker: **15.9 min/executie** (mediane in-sessie-tijd tussen resultaat-submits, run 26119). Banden: {'low': 11.9, 'mid': 23.9, 'high': 31.8}. Her-executiefactor 1.0×. Bouw: [2, 4, 8] uur/case over 14 cases; onderhoud 20%/jaar; restinspanning na automatisering 10%.

Jaarlijkse executies per scope: {}

| Scope | Band | Min/exec | Handm. uren/jr | Bouw u/case | Bouw totaal | Netto besparing/jr | Terugverdientijd |
|---|---|---|---|---|---|---|---|

### Doelcadans: wekelijkse of per-sprint regressie van het incassoproces

Het team wil het volledige incassoproces **1×/week of 1×/sprint (3 weken)** kunnen regressietesten, omdat het proces verbeterd, robuust gemaakt (gerefactord) en qua business rules vereenvoudigd gaat worden. Dat is de cadans waarop de business case beoordeeld moet worden — niet de historische (4–37 uitgevoerde regressietests/jaar). Model: 14 cases × 1 executie per run (defect-herexecuties niet meegerekend), bouw 56 uur (middenband 4 u/case), onderhoud 20%/jaar.

| Cadans | Runs/jr | Band | Min/exec | Handmatig equivalent (u/jr) | Netto besparing/jr | Terugverdientijd |
|---|---|---|---|---|---|---|
| wekelijks | 52 | low | 11.9 | 144 | 119 | 0.5 jr |
| wekelijks | 52 | mid | 23.9 | 290 | 250 | 0.2 jr |
| wekelijks | 52 | high | 31.8 | 386 | 336 | 0.2 jr |
| per sprint (3 wk) | 17 | low | 11.9 | 47 | 31 | 1.8 jr |
| per sprint (3 wk) | 17 | mid | 23.9 | 95 | 74 | 0.8 jr |
| per sprint (3 wk) | 17 | high | 31.8 | 126 | 102 | 0.5 jr |

**Conclusie:** handmatig kost de wekelijkse doelcadans ~290 uur/jaar (middenband) — ≈ 0.2 FTE, niet realistisch naast het huidige werk (historisch worden regressieruns wél aangemaakt maar amper uitgevoerd). Geautomatiseerd is dezelfde cadans na een bouwinvestering van 56 uur haalbaar, met terugverdientijd 0.2–1.8 jaar afhankelijk van cadans en effortband. De businesscase is dus geen efficiency-case op bestaande uren, maar een **enabler-case**: de gewenste kwaliteitsborging rond de incasso-refactoring is zonder automatisering praktisch onhaalbaar.

## 6b. Waardestroom: waar gaat de doorlooptijd heen?

_Scope: start bouw → story opgeleverd (backlog-wachttijd uitgesloten). Eenheid: werkdagen (ma–vr); actief = werk, wacht = stilstand. Actieve bouwtijd geschat op 0.8 FTE (40 u/week); testinzet is gemeten._

| Stap | Actieve tijd | Wachttijd | First-time-right | Toelichting |
|---|---|---|---|---|
| Bouw (development) | 13.6 d | 3.4 d | — | start bouw → overdracht naar test |
| Testvoorbereiding | 3.0 d | 0.0 d | — | Key Users + testdata klaarzetten |
| Testuitvoering | 2.0 d | 0.0 d | 100% | 14 uitvoeringen door 1 testers |
| Bugfix + hertest | 0.0 d | 0 d | 100% | 0 bugs; mediaan None d wachten per bug |
| Afronding / oplevering | 1.0 d | 3.0 d | 100% | laatste test → story Resolved |
| **Totaal** | **19.6 d** | **6.4 d** | — | doorlooptijd **26.0 werkdagen** |

**Flow-efficiëntie: 75%** — van de 26.0 werkdagen doorlooptijd wordt er 19.6 dagen daadwerkelijk gewerkt; de rest is wachten (op testcapaciteit, op bugfixes, op hertestslots).

Met geautomatiseerde regressie: **26.0 werkdagen** doorlooptijd (18.6 d actief, 7.4 d wachten) — flow-efficiëntie **72%**. De testuitvoering verdwijnt als handwerk en de hertestlus krimpt van dagen naar uren.

_Buiten scope maar wel relevant: de story stond hiervóór nog 168 werkdagen in de backlog._

## 7. Non-regressie en wijzigingsdruk (W-stappen)

Naast regressie draait de suite vooral **story-/changetests** — en elke wijziging aan een W-stap dwingt straks een tweak + her-run van de geautomatiseerde regressieset af. Dit is de onderhoudskant van de business case.

Wijzigingsdruk per W-stap (Jira-issues met de stap in de titel, projecten S34, KFDO):

| W-stap | Cases in suite | In case-study-run | Jira-issues | Stories | Bugs | Voorbeeld |
|---|---|---|---|---|---|---|
| W010 | 0 | ✓ | 18 | 7 | 11 | KFDO-768 (Task): Uitwerken requirement als W010 de vriendelijke reminder word |
| W020 | 0 | ✓ | 4 | 3 | 1 | KFDO-284 (Story): W030: Als de W020 eerder wordt gestuurd dan de W030 sturen i |
| W040 | 0 | ✓ | 14 | 4 | 10 | KFDO-1076 (Bug): Verzamelfactuur wil niet door in aanmaanproces naar W040 |
| W060 | 0 | ✓ | 3 | 1 | 2 | KFDO-730 (Epic): Vitens - Aanpassing in W040 (freq. en bedrag aanmaning) en W |
| W070 | 0 | ✓ | 0 | 0 | 0 | — |
| W080 | 0 | ✓ | 2 | 1 | 1 | KFDO-705 (Epic): Evides - W080 Drempelbedrag |
| W090 | 0 | ✓ | 2 | 0 | 2 | KFDO-1017 (Bug): Voor betaalde aanmaankosten wordt vereffening niet ongedaan  |
| W100 | 0 | ✓ | 15 | 3 | 12 | KFDO-1017 (Bug): Voor betaalde aanmaankosten wordt vereffening niet ongedaan  |

## 8. Dev- vs testinspanning (kalenderproxy)

_Kalenderproxy: dagen 'In Progress' (dev) vs 'In testing' (test) uit de Jira-changelog. Geen urenregistratie aanwezig; administratief teruggeboekte statussen (alle transities binnen ~1 uur) zijn gemarkeerd en uitgesloten._

| Issue | Type | Dev (In Progress, d) | Test (In testing, d) | Ratio test:dev | Backfilled |
|---|---|---|---|---|---|
| S34-2908 | Story | 22.2 | 6.8 | 0.31 |  |

**Samenvatting:** mediaan test:dev-ratio **0.31** (gem. 0.31, n=1 issues waar béide fasen zijn geregistreerd). Bugfix-lus: failed→passed hertest-gap mediaan **None d** (gem. None, n=0) — de tijd die de testkant per defect wacht op dev-fix + hertestslot; de bug-oplostijd zelf (§4, gem. 6,3 d) is de dev-kant van diezelfde lus.

## 9. Kanttekeningen (eerlijk)

- Netto actieve tijd is een **ondergrens**: de gap-methode mist losse resultaten, setup, analyse en overleg.
- Kalenderduren zijn **wandkloktijd** en bevatten niet-testgebonden wachttijd. Besparing op executie-uren en verkorte doorlooptijd zijn **aparte** batenregels — niet optellen.
- Nergens zijn uren geregistreerd (0 worklogs, 0 estimates, TestRail `elapsed` vrijwel leeg); het anker moet door Key Users worden gevalideerd.
- De dev:test-ratio is een **kalender**verhouding (In Progress- vs In testing-dagen), geen uren-verhouding; statussen worden soms achteraf geboekt (gemarkeerd ⚠️ en uitgesloten uit het aggregaat).

## 10. Openstaande vragen

1. Klopt ±15.9 min hands-on per test-executie met het gevoel van de Key Users, of ligt de echte tijd (incl. setup/analyse) wezenlijk hoger?
2. Ranorex: bouwuren per case en verwacht jaarlijks onderhoud — is er een pilot-datapunt?
3. Is de huidige run-frequentie representatief voor de toekomst, of was 2024–2025 opgeblazen door de SAP-migratie?
4. Moet defect-preventie (eerder vangen van bugs) worden gemonetariseerd, of blijft de case puur op executie-inspanning?
5. Aanbeveling los van de business case: registreer TestRail `elapsed` één regressiecyclus lang en vul `custom_automation_type` bij elke geautomatiseerde case — gratis meetbaarheid.

## 11. Verantwoording — functioneel & technisch ontwerp

### 11.1 Functionele stappen

| # | Stap | Doel | Resultaat |
|---|---|---|---|
| 1 | Bronverkenning | Vaststellen welke meetdata bestaat | Jira-changelog ✓ · worklogs ✗ (0) · TestRail `elapsed` ✗ (~0%) · estimates ✗ |
| 2 | Jira-levenscyclus | Statusovergangen van story + subtaken | Fasen 26.1d prep / 1.2d executie / 1.7d afronding; 6.8d In testing |
| 3 | TestRail-executie | Resultaathistorie van de run | 14 resultaten / 14 tests; 1.0× her-executie; first-pass 100% |
| 4 | Defect-koppeling | TestRail `defects`-veld → Jira-bugs | 0 bugs, oplostijd gem. None d |
| 5 | Effort-proxy | Uren nergens geregistreerd → sessie-gap-methode | Anker 15.9 min/executie; 3.06 netto uren |
| 7 | Tijdlijn | Cross-systeem event-stroom | 19 events; defect-loop zichtbaar (bug → failed → retest → passed → resolved) |
| 8 | ROI-model | Gevoeligheidsanalyse i.p.v. schijnprecisie | 2 scopes × 3 effortbanden × 3 bouwbanden = 18 scenario's + doelcadans |
| 9 | Wijzigingsdruk per W-stap | Onderhoudslast regressieset onderbouwen | W-inventaris uit case-titels + Jira-search op W-codes (§7) |
| 10 | Dev:test-kalenderproxy | Verhouding test- vs dev-inspanning | In Progress- vs In testing-dagen, story + bugs + epic-children (§8) |
| 11 | Rapportage | JSON + CSV's (runs/defects/tijdlijn/wsteps/devtest) + dit rapport | reproduceerbaar via één CLI-run |

### 11.2 Technisch ontwerp — bronnen en velden

**Jira Data Center** (Bearer PAT uit `creds.yaml`; REST-basis autogedetecteerd incl. `/jira`-contextpad):

| Endpoint | Gebruikte velden | Gebruikt voor |
|---|---|---|
| `GET /rest/api/2/issue/{key}?expand=changelog` (story én per subtaak) | `created`, `updated`, `resolutiondate`, `status`, `issuetype`, `summary`, `subtasks`, `issuelinks`; `changelog.histories[].items[]` met field = `status` / `Sprint` / `Flagged` / `Story Points` | Statusovergangen, tijd-per-status, fasegrenzen, teststadia, sprint-spillover, impediments |
| `GET /rest/api/2/search` (`issuekey in (…)`, ook met `expand=changelog`) | `summary`, `issuetype`, `status`, `created`, `resolutiondate` (+ changelog voor bugs/epic-children) | Defect-oplostijden; dev:test-fasen per issue |
| `GET /rest/api/2/search` (`project in (S34, KFDO) AND summary ~ "Wxxx"`) | `summary`, `issuetype`, `created` | Wijzigingsdruk per W-stap |
| `GET /rest/api/2/search` (`"Epic Link" = <epic>`) | idem + changelog | Epic-brede dev:test-verhouding |

**TestRail** (Basic auth):

| Endpoint | Gebruikte velden | Gebruikt voor |
|---|---|---|
| `get_run/{id}` | `name`, `suite_id`, `project_id`, `created_on`, status-counts, `untested_count` | Runmetadata; fallback-telling |
| `get_tests/{run_id}` | `title`, `status_id`, `custom_automation_type` | W-codes, regressiedetectie (titel-regex), uitgevoerd-filter (`status_id ≠ 3`) |
| `get_results_for_run/{run_id}` | `test_id`, `status_id`, `created_on`, `created_by`, `defects` (`elapsed` bleek leeg) | Her-executies, first-pass-rate, effort-proxy, defect-koppeling, tijdlijn |
| `get_statuses` | `id`, `name` | Statuslabels |
| `get_runs/{project_id}?suite_id=` | `id`, `name`, `created_on`, counts | Corpus/frequentie |
| `get_cases/{project_id}?suite_id=` | `title`, `custom_automation_type` | Automatiseringsgraad, regressie-cases |

### 11.3 Afgeleide metrieken

| Metriek | Berekening |
|---|---|
| Tijd per status | changelog-transities chronologisch; created → … → resolutiondate |
| Fasen | prep = In Progress → 1e TestRail-resultaat; executie = 1e → laatste resultaat; afronding = laatste resultaat → Resolved |
| Netto actieve tijd | som van gaps ≤ 60 min tussen opeenvolgende result-submits per tester (ondergrens) |
| Anker min/executie | mediaan van diezelfde gaps |
| First-pass-rate | eerste betekenisvolle resultaat per test = passed |
| Uitgevoerd (corpus) | `status_id ≠ 3` (untested) — nooit-gedraaide runs vallen zo weg |
| Regressiedetectie | test-**titel**-regex (`regress` of `W### -> W###`); run-naam is onbetrouwbaar |
| Jaarvolume | gem. uitgevoerde tests/jaar (lopend jaar geannualiseerd) × her-executiefactor 1.0 |
| ROI | besparing = handm. uren × 90%; onderhoud = 20% van bouw/jr; terugverdientijd = bouw / netto besparing |

### 11.4 Datakwaliteitsbeslissingen

| Bevinding | Beslissing |
|---|---|
| 0 worklogs, 0 estimates, `elapsed` ~0% | Effort via sessie-gap-proxy + aannamebanden i.p.v. schijnprecisie |
| Volledige-suite-runs 100% untested (phantom-intent) | Uitgesloten via uitgevoerd-filter |
| TestRail negeert `offset` op `get_tests` | Paginatie met stall-detectie + paginacap |
| `creds.yaml` mist `/jira`-contextpad | Base-URL-autodetectie via serverInfo-probe |
| Run-naam ≠ betrouwbare regressie-marker | Detectie op test-titel i.p.v. run-naam |
| Bug-statussen deels achteraf geboekt (alle transities < 1 u) | Backfill-detectie; uitgesloten uit dev:test-aggregaat |

## 12. Verdiepingssuggesties — voortbrengingsketen

Wat deze analyse (nog) níet ziet, en hoe dat inzicht wél te krijgen is:

| # | Suggestie | Waarom / wat het oplevert | Bron |
|---|---|---|---|
| 1 | **SAP-transportdata koppelen** (ChaRM/Solution Manager, of de 'Change'/'Standard Change'-issues in Jira zoals ITS-304898) | Echte dev-inspanning en release-cadans; Jira's dev-status-API toont 0 commits/PR's — het werk zit in transports, niet in git | SolMan-export of ITS-Change-issues |
| 2 | **Defect-escape-rate** meten: bugs gevonden in test (S34-bugs) vs incidenten in productie (ITS-incidents, bv. ITS-303099 dat door S34-2907 werd opgelost) per W-stap | Monetariseert defect-preventie — de batenregel die nu bewust buiten de case blijft | Jira JQL over ITS + issuelinks |
| 3 | **Flow-metrics over het hele epic/portfolio** (alle S34/KFDO-stories: cycle time, flow-efficiency = actieve dagen / kalenderdagen, wachttijd per status) | Laat zien waar de keten écht wacht (deze case: 1,1% actief); automation verkort maar één schakel | Jira changelog batch-scan (deze scripts herbruikbaar) |
| 4 | **TestRail-milestones/plans gebruiken** en `elapsed` één cyclus registreren + `custom_automation_type` bijhouden bij elke geautomatiseerde case | Maakt de volgende versie van deze case gemeten i.p.v. proxy-gebaseerd; sluit aan op KFDO-715 (herinrichting TestRail) | TestRail |
| 5 | **Onderhouds-baseline uit de wijzigingsdruk** (§7): per W-stap-wijziging de werkelijke tweak-uren van de Ranorex-set loggen zodra de pilot draait | Vervangt de aanname 20%/jaar door een gemeten onderhoudsfactor | Ranorex-pilot + Jira |
| 6 | **Doorlooptijd-baten apart modelleren**: kortere feedback-lus (bug binnen een dag i.p.v. mediaan ~8 d hertest-gap) versnelt de refactoring zelf | De enabler-waarde van §10 wordt kwantificeerbaar in refactor-sprintcapaciteit | deze extractie, per sprint herhaald |
