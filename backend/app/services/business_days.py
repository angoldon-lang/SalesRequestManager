"""Giorni lavorativi italiani (sabato/domenica e festività nazionali escluse)."""
from datetime import date, timedelta
from functools import lru_cache


def _easter(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


@lru_cache(maxsize=16)
def holidays(year: int) -> frozenset[date]:
    fixed = [(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8), (12, 25), (12, 26)]
    days = {date(year, m, d) for m, d in fixed}
    days.add(_easter(year) + timedelta(days=1))  # Lunedì dell'Angelo
    return frozenset(days)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in holidays(d.year)


def business_days_between(start: date, end: date) -> int:
    """Giorni lavorativi trascorsi dopo `start` fino a `end` incluso."""
    n, cur = 0, start
    while cur < end:
        cur += timedelta(days=1)
        if is_business_day(cur):
            n += 1
    return n
