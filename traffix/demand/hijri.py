"""Hijri calendar facts for a Gregorian date: Ramadan, Eids, pre-Eid days, holidays.
Ramadan moves about 11 days earlier every Gregorian year; this module finds it."""
from datetime import date, timedelta
from functools import lru_cache

from hijridate import Gregorian


@lru_cache(maxsize=4096)
def hijri(d: date):
    h = Gregorian(d.year, d.month, d.day).to_hijri()
    return h.year, h.month, h.day


@lru_cache(maxsize=4096)
def info(d: date, eid_fitr_days=2, eid_adha_days=2, pre_eid_days=3):
    _, m, day = hijri(d)
    out = {"hijri_month": m, "hijri_day": day, "ramadan": m == 9,
           "eid_al_fitr": m == 10 and day <= eid_fitr_days,
           "eid_al_adha": m == 12 and 10 <= day < 10 + eid_adha_days,
           "islamic_new_year": m == 1 and day == 1,
           "mawlid": m == 3 and day == 12,
           "pre_eid": False}
    for k in range(1, pre_eid_days + 1):
        _, m2, d2 = hijri(d + timedelta(days=k))
        if (m2 == 10 and d2 == 1) or (m2 == 12 and d2 == 10):
            out["pre_eid"] = True
    return out
