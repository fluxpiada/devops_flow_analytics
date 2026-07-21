# devops_flow

Meet doorlooptijd, inspanning en flow-efficiëntie van ontwikkel- en testwerk,
op basis van wat Jira en TestRail al registreren. Geen urenregistratie nodig.

## Wat het meet

- **Levenscyclus** — statusovergangen per story en subtaak uit de Jira-changelog.
- **Testuitvoering** — uitvoeringen per testgeval, first-pass-rate en testdagen
  per tester, uit de TestRail-resultaathistorie.
- **Defect-lus** — gevonden bugs, oplostijd (Jira) en hertest-wachttijd (TestRail).
- **Waardestroom** — per processtap actieve tijd vs wachttijd, plus
  flow-efficiëntie; inclusief een geautomatiseerd scenario.
- **Wijzigingsdruk** — hoe vaak elke processtap wordt geraakt door wijzigingen,
  als onderbouwing voor de onderhoudslast van een geautomatiseerde testset.

## Gebruik

```bash
uv sync

# analyse van één story + testrun (snel, zonder historie-scan)
uv run python scripts/testauto_businesscase.py --jira S34-2907 --run 26442 --skip-corpus

# volledig, inclusief frequentie-historie van de hele suite (~7 min)
uv run python scripts/testauto_businesscase.py --jira S34-2907 --run 26442

# managementdeck uit de laatste analyse
uv run python scripts/build_mgmt_deck.py
```

Output komt in `output/`: een JSON met alle cijfers, CSV's (runs, defects,
tijdlijn, W-stappen, dev/test) en een Markdown-rapport.

### Handige opties

| Wat je wilt | Optie |
|---|---|
| Andere Jira-projecten voor wijzigingsdruk | `--jql-projects "S34, KFDO, ITS"` |
| Portfolio-analyse via een specifiek epic | `--epic KFDO-123` |
| Historie-scan beperken | `--max-runs 20` |
| Ander pad naar credentials | `--creds ../fo_doc_gen/creds.yaml` |

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

## Beperkingen

Deze zijn bewust expliciet, omdat ze de interpretatie van de cijfers bepalen.

- **Uren worden nergens geregistreerd** (geen worklogs, geen estimates, TestRail
  `elapsed` vrijwel leeg). Inspanning is afgeleid uit timestamps en is daarmee
  een **ondergrens**; het ROI-model rekent met expliciete aannamebanden.
- **De waardestroom leest de statussen `In Progress` en `In testing`.** Stories
  die de teststatus niet doorlopen — en dat komt voor — geven een onvolledige
  tijdlijn. Dat is zelf een bevinding: testwerk wordt vaak niet op story-niveau
  geregistreerd.
- **De W-code-herkenning voor processtappen is specifiek voor het incassoproces.**
  Voor een ander domein werkt de rest wel, maar vind je geen processtappen.
- **`build_mgmt_deck.py` is deels een sjabloon.** De tijdlijn en de kengetallen
  komen uit de data; de argumentatie is geschreven voor één specifieke
  beslissing en moet je herschrijven voor een andere case.
