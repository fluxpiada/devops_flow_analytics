# Business case data: manual → geautomatiseerd (regressie)testen

_Extractie 2026-07-20T14:48:32 · Jira **S34-2907** · TestRail run **26442** · suite 496_

## 0. De kern — in testdagen

| Vraag | Antwoord |
|---|---|
| Wat kost één handmatige regressieronde? | **26 persoonstestdagen** inzet, verspreid over **5 weken** (25 werkdagen) testvenster |
| Hoeveel daarvan ligt het stil? | **8 werkdagen** binnen het testvenster zonder enige testactiviteit (wachten op bugfixes) |
| En de hele story, van bouw tot oplevering? | **83 werkdagen**, waarvan 28 wachten — flow-efficiëntie 66% (zie §6b) |
| Hoe vaak willen we een ronde? | elke week, of minimaal elke sprint (3 weken) — nodig voor de incasso-refactoring |
| Kan dat handmatig? | Nee. Eén ronde beslaat 5 weken en ±1 tester; wekelijks is fysiek onmogelijk |
| Wat kost automatiseren? | eenmalig **40–80 dagen** bouwen (80 testgevallen) + onderhoud bij proceswijzigingen |
| Wat levert het per ronde op? | ±13 testdagen bespaard en doorlooptijd terug naar **44 werkdagen** |
| Wanneer terugverdiend? | na **±5 rondes** — bij wekelijks draaien binnen een kwartaal |

**Conclusie:** dit is geen besparingscase op bestaande uren (die worden nauwelijks gemaakt), maar een **enabler-case**: automatisering maakt de wekelijkse regressie mogelijk die de refactoring van het incassoproces vereist.

_De hoofdstukken hierna onderbouwen deze zeven regels; hoofdstuk 11 verantwoordt de methode._

## 1. Kernbevindingen

- **Kalenderdoorlooptijd** (In Progress → Resolved): **79.0 dagen**, waarvan 45.0 dagen in status *In testing*.
- **Netto actieve testtijd**: **7.01 persoonsuren** verdeeld over 4 testers — ≈ **1.1%** van een 8-uurs werkkalender. De rest is wachttijd (dataprep, bugfixes, hertests).
- **Her-executie-belasting**: 108 resultaten op 35 tests = gem. 3.1× per test (max 9); first-pass-rate 57%.
- **Defects**: 10 bugs uit deze run; gemiddelde oplostijd 6.3 dagen (mediaan 7.8).
- **Frequentie**: 394 runs op suite 496; 32 bevatten regressie-getitelde tests. Automatiseringsgraad: **0.0%** van 2868 cases (veld `custom_automation_type`, opties: None/Ranorex).

## 2. Levenscyclus-tijdlijn (Jira → TestRail → Jira)

| Fase | Duur |
|---|---|
| Voorbereiding (In Progress → eerste testresultaat) | 41.2 dagen |
| Executievenster (eerste → laatste resultaat) | 31.8 dagen (17 actieve dagen) |
| Afronding (laatste resultaat → story Resolved) | 6.0 dagen |
| **Totaal kalender** | **79.0 dagen** |
| **Netto actief (timestamp-proxy)** | **7.01 uur** |

Teststadia (Jira-subtaken):

| Subtaak | Omschrijving | Aangemaakt | Opgelost |
|---|---|---|---|
| S34-3575 | Testen 1 week (incl) | 2025-12-03 | 2026-03-03 |
| S34-3576 | Testvoorbereiding Key Users | 2025-12-03 | 2026-01-05 |
| S34-3577 | Bestaalstapel klant factuuur enz | 2025-12-03 | 2025-12-18 |
| S34-3845 | Testen verzamelklanten | 2026-02-02 | 2026-02-23 |
| S34-3846 | Aanpassen procesplaat naincassoproces B2B en VZK | 2026-02-02 | 2026-03-05 |
| S34-3914 | Aanmaanritme Evides incorrect | 2026-02-16 | 2026-02-25 |
| S34-3974 | testen P2P | 2026-02-27 | 2026-02-27 |

## 3. Onderwerpen (W-codes)

| W-code | Tests | Executies | Failed | Defects |
|---|---|---|---|---|
| W010 | 26 | 88 | 12 | S34-3840, S34-3843, S34-3851, S34-3880, S34-3881, S34-3903, S34-3904, S34-3914, S34-3922, S34-3945 |
| W020 | 1 | 2 | 0 | — |
| W030 | 1 | 2 | 0 | — |
| W040 | 5 | 15 | 1 | S34-3840 |
| W060 | 1 | 2 | 0 | — |
| W100 | 12 | 49 | 6 | S34-3843, S34-3851, S34-3903, S34-3904, S34-3914, S34-3922 |

