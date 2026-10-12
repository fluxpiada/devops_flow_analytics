"""Robuuste norm en uitschieters: Wheeler's XmR-kaart met medianen.

Puur rekenwerk. Doorlooptijden zijn scheef (een lange staart trage items), dus
alles is op de mediaan gebouwd, niet op het gemiddelde:

- centrum      = mediaan van alle waarden
- moving range = |xᵢ − xᵢ₋₁| in tijdsvolgorde
- limieten     = mediaan ± 3,145 × mediaan(moving range), ondergrens minimaal 0
- robuuste z   = (x − mediaan) / (1,4826 × MAD)

Buiten de limieten = speciale oorzaak, uitzoeken. Binnen = het systeem zelf.
"""

from __future__ import annotations

import statistics
from collections.abc import Hashable, Iterable
from itertools import pairwise

XMR_MEDIAN_K = 3.145  # Wheeler: limieten uit de mediaan van de moving ranges
XMR_MEAN_K = 2.66     # klassiek: uit het gemiddelde — alleen als terugval
MAD_SIGMA = 1.4826    # MAD → σ bij een normale verdeling


Limits = tuple[float, float | None, float | None]


def xmr(series: Iterable[tuple[Hashable, float]]) -> Limits | None:
    """(centrum, ondergrens, bovengrens) uit (tijdstip, waarde)-paren.

    Waarden met hetzelfde tijdstip worden eerst tot hun mediaan samengevoegd:
    werk dat in één klik verschuift (een batch) geeft anders een reeks
    identieke buren, een moving range van 0 en limieten die samenvallen met
    het centrum. Is de mediaan van de moving ranges dan nog 0, dan vallen we
    terug op het gemiddelde (× 2,66). Zonder spreiding (één punt, of alle
    punten gelijk) zijn er geen limieten: ondergrens en bovengrens zijn None,
    en niets is een uitschieter.
    """
    series = sorted(series, key=lambda p: p[0])
    if not series:
        return None
    centre = statistics.median(v for _, v in series)  # alle waarden: ligt altijd binnen de limieten
    groups: dict[Hashable, list[float]] = {}
    for t, v in series:
        groups.setdefault(t, []).append(v)
    points = [statistics.median(vs) for vs in groups.values()]
    ranges = [abs(b - a) for a, b in pairwise(points)]
    width = ranges and (XMR_MEDIAN_K * statistics.median(ranges)
                        or XMR_MEAN_K * statistics.mean(ranges))
    if not width:
        return centre, None, None
    return centre, max(centre - width, 0.0), centre + width


def robust_z(x: float, values: list[float]) -> float | None:
    """Hoeveel robuuste σ ligt x van de mediaan? None als de MAD 0 is."""
    med = statistics.median(values)
    mad = statistics.median(abs(v - med) for v in values)
    return (x - med) / (MAD_SIGMA * mad) if mad else None


def percent_rank(x: float, values: list[float]) -> float:
    """Aandeel van de andere waarden dat kleiner is — als PERCENTRANK.INC."""
    return sum(v < x for v in values) / (len(values) - 1) if len(values) > 1 else 0.0


def side(x: float, lower: float | None, upper: float | None) -> str:
    """"hoog" boven de bovengrens, "laag" onder een ondergrens > 0, anders ""."""
    if upper is not None and x > upper:
        return "hoog"
    return "laag" if lower and x < lower else ""
