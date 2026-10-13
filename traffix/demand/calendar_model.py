"""
The calendar model: combines every layer of config/calendar.yaml into
  level          multiplier on base demand (1.0 = normal weekday peak hour)
  inbound_share  share of trips heading INTO the centre
  ped_factor     multiplier on pedestrian demand

level = month factor x day factor x hour factor (Ramadan replaces the hour layer,
Eids and holidays replace the day layer, pre-Eid evenings add a surge).

This is the hidden "truth" used to generate traffic. Agents never call it.
"""
from datetime import datetime

from ..core import config
from . import hijri
from .sun import sunset_minutes


class CalendarModel:
    def __init__(self, cal=None, loc=None):
        self.c = cal or config.calendar()
        self.loc = loc or config.simulation()["location"]
        self.hourly = {int(h): (float(v), float(s)) for h, v, s in self.c["hourly_profile"]}

    def sunset(self, d):
        return sunset_minutes(d, self.loc["latitude"], self.loc["longitude"], self.loc["utc_offset"])

    def info(self, dt: datetime):
        ev = self.c["hijri_events"]
        h = hijri.info(dt.date(), ev["eid_al_fitr_days"], ev["eid_al_adha_days"], ev["pre_eid_days"])
        md = [dt.month, dt.day]
        return {**h, "hour": dt.hour, "minute": dt.minute, "weekday": dt.weekday(),
                "month": dt.month, "holiday": md in self.c["national_holidays"]["dates"],
                "minutes_to_sunset": self.sunset(dt.date()) - (dt.hour * 60 + dt.minute)}

    def _day_factor(self, i):
        ev = self.c["hijri_events"]
        if i["eid_al_fitr"]:
            return ev["eid_al_fitr_factor"]
        if i["eid_al_adha"]:
            return ev["eid_al_adha_factor"]
        if i["islamic_new_year"]:
            return ev["islamic_new_year_factor"]
        if i["mawlid"]:
            return ev["mawlid_factor"]
        if i["holiday"]:
            return self.c["national_holidays"]["factor"]
        return self.c["weekday_factor"][i["weekday"]]

    def _hour_normal(self, dt):
        h = dt.hour
        v0, share = self.hourly[h]
        v1, _ = self.hourly[(h + 1) % 24]
        frac = dt.minute / 60
        return v0 * (1 - frac) + v1 * frac, share, 1.0

    def _hour_ramadan(self, dt, i):
        r = self.c["ramadan_profile"]
        m = dt.hour * 60 + dt.minute
        to_sunset = i["minutes_to_sunset"]
        ped = 1.0
        if 0 <= to_sunset <= r["pre_iftar_minutes"]:
            seg = "pre_iftar_rush"
        elif -r["iftar_minutes"] <= to_sunset < 0:
            seg = "iftar"
        elif to_sunset < -r["iftar_minutes"]:
            seg = "evening" if dt.hour >= 21 else "after_iftar"
            ped = r["evening_pedestrian_factor"]
        elif m < 6 * 60:
            seg = "night"
        elif m < 9 * 60:
            seg = "morning_build"
        elif m < 10 * 60:
            seg = "morning_peak"
        else:
            seg = "midday"
        level, share = r[seg]
        return level, share, ped

    def level(self, dt: datetime):
        i = self.info(dt)
        if i["ramadan"]:
            hour_level, share, ped = self._hour_ramadan(dt, i)
        else:
            hour_level, share, ped = self._hour_normal(dt)
        level = self.c["month_factor"][dt.month] * self._day_factor(i) * hour_level
        if i["pre_eid"] and 17 <= dt.hour < 23:
            level *= self.c["hijri_events"]["pre_eid_evening_factor"]
        return level, share, ped