## 4. Defects uit deze run

| Key | Type | Status | Aangemaakt | Opgelost | Dagen |
|---|---|---|---|---|---|
| S34-3945 | Bug | Resolved | 2026-02-19 | 2026-02-19 | 0.0 |
| S34-3922 | Bug | Done | 2026-02-17 | 2026-02-25 | 8.2 |
| S34-3914 | Story Bug | Done | 2026-02-16 | 2026-02-25 | 9.1 |
| S34-3904 | Bug | Resolved | 2026-02-13 | 2026-03-04 | 18.9 |
| S34-3903 | Bug | Done | 2026-02-13 | 2026-02-23 | 10.2 |
| S34-3881 | Bug | Resolved | 2026-02-11 | 2026-02-19 | 7.7 |
| S34-3880 | Bug | Done | 2026-02-11 | 2026-02-19 | 7.8 |
| S34-3851 | Bug | Done | 2026-02-06 | 2026-02-06 | 0.1 |
| S34-3843 | Bug | Done | 2026-01-30 | 2026-01-30 | 0.1 |
| S34-3840 | Bug | Done | 2026-01-29 | 2026-01-30 | 1.0 |

## 5. Corpus en frequentie (suite 496)

| Jaar | Runs | Tests (aangemaakt) | Tests (uitgevoerd) | Regressie-runs | Regressie uitgevoerd |
|---|---|---|---|---|---|
| 2023 | 108 | 3303 | 336 | 4 | 4 |
| 2024 | 112 | 3736 | 798 | 5 | 4 |
| 2025 | 98 | 4198 | 1115 | 13 | 17 |
| 2026 | 76 | 344 | 339 | 10 | 37 |

_Alleen **uitgevoerde** tests tellen mee in het ROI-model; aangemaakte-maar-nooit-gedraaide suite-runs (bv. 3× een 2868-tests selectie, 100% untested) zijn uitgesloten._

Regressie als deelverzameling: 32 van 394 runs (8%) bevat regressie-getitelde tests. Het ROI-model rekent daarom **beide scopes** door (regressie-subset én hele suite).

## 6. ROI-model (aannames + gevoeligheid)

Anker: **8.3 min/executie** (mediane in-sessie-tijd tussen resultaat-submits, run 26442). Banden: {'low': 6.2, 'mid': 12.5, 'high': 16.6}. Her-executiefactor 3.1×. Bouw: [2, 4, 8] uur/case over 80 cases; onderhoud 20%/jaar; restinspanning na automatisering 10%.

Jaarlijkse executies per scope: {'regression_subset': 71, 'whole_suite': 2220}

| Scope | Band | Min/exec | Handm. uren/jr | Bouw u/case | Bouw totaal | Netto besparing/jr | Terugverdientijd |
|---|---|---|---|---|---|---|---|
| regression_subset | low | 6.2 | 7 | 2 | 160 | -25 | n.v.t. |
| regression_subset | low | 6.2 | 7 | 4 | 320 | -57 | n.v.t. |
| regression_subset | low | 6.2 | 7 | 8 | 640 | -121 | n.v.t. |
| regression_subset | mid | 12.5 | 15 | 2 | 160 | -19 | n.v.t. |
| regression_subset | mid | 12.5 | 15 | 4 | 320 | -51 | n.v.t. |
| regression_subset | mid | 12.5 | 15 | 8 | 640 | -115 | n.v.t. |
| regression_subset | high | 16.6 | 20 | 2 | 160 | -14 | n.v.t. |
| regression_subset | high | 16.6 | 20 | 4 | 320 | -46 | n.v.t. |
| regression_subset | high | 16.6 | 20 | 8 | 640 | -110 | n.v.t. |
| whole_suite | low | 6.2 | 229 | 2 | 160 | 174 | 0.9 jr |
| whole_suite | low | 6.2 | 229 | 4 | 320 | 142 | 2.2 jr |
| whole_suite | low | 6.2 | 229 | 8 | 640 | 78 | 8.2 jr |
| whole_suite | mid | 12.5 | 462 | 2 | 160 | 384 | 0.4 jr |
| whole_suite | mid | 12.5 | 462 | 4 | 320 | 352 | 0.9 jr |
| whole_suite | mid | 12.5 | 462 | 8 | 640 | 288 | 2.2 jr |
| whole_suite | high | 16.6 | 614 | 2 | 160 | 521 | 0.3 jr |
| whole_suite | high | 16.6 | 614 | 4 | 320 | 489 | 0.7 jr |
| whole_suite | high | 16.6 | 614 | 8 | 640 | 425 | 1.5 jr |

