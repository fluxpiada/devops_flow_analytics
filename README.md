# devops_flow — flow- en sprintmetrics uit Jira, voor Excel

Leest de statusgeschiedenis van een Jira-project en zet die om in de standaard
Kanban- en Scrum-metrics. Python meet alleen; Excel presenteert. Geen
urenregistratie nodig, read-only.

## Wat het meet

Per item in **werkdagen**: weekenden en Nederlandse feestdagen tellen niet mee.

| Metric | Definitie |
| --- | --- |
| Cycle time | eerste stap naar een *In Progress*-status → laatste stap naar *Done* |
| Lead time | aangemaakt → *Done* |
| Work item age | eerste *In Progress* → nu, voor werk dat nu *In Progress* staat |
| Doorvoer | afgeronde items per week |
| WIP / CFD | per werkdag het aantal items per status |
| Velocity, say/do | uit Jira's eigen Sprint Report: toegezegd, toegevoegd, verwijderd, afgerond |

**Waardestroom** — per stap (elke To Do- en In Progress-status, in de volgorde
waarin het werk er werkelijk doorheen gaat) in **uren**:

| | Definitie |
| --- | --- |
| PT (process time) | uren binnen kantooruren (09–17, werkdagen) in de status. Een proxy, géén gemeten inspanning: er is nergens urenregistratie |
| LT (lead time) | kloktijd in de status, alle bezoeken opgeteld |
| %C&A | aandeel items dat de stap verliet en er nooit naar terugkwam |

Per stap staan de **modale klasse** (de meest voorkomende, in verdubbelende
klassen 1–2, 2–4, 4–8 h …) en de **mediaan**. Alleen afgeronde bezoeken tellen:
een item dat nu in een stap staat telt daar nog niet mee. Het totaal is de som
van de medianen, met de activiteitsratio (PT/LT) en de gerolde %C&A (het
product over alle stappen).

Statuscategorieën komen uit Jira zelf (`statusCategory`), op status-id: de
changelog bewaart statusnamen zoals ze toen heetten, soms in een andere taal,
dus een naam zegt niets. Epics en subtaken tellen niet mee. Issues waarvan alle
overgangen binnen een uur vallen (achteraf bijgewerkt) krijgen de vlag
`backfilled` en vallen buiten de percentielen en de waardestroom.

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

- `dashboard_<PROJECT>.xlsx` — tab *Dashboard*: kerncijfers (formules),
  cycle-time-scatter met P50/P85, doorvoer per week, cumulative flow, leeftijd
  lopend werk, sprints toegezegd vs afgerond (plus velocity als het team in
  punten schat); tab *Waardestroom*: de waardestroomkaart, een blok per stap
  met PT, LT en %C&A
- `items.csv` — één rij per issue
- `daily.csv` — één rij per werkdag, een kolom per status plus `wip`
- `sprints.csv` — één rij per afgesloten sprint
- `time_in_status.csv` — per issue per status: werkdagen, aantal bezoeken,
  `pt_hours`, `lt_hours` en `current` (staat er nu nog) — de bron van de
  waardestroom
- `value_stream.csv` — één rij per stap van de waardestroom

De CSV's zijn voor een Nederlandstalige Excel geschreven (UTF-8 met BOM, `;`,
decimale komma) en openen met een dubbelklik in kolommen.

## Zelf testen

Stap voor stap, vanuit de repo-map. Op Windows zijn de commando's in
PowerShell gelijk, behalve het openen van het dashboard (stap 3).

1. **Rekenwerk** — offline, geen creds of netwerk nodig:

   ```bash
   uv run pytest
   ```

   Verwacht: `32 passed`. Faalt er iets, dan is het rekenwerk (feestdagen,
   werkdagen, kantooruren, cycle time, CFD, sprints, waardestroom) stuk; draai
   dan niet verder.

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

5. **Waardestroom narekenen** — kies een stap in `value_stream.csv`, filter
   `time_in_status.csv` op die status met `current` = 0, en tel de items met
   `visits` = 1: gedeeld door het aantal rijen (plus de rijen met `current` = 1
   én `visits` > 1) is dat de %C&A. Kijk bij één item met `visits` > 1 in de
   *Geschiedenis* of het echt terugkwam.

6. **Tweede run** (zonder `--refresh`) moet `… issues uit cache` melden en in
   seconden klaar zijn.

## Archief

De business case testautomatisering (incasso, TestRail, managementdeck) staat
bevroren in [`archive/business_case/`](archive/business_case/); tag `devops_01`
is de staat van vóór dit herontwerp.
