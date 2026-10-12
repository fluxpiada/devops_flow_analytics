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
waarin het werk er werkelijk doorheen gaat) in **werkuren**: 1 werkdag = 8 uur,
weekend en feestdagen tellen niet. Tot en met 40 h in uren, daarboven in dagen
(h ÷ 8), dus 40 h = 5 d = een werkweek.

| | Definitie |
| --- | --- |
| PT (process time) | tijd in de stap, opgeteld over alle bezoeken. Per bezoek: korter dan 8 h → de echte duur; 8–24 h → 8 h (één werkdag); langer → 8 h per werkdag. Nooit meer dan LT. Een proxy, géén gemeten inspanning: er is nergens urenregistratie |
| LT (lead time) | elke werkdag waarop het item in de stap stond telt helemaal (00:00–23:59 = 8 h). Twee bezoeken op één dag tellen die dag één keer. LT ≥ PT; het verschil is de rest van de begin- en einddag, **géén** Lean-wachttijd |
| Bereik | natuurlijke proceslimieten, zie [Norm en uitschieters](#norm-en-uitschieters) |
| Uitschieters | items met LT boven de bovengrens |
| Doorgeklikt | items met PT onder 1 werkuur: overgeslagen of administratief doorgezet. Een vaste regel, geen statistiek |
| %C&A | aandeel items dat de stap verliet en er nooit naar werd *teruggestuurd*: een stap vanuit een latere status naar een status waar het item al was (Test → In uitvoering telt tegen In uitvoering). Opnieuw door Test ná de fix telt niet tegen Test |

Per stap staan het bereik en de **mediaan** van PT en LT. Alleen afgeronde
bezoeken tellen: een item dat nu in een stap staat telt daar nog niet mee. Het
totaal is de som van de medianen, met de gerolde %C&A (het product over alle
stappen). Een activiteitsratio (PT/LT) staat er bewust niet: met één klok voor
beide zegt die niets over wachten. De werkmap herhaalt deze definities als
legenda onder de kaart.

%C&A ziet alleen rework die als statuswijziging in Jira staat: wie een fout
herstelt terwijl het ticket in Test blijft staan, laat geen spoor na. Het getal
is dus eerder te hoog dan te laag. Terugzetten naar Te doen telt als rework van
Te doen, ook als het een planningskeuze was.

Statuscategorieën komen uit Jira zelf (`statusCategory`), op status-id: de
changelog bewaart statusnamen zoals ze toen heetten, soms in een andere taal,
dus een naam zegt niets. Epics en subtaken tellen niet mee. Issues waarvan alle
overgangen binnen een uur vallen (achteraf bijgewerkt) krijgen de vlag
`backfilled` en vallen buiten de percentielen en de waardestroom.

## Norm en uitschieters

Doorlooptijden zijn scheef: veel items gaan snel, een staart blijft lang
liggen. Daarom staat alles op de **mediaan**, niet op het gemiddelde, met
Wheeler's XmR-kaart (Deming/Shewhart, robuuste variant):

- **Centrum** = de mediaan van alle waarden.
- **Moving range** = |xᵢ − xᵢ₋₁|, met de items op volgorde van verlaten (stap)
  of afronden (cycle/lead time). Items die in dezelfde minuut verschoven — één
  klik, een batch — tellen samen als één punt (hun mediaan); anders zouden ze
  een rij moving ranges van 0 geven en de limieten laten instorten.
- **Limieten** = mediaan ± 3,145 × de mediaan van de moving ranges; is die 0,
  dan ± 2,66 × het gemiddelde. Zonder enige spreiding: geen limieten.
- **Boven de bovengrens** = een speciale oorzaak (vastgelopen, geblokkeerd,
  vergeten): uitzoeken. **Binnen** de grenzen = het systeem zelf: niet per item
  najagen, maar het systeem verbeteren.
- **De ondergrens** wordt getoond maar is bij scheve tijden vrijwel altijd 0, dus
  "te snel" komt statistisch zelden voor. Daarom de vaste regel *doorgeklikt*
  (onder 1 werkuur) voor de onderkant.

Per rij staan ook de **percentielrang** (als `PERCENTRANK.INC`: welk deel van de
andere items sneller was) en de **robuuste z** = (x − mediaan) / (1,4826 × MAD).
Een rang zegt wáár een item staat, niet óf het afwijkt: in de bovenste 10%
zit altijd 10% van de items. De vlag `hoog` komt alleen van de XmR-grens.

Let op stappen die geen echt proces zijn. *Te doen* is een backlog: daar
wacht werk op prioriteit, niet op beurt, en de tijden vallen in twee groepen
(meteen opgepakt, of maanden blijven liggen). XmR markeert dan een groot deel
als uitschieter — dat is geen fout in de som, maar het signaal dat die stap
niet stabiel is. Hetzelfde geldt voor de lead time na een opruimactie waarin
oude tickets in één keer zijn gesloten, of na een migratie waarin tickets in
één keer zijn aangemaakt: de lead-time-uitschieters liggen dan op een schuine
lijn in de tijd, want hun lead time telt vanaf de importdatum, niet vanaf de
echte vraag. Daarom staat er geen lead-time-XmR-kaart op het dashboard.

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

| Optie | Default | |
| --- | --- | --- |
| `MOD` of een Jira-URL | — (verplicht) | het project (`…/browse/MOD-123` mag ook) |
| `--months N` | 6 | het venster: items afgerond in de laatste N maanden plus alles wat nog open is; ook de sprints |
| `--refresh` | uit | negeer de cache en haal vers op. Een ander `--months` haalt sowieso vers op |
| `--board ID` | het board waar de sprints van het project ontstaan | ander scrumboard; het id staat in de board-URL (`…?rapidView=727`) |
| `--creds PAD` | zoekt in de werkdirectory, de repo en fo_doc_gen | pad naar `creds.yaml` |
| `--out-dir PAD` | `output` | map voor de resultaten; daaronder komt `<PROJECT>/` |
| `-h`, `--help` | | toont deze opties |

Voorbeelden (macOS / Linux; in PowerShell gelijk, alleen paden met `\`):

```bash
uv run devops-flow MOD                                    # 6 maanden, met cache
uv run devops-flow MOD --months 12 --refresh              # een jaar, vers uit Jira
uv run devops-flow https://jira.vitens.lan/jira/browse/MOD-123
uv run devops-flow MOD --board 727                        # vast scrumboard
uv run devops-flow MOD --out-dir rapport_q3               # → rapport_q3/MOD/
```

```powershell
uv run devops-flow MOD --months 12 --refresh
uv run devops-flow MOD --creds C:\Users\<naam>\github_repos\fo_doc_gen\creds.yaml
uv run devops-flow MOD --out-dir C:\Users\<naam>\Documents\flow
```

De resultaten worden elke run overschreven. Wil je een eerdere run bewaren,
geef dan een andere `--out-dir` of hernoem de map eerst.

## Wat eruit komt

In `output/<PROJECT>/`, elke run overschreven:

- `dashboard_<PROJECT>.xlsx` — tab *Dashboard*: links de kerncijfers
  (formules, met aantallen uitschieters), rechts vijf grafieken:

  | | links | rechts |
  | --- | --- | --- |
  | boven | cycle time per afgerond item (XmR) | leeftijd lopend werk |
  | midden | doorvoer per week | sprints toegezegd vs afgerond (plus velocity als het team in punten schat) |
  | onder | cumulative flow | |

  De XmR-kaart toont de items op volgorde van afronden met de mediaan, de
  bovengrens (UPL) en ondergrens (LPL) als rode stippellijn, de uitschieters
  in rood en de P85 (grijs gestippeld) als verwachting. Een lead-time-kaart
  staat er bewust niet: na een migratie tellen veel items vanaf de
  importdatum (zie [Norm en uitschieters](#norm-en-uitschieters)); de
  lead-time-kerncijfers en de `lt_`-kolommen in `items.csv` blijven. Tab *Waardestroom*: de waardestroomkaart, een blok per stap met
  PT en LT (bereik en mediaan), uitschieters, doorgeklikt en %C&A, met de
  legenda eronder; tab *XmR*: de reeks en lijnen achter de XmR-kaart
- `items.csv` — één rij per issue, met per afgerond item voor cycle time (`ct_`)
  en lead time (`lt_`): `pct_rank`, `robust_z` en `outlier` (`hoog`/`laag`/leeg)
- `daily.csv` — één rij per werkdag, een kolom per status plus `wip`
- `sprints.csv` — één rij per afgesloten sprint
- `time_in_status.csv` — per issue per status: werkdagen, aantal bezoeken,
  `pt_hours`, `lt_hours`, `sent_back` (keren teruggestuurd), `current` (staat
  er nu nog), `left_at` (laatste keer verlaten), en voor de LT `lt_pct_rank`,
  `lt_robust_z`, `outlier` en `doorgeklikt` — de bron van de waardestroom
- `value_stream.csv` — één rij per stap: mediaan, onder- en bovengrens van PT
  en LT, aantallen uitschieters, doorgeklikt en %C&A

De CSV's zijn voor een Nederlandstalige Excel geschreven (UTF-8 met BOM, `;`,
decimale komma) en openen met een dubbelklik in kolommen.

## Zelf testen

Stap voor stap, vanuit de repo-map. Op Windows zijn de commando's in
PowerShell gelijk, behalve het openen van het dashboard (stap 3).

1. **Rekenwerk** — offline, geen creds of netwerk nodig:

   ```bash
   uv run pytest
   ```

   Verwacht: `48 passed`. Faalt er iets, dan is het rekenwerk (feestdagen,
   werkdagen, werkuren, cycle time, CFD, sprints, waardestroom, XmR-limieten)
   stuk; draai dan niet verder.

2. **Een echte run** — VPN aan, `creds.yaml` aanwezig:

   ```bash
   uv run devops-flow MOD --months 12 --refresh
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

5. **Waardestroom narekenen** — kies een stap in `value_stream.csv` en filter
   `time_in_status.csv` op die status. Laat de rijen weg met `current` = 1 én
   `visits` = 1 (die zijn er voor het eerst en nog bezig). Van de rest is het
   aandeel met `sent_back` = 0 de %C&A. Kijk bij één item met `sent_back` > 0
   in de *Geschiedenis* (*History*) of het echt vanuit een latere stap
   terugkwam.

   De limieten: neem van die stap de rijen met `current` = 0, sorteer op
   `left_at` en neem de mediaan van `lt_hours` (= `lt_median_h`). Maak een
   kolom met het verschil met de rij erboven (zonder min-teken; rijen met
   dezelfde minuut in `left_at` eerst samenvoegen tot hun mediaan). De
   bovengrens is de mediaan + 3,145 × de mediaan van die verschillen; het
   aantal rijen erboven is het aantal uitschieters (`outlier` = `hoog`).

6. **Tweede run** (zonder `--refresh`) moet `… issues uit cache` melden en in
   seconden klaar zijn.

## Archief

De business case testautomatisering (incasso, TestRail, managementdeck) staat
bevroren in [`archive/business_case/`](archive/business_case/); tag `devops_01`
is de staat van vóór dit herontwerp.