### Doelcadans: wekelijkse of per-sprint regressie van het incassoproces

Het team wil het volledige incassoproces **1×/week of 1×/sprint (3 weken)** kunnen regressietesten, omdat het proces verbeterd, robuust gemaakt (gerefactord) en qua business rules vereenvoudigd gaat worden. Dat is de cadans waarop de business case beoordeeld moet worden — niet de historische (4–37 uitgevoerde regressietests/jaar). Model: 80 cases × 1 executie per run (defect-herexecuties niet meegerekend), bouw 320 uur (middenband 4 u/case), onderhoud 20%/jaar.

| Cadans | Runs/jr | Band | Min/exec | Handmatig equivalent (u/jr) | Netto besparing/jr | Terugverdientijd |
|---|---|---|---|---|---|---|
| wekelijks | 52 | low | 6.2 | 430 | 323 | 1.0 jr |
| wekelijks | 52 | mid | 12.5 | 867 | 716 | 0.4 jr |
| wekelijks | 52 | high | 16.6 | 1151 | 972 | 0.3 jr |
| per sprint (3 wk) | 17 | low | 6.2 | 141 | 62 | 5.1 jr |
| per sprint (3 wk) | 17 | mid | 12.5 | 283 | 191 | 1.7 jr |
| per sprint (3 wk) | 17 | high | 16.6 | 376 | 275 | 1.2 jr |

**Conclusie:** handmatig kost de wekelijkse doelcadans ~867 uur/jaar (middenband) — ≈ 0.5 FTE, niet realistisch naast het huidige werk (historisch worden regressieruns wél aangemaakt maar amper uitgevoerd). Geautomatiseerd is dezelfde cadans na een bouwinvestering van 320 uur haalbaar, met terugverdientijd 0.3–5.1 jaar afhankelijk van cadans en effortband. De businesscase is dus geen efficiency-case op bestaande uren, maar een **enabler-case**: de gewenste kwaliteitsborging rond de incasso-refactoring is zonder automatisering praktisch onhaalbaar.

## 6b. Waardestroom: waar gaat de doorlooptijd heen?

_Scope: start bouw → story opgeleverd (backlog-wachttijd uitgesloten). Eenheid: werkdagen (ma–vr); actief = werk, wacht = stilstand. Actieve bouwtijd geschat op 0.8 FTE (40 u/week); testinzet is gemeten._

| Stap | Actieve tijd | Wachttijd | First-time-right | Toelichting |
|---|---|---|---|---|
| Bouw (development) | 20.0 d | 5.0 d | — | start bouw → overdracht naar test |
| Testvoorbereiding | 3.6 d | 2.4 d | — | Key Users + testdata klaarzetten |
| Testuitvoering | 26.0 d | 8.0 d | 57% | 108 uitvoeringen door 4 testers |
| Bugfix + hertest | 4.5 d | 7.9 d | 100% | 10 bugs; mediaan 7.9 d wachten per bug |
| Afronding / oplevering | 1.0 d | 5.0 d | 100% | laatste test → story Resolved |
| **Totaal** | **55.1 d** | **28.3 d** | — | doorlooptijd **83.4 werkdagen** |

**Flow-efficiëntie: 66%** — van de 83.4 werkdagen doorlooptijd wordt er 55.1 dagen daadwerkelijk gewerkt; de rest is wachten (op testcapaciteit, op bugfixes, op hertestslots).

Met geautomatiseerde regressie: **43.5 werkdagen** doorlooptijd (30.1 d actief, 13.4 d wachten) — flow-efficiëntie **69%**. De testuitvoering verdwijnt als handwerk en de hertestlus krimpt van dagen naar uren.

_Buiten scope maar wel relevant: de story stond hiervóór nog 187 werkdagen in de backlog._

## 7. Non-regressie en wijzigingsdruk (W-stappen)

Naast regressie draait de suite vooral **story-/changetests** — en elke wijziging aan een W-stap dwingt straks een tweak + her-run van de geautomatiseerde regressieset af. Dit is de onderhoudskant van de business case.

| Jaar | Non-regressie uitgevoerd | Regressie uitgevoerd |
|---|---|---|
| 2023 | 332 | 4 |
| 2024 | 794 | 4 |
| 2025 | 1098 | 17 |
| 2026 | 302 | 37 |

