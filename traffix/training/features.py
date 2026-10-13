"""Feature builders shared by agents and training (no simulation access)."""
from datetime import datetime

from ..demand import hijri
from ..demand.sun import sunset_minutes
from ..core import config


def calendar_features(when: datetime):
    """What a forecasting agent may know: the date and time, and public calendar
    facts (Hijri date, sunset). Never the calendar assumption values."""
    loc = config.simulation()["location"]
    h = hijri.info(when.date())
    minute = when.hour * 60 + when.minute
    to_sunset = sunset_minutes(when.date(), loc["latitude"], loc["longitude"], loc["utc_offset"]) - minute
    return [when.hour + when.minute / 60, when.weekday(), when.month,
            int(h["ramadan"]), to_sunset, int(h["eid_al_fitr"] or h["eid_al_adha"]),
            int(h["pre_eid"]), int(h["islamic_new_year"] or h["mawlid"]),
            int([when.month, when.day] in config.calendar()["national_holidays"]["dates"])]


FEATURE_NAMES = ["hour", "weekday", "month", "ramadan", "minutes_to_sunset", "eid",
                 "pre_eid", "religious_holiday", "national_holiday"]
