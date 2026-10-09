"""Werkdagen: ma–vr minus de Nederlandse landelijke feestdagen.

Eén maat voor alle duren in deze tool. Een deel van een dag telt naar rato van
het etmaal: er is nergens urenregistratie, dus een kantoorurenvenster (09–17)
zou een precisie suggereren die de data niet heeft.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache


def easter(year: int) -> date:
    """Eerste Paasdag — anoniem Gregoriaans algoritme (Meeus/Jones/Butcher).

    Berekend in plaats van opgezocht, zodat er geen tabel is die over een paar
    jaar stilletjes verloopt.
    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def dutch_holidays(year: int) -> dict[date, str]:
    """Landelijke vrije dagen in Nederland, met hun naam.

    Twee keuzes die per werkgever kunnen verschillen:
    - **Goede Vrijdag zit er NIET in** — onder de meeste CAO's geen vrije dag.
    - **Bevrijdingsdag alleen in lustrumjaren** (2025, 2030, …).
    Wijkt dat af voor deze organisatie, dan is dit de enige plek die aanpassing
    vraagt.
    """
    e = easter(year)
    out = {
        date(year, 1, 1): "Nieuwjaarsdag",
        e + timedelta(days=1): "Tweede Paasdag",
        e + timedelta(days=39): "Hemelvaartsdag",
        e + timedelta(days=50): "Tweede Pinksterdag",
        date(year, 12, 25): "Eerste Kerstdag",
        date(year, 12, 26): "Tweede Kerstdag",
    }
    kings = date(year, 4, 27)
    if kings.weekday() == 6:  # op zondag wordt Koningsdag daags ervoor gevierd
        kings = date(year, 4, 26)
    out[kings] = "Koningsdag"
    if year % 5 == 0:
        out[date(year, 5, 5)] = "Bevrijdingsdag"
    return out


@lru_cache(maxsize=64)
def _holiday_dates(year: int) -> frozenset[date]:
    return frozenset(dutch_holidays(year))


def is_workday(day: date) -> bool:
    """Ma–vr én geen landelijke feestdag."""
    return day.weekday() < 5 and day not in _holiday_dates(day.year)


def count_workdays(first: date, last: date) -> int:
    """Hele werkdagen in [first, last), zonder per dag te itereren."""
    if last <= first:
        return 0
    weeks, rem = divmod((last - first).days, 7)
    n = weeks * 5 + sum(1 for i in range(rem)
                        if (first + timedelta(days=i)).weekday() < 5)
    for year in range(first.year, last.year + 1):
        n -= sum(1 for d in _holiday_dates(year)
                 if first <= d < last and d.weekday() < 5)
    return n


def workdays_between(start: datetime, end: datetime) -> float:
    """Verstreken tijd in werkdagen; tien minuten is 0,01 dag, niet 1."""
    if end <= start:
        return 0.0
    s_day, e_day = start.date(), end.date()
    if s_day == e_day:
        return (end - start).total_seconds() / 86400 if is_workday(s_day) else 0.0
    total = 0.0
    if is_workday(s_day):  # restant van de startdag
        total += (datetime.combine(s_day + timedelta(days=1), time.min)
                  - start).total_seconds() / 86400
    total += count_workdays(s_day + timedelta(days=1), e_day)
    if is_workday(e_day):  # aanloop van de einddag
        total += (end - datetime.combine(e_day, time.min)).total_seconds() / 86400
    return total