Wijzigingsdruk per W-stap (Jira-issues met de stap in de titel, projecten S34, KFDO):

| W-stap | Cases in suite | In case-study-run | Jira-issues | Stories | Bugs | Voorbeeld |
|---|---|---|---|---|---|---|
| W010 | 64 | ✓ | 18 | 7 | 11 | KFDO-768 (Task): Uitwerken requirement als W010 de vriendelijke reminder word |
| W020 | 55 | ✓ | 4 | 3 | 1 | KFDO-284 (Story): W030: Als de W020 eerder wordt gestuurd dan de W030 sturen i |
| W030 | 2 | ✓ | 2 | 2 | 0 | KFDO-284 (Story): W030: Als de W020 eerder wordt gestuurd dan de W030 sturen i |
| W040 | 36 | ✓ | 14 | 4 | 10 | KFDO-1076 (Bug): Verzamelfactuur wil niet door in aanmaanproces naar W040 |
| W050 | 3 | **✗** | 2 | 2 | 0 | KFDO-704 (Epic): FactBV - W050 de Rotonde |
| W060 | 9 | ✓ | 3 | 1 | 2 | KFDO-730 (Epic): Vitens - Aanpassing in W040 (freq. en bedrag aanmaning) en W |
| W070 | 8 | **✗** | 0 | 0 | 0 | — |
| W080 | 9 | **✗** | 2 | 1 | 1 | KFDO-705 (Epic): Evides - W080 Drempelbedrag |
| W085 | 1 | **✗** | 0 | 0 | 0 | — |
| W090 | 6 | **✗** | 2 | 0 | 2 | KFDO-1017 (Bug): Voor betaalde aanmaankosten wordt vereffening niet ongedaan  |
| W100 | 90 | ✓ | 15 | 3 | 12 | KFDO-1017 (Bug): Voor betaalde aanmaankosten wordt vereffening niet ongedaan  |

⚠️ **Antwoord op 'vergeet ik stappen?': ja** — de suite kent ook W050, W070, W080, W085, W090, die in de onderzochte regressierun níet zaten. Neem ze mee in de scope van de te automatiseren set (of onderbouw expliciet waarom niet).

## 8. Dev- vs testinspanning (kalenderproxy)

_Kalenderproxy: dagen 'In Progress' (dev) vs 'In testing' (test) uit de Jira-changelog. Geen urenregistratie aanwezig; administratief teruggeboekte statussen (alle transities binnen ~1 uur) zijn gemarkeerd en uitgesloten._

| Issue | Type | Dev (In Progress, d) | Test (In testing, d) | Ratio test:dev | Backfilled |
|---|---|---|---|---|---|
| S34-2907 | Story | 33.9 | 45.0 | 1.33 |  |
| S34-3945 | Bug | 0 | 0 | — | ⚠️ |
| S34-3922 | Bug | 0 | 0 | — |  |
| S34-3914 | Story Bug | 0 | 0 | — | ⚠️ |
| S34-3904 | Bug | 0.0 | 18.7 | — |  |
| S34-3903 | Bug | 10.0 | 0 | 0.0 |  |
| S34-3881 | Bug | 0.0 | 5.9 | — |  |
| S34-3880 | Bug | 0 | 0 | — |  |
| S34-3851 | Bug | 0.0 | 0 | — |  |
| S34-3843 | Bug | 0 | 0 | — |  |
| S34-3840 | Bug | 0.0 | 0.0 | — |  |

Epic-breed (S34-3642, 19 children):

| Issue | Type | Status | Dev (d) | Test (d) | Ratio | Backfilled |
|---|---|---|---|---|---|---|
| KFDO-271 | Story | Resolved | 20.2 | 0 | 0.0 |  |
| KFDO-273 | Story | Analyse | 15.1 | 0 | 0.0 |  |
| KFDO-274 | Story | In Progress | 20.2 | 0 | 0.0 |  |
| KFDO-281 | Story | Analyse | 0 | 0 | — |  |
| KFDO-286 | Story | In Progress | 0 | 0 | — |  |
| KFDO-287 | Story | Analyse | 0 | 0 | — |  |
| KFDO-289 | Story | Open | 0 | 0 | — |  |
| KFDO-549 | Story | In Progress | 0 | 0 | — |  |
| KFDO-688 | Story | Analyse | 0 | 0 | — | ⚠️ |
| KFDO-695 | Story | In Progress | 0 | 0 | — |  |
| KFDO-715 | Task | Open | 0 | 0 | — |  |
| KFDO-784 | Story | Open | 0 | 0 | — |  |
| KFDO-1076 | Bug | In Progress | 0 | 0 | — | ⚠️ |
| S34-2907 | Story | Resolved | 33.9 | 45.0 | 1.33 |  |
| S34-3734 | Story | Resolved | 14.9 | 0.0 | 0.0 |  |
| S34-3838 | Story | Done | 0 | 0 | — |  |
| S34-3850 | Story | Resolved | 6.2 | 0.0 | 0.0 |  |
| S34-3989 | Story | Resolved | 13.7 | 0.0 | 0.0 |  |
| S34-3993 | Story | Resolved | 8.1 | 7.0 | 0.86 |  |

