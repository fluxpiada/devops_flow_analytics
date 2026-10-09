# devops_flow — flow- en sprintmetrics uit Jira, voor Excel

Leest de statusgeschiedenis van een Jira-project en zet die om in de standaard
Kanban- en Scrum-metrics. Python meet alleen; Excel presenteert. Geen
urenregistratie nodig, read-only.

## Wat het meet

Alle duren in **werkdagen**: weekenden en Nederlandse feestdagen tellen niet mee.

| Metric | Definitie |
| --- | --- |
| Cycle time | eerste stap naar een *In Progress*-status → laatste stap naar *Done* |
| Lead time | aangemaakt → *Done* |
| Work item age | eerste *In Progress* → nu, voor werk dat nu *In Progress* staat |
| Doorvoer | afgeronde items per week |
| WIP / CFD | per werkdag het aantal items per status |
| Velocity, say/do | uit Jira's eigen Sprint Report: toegezegd, toegevoegd, verwijderd, afgerond |

Statuscategorieën komen uit Jira zelf (`statusCategory`), op status-id: de
changelog bewaart statusnamen zoals ze toen heetten, soms in een andere taal,
dus een naam zegt niets. Epics en subtaken tellen niet mee. Issues waarvan alle overgangen binnen een uur
vallen (achteraf bijgewerkt) krijgen de vlag `backfilled` en vallen buiten de
percentielen.

## Installeren en draaien

Vereist [uv](https://docs.astral.sh/uv/) en een `creds.yaml` (zie
`creds.yaml.example`: Jira Data Center-PAT, Bearer).

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
uv run devops-flow MOD                      # laatste 6 maanden, met cache
uv run devops-flow MOD --months 12 --refresh
```

Windows (PowerShell):

```powershell
winget install --id=astral-sh.uv -e        # of: irm https://astral.sh/uv/install.ps1 | iex
uv sync
uv run devops-flow MOD
uv run devops-flow MOD --creds C:\Users\<naam>\github_repos\fo_doc_gen\creds.yaml
```

Niet getest op Windows. De code gebruikt geen POSIX-specifieke paden, maar dat
is niet geverifieerd.

| Optie | |
| --- | --- |
| `MOD` of een Jira-URL | het project (`…/browse/MOD-123` mag ook) |
| `--months N` | venster, default 6 |
| `--refresh` | negeer de cache en haal vers op |
| `--board ID` | ander scrumboard (default: het board waar de sprints van het project ontstaan) |
| `--creds PAD` | default: zoekt in de werkdirectory, de repo en fo_doc_gen |

## Wat eruit komt

In `output/<PROJECT>/`, elke run overschreven:

- `dashboard_<PROJECT>.xlsx` — kerncijfers (formules), cycle-time-scatter met
  P50/P85, doorvoer per week, cumulative flow, leeftijd lopend werk,
  sprints toegezegd vs afgerond (plus velocity als het team in punten schat)
- `items.csv` — één rij per issue
- `daily.csv` — één rij per werkdag, een kolom per status plus `wip`
- `sprints.csv` — één rij per afgesloten sprint
- `time_in_status.csv` — werkdagen per issue per status

De CSV's zijn voor een Nederlandstalige Excel geschreven (UTF-8 met BOM, `;`,
decimale komma) en openen met een dubbelklik in kolommen.

## Zelf testen

Stap voor stap, vanuit de repo-map. Op Windows zijn de commando's in
PowerShell gelijk, behalve het openen van het dashboard (stap 3).

1. **Rekenwerk** — offline, geen creds of netwerk nodig:

   ```bash
   uv run pytest
   ```

   Verwacht: `22 passed`. Faalt er iets, dan is het rekenwerk (feestdagen,
   werkdagen, cycle time, CFD, sprints) stuk; draai dan niet verder.

2. **Een echte run** — VPN aan, `creds.yaml` aanwezig:

   ```bash
   uv run devops-flow MOD --refresh
   ```

   Verwacht: een regel `board …: N afgesloten sprints in het venster` en een
   afsluitende `✓ … issues (… afgerond), N sprints → output/MOD`.
   Meldingen die je kunt tegenkomen:
   - `Jira niet bereikbaar` (de run stopt) — VPN of `jira.base_url` in `creds.yaml`.
   - `⚠️ onbekende status-ids` — die statussen tellen als To Do; meld het.
   - `⚠️ … geen sprintmetrics` — geen scrumboard gevonden; geef er een op met
     `--board ID` (het id staat in de board-URL: `…?rapidView=727`). Hetzelfde
     als de `board …`-regel een ander board noemt dan je verwacht.

3. **Het dashboard** — open `output/MOD/dashboard_MOD.xlsx`
   (macOS `open output/MOD/dashboard_MOD.xlsx`, Windows
   `start output\MOD\dashboard_MOD.xlsx`). Excel rekent de kerncijfers bij
   het openen uit; staan er lege cellen of `#WAARDE!`, druk dan op F9.

4. **Klopt het met Jira?** Twee steekproeven:
   - Sprints: open in Jira *Rapporten → Sprintrapport* (*Reports → Sprint
     Report*) voor een sprint en vergelijk met die rij in `sprints.csv`
     (toegezegd, toegevoegd, verwijderd, afgerond).
   - Cycle time: kies een afgerond issue in `items.csv`, open de *Geschiedenis*
     (*History*) in Jira en tel de werkdagen van de eerste stap naar een
     In Progress-status tot de laatste stap naar Done.

5. **Tweede run** (zonder `--refresh`) moet `… issues uit cache` melden en in
   seconden klaar zijn.

## Archief

De business case testautomatisering (incasso, TestRail, managementdeck) staat
bevroren in [`archive/business_case/`](archive/business_case/); tag `devops_01`
is de staat van vóór dit herontwerp.
