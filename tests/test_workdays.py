from datetime import date, datetime

import pytest

from devops_flow.workdays import (
    count_workdays,
    dutch_holidays,
    easter,
    is_workday,
    office_hours_between,
    workdays_between,
)


def holiday(year: int, name: str) -> date:
    return next(d for d, n in dutch_holidays(year).items() if n == name)


@pytest.mark.parametrize("year, want", [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)),
                                        (2026, date(2026, 4, 5)), (2027, date(2027, 3, 28))])
def test_easter(year, want):
    assert easter(year) == want


def test_holidays():
    assert holiday(2026, "Tweede Paasdag") == date(2026, 4, 6)
    assert holiday(2026, "Hemelvaartsdag") == date(2026, 5, 14)
    assert holiday(2026, "Tweede Pinksterdag") == date(2026, 5, 25)
    assert holiday(2025, "Koningsdag") == date(2025, 4, 26)  # 27 apr op zondag
    assert holiday(2026, "Koningsdag") == date(2026, 4, 27)
    assert "Bevrijdingsdag" in dutch_holidays(2025).values()
    assert "Bevrijdingsdag" not in dutch_holidays(2026).values()


def test_is_workday():
    assert is_workday(date(2026, 4, 3))       # Goede Vrijdag: gewoon werken
    assert not is_workday(date(2026, 5, 14))  # Hemelvaart
    assert not is_workday(date(2026, 5, 16))  # zaterdag


@pytest.mark.parametrize("start, end, want", [
    (datetime(2026, 5, 13, 9), datetime(2026, 5, 15, 9), 1.0),   # over Hemelvaart
    (datetime(2026, 5, 20, 9), datetime(2026, 5, 22, 9), 2.0),   # gewone week
    (datetime(2026, 1, 2, 9), datetime(2026, 1, 5, 9), 1.0),     # vr → ma
    (datetime(2026, 1, 5, 9), datetime(2026, 1, 5, 9, 10), 0.01),  # tien minuten
    (datetime(2026, 5, 14, 9), datetime(2026, 5, 14, 17), 0.0),  # op een feestdag
    (datetime(2026, 1, 3, 9), datetime(2026, 1, 4, 9), 0.0),     # weekend
    (datetime(2026, 1, 5, 9), datetime(2026, 1, 5, 9), 0.0),     # eind = start
])
def test_workdays_between(start, end, want):
    assert round(workdays_between(start, end), 2) == want


def test_count_workdays_christmas_week():
    # 21–27 dec 2026: ma–vr = 5, minus Eerste Kerstdag (vr); Tweede valt op za.
    assert count_workdays(date(2026, 12, 21), date(2026, 12, 28)) == 4


@pytest.mark.parametrize("start, end, want", [
    (datetime(2026, 1, 5, 10), datetime(2026, 1, 5, 12, 30), 2.5),  # binnen één dag
    (datetime(2026, 1, 5, 6), datetime(2026, 1, 5, 8), 0.0),         # vóór kantoortijd
    (datetime(2026, 1, 5, 16), datetime(2026, 1, 6, 10), 2.0),       # over de nacht
    (datetime(2026, 1, 9, 15), datetime(2026, 1, 12, 11), 4.0),      # over het weekend
    (datetime(2026, 1, 5, 9), datetime(2026, 1, 7, 17), 24.0),       # drie hele dagen
    (datetime(2026, 5, 13, 9), datetime(2026, 5, 15, 17), 16.0),     # over Hemelvaart
])
def test_office_hours_between(start, end, want):
    assert office_hours_between(start, end) == want