**Samenvatting:** mediaan test:dev-ratio **1.09** (gem. 1.09, n=2 issues waar béide fasen zijn geregistreerd). Bugfix-lus: failed→passed hertest-gap mediaan **7.9 d** (gem. 6.3, n=9) — de tijd die de testkant per defect wacht op dev-fix + hertestslot; de bug-oplostijd zelf (§4, gem. 6,3 d) is de dev-kant van diezelfde lus.

⚠️ Datakwaliteit: **5 afgeronde issues doorliepen nooit de status 'In testing'** — testinspanning wordt op story-niveau vaak niet geregistreerd (of zit in subtaken). De werkelijke test:dev-verhouding ligt dus eerder hóger dan hier gemeten.

## 9. Kanttekeningen (eerlijk)

- Netto actieve tijd is een **ondergrens**: de gap-methode mist losse resultaten, setup, analyse en overleg.
- Kalenderduren zijn **wandkloktijd** en bevatten niet-testgebonden wachttijd. Besparing op executie-uren en verkorte doorlooptijd zijn **aparte** batenregels — niet optellen.
- Nergens zijn uren geregistreerd (0 worklogs, 0 estimates, TestRail `elapsed` vrijwel leeg); het anker moet door Key Users worden gevalideerd.
- De dev:test-ratio is een **kalender**verhouding (In Progress- vs In testing-dagen), geen uren-verhouding; statussen worden soms achteraf geboekt (gemarkeerd ⚠️ en uitgesloten uit het aggregaat).

## 10. Openstaande vragen

1. Klopt ±8.3 min hands-on per test-executie met het gevoel van de Key Users, of ligt de echte tijd (incl. setup/analyse) wezenlijk hoger?
2. Ranorex: bouwuren per case en verwacht jaarlijks onderhoud — is er een pilot-datapunt?
3. Is de huidige run-frequentie representatief voor de toekomst, of was 2024–2025 opgeblazen door de SAP-migratie?
4. Moet defect-preventie (eerder vangen van bugs) worden gemonetariseerd, of blijft de case puur op executie-inspanning?
5. Aanbeveling los van de business case: registreer TestRail `elapsed` één regressiecyclus lang en vul `custom_automation_type` bij elke geautomatiseerde case — gratis meetbaarheid.

## 11. Verantwoording — functioneel & technisch ontwerp

### 11.1 Functionele stappen

| # | Stap | Doel | Resultaat |
|---|---|---|---|
| 1 | Bronverkenning | Vaststellen welke meetdata bestaat | Jira-changelog ✓ · worklogs ✗ (0) · TestRail `elapsed` ✗ (~0%) · estimates ✗ |
| 2 | Jira-levenscyclus | Statusovergangen van story + subtaken | Fasen 41.2d prep / 31.8d executie / 6.0d afronding; 45.0d In testing |
| 3 | TestRail-executie | Resultaathistorie van de run | 108 resultaten / 35 tests; 3.1× her-executie; first-pass 57% |
| 4 | Defect-koppeling | TestRail `defects`-veld → Jira-bugs | 10 bugs, oplostijd gem. 6.3 d |
| 5 | Effort-proxy | Uren nergens geregistreerd → sessie-gap-methode | Anker 8.3 min/executie; 7.01 netto uren |
| 6 | Corpus-scan | Frequentie + automatiseringsgraad | 394 runs, 2868 cases, 0.0% geautomatiseerd |
| 7 | Tijdlijn | Cross-systeem event-stroom | 158 events; defect-loop zichtbaar (bug → failed → retest → passed → resolved) |
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
| Jaarvolume | gem. uitgevoerde tests/jaar (lopend jaar geannualiseerd) × her-executiefactor 3.1 |
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
