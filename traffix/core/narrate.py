"""
Turns decision-log entries into plain sentences, without a language model.

Each reason code has a sentence template filled from the entry's details, with
readable names: junction names, street names, "bus 3 of line L1 east", clock
times. Deterministic, so it never states anything the log does not contain.
Used by the analyst page, the explainer (Synapse) and the persona pages.
"""
from datetime import datetime, timedelta

from .decision_log import REASON_CODES


def pct(x):
    return f"{x * 100:.0f}%" if isinstance(x, (int, float)) else "?"


def sec(x):
    if not isinstance(x, (int, float)):
        return "an unknown time"
    return f"{x:.0f} s" if x < 90 else f"{x / 60:.1f}".rstrip("0").rstrip(".") + " min"


def cap(s):
    return s[:1].upper() + s[1:]


class Narrator:
    def __init__(self, junction_names=None, edge_names=None, start=None):
        self.j = junction_names or {}
        self.edges = edge_names or {}
        self.start = start

    # ---------------------------------------------------------------- names
    def clock(self, t):
        return (self.start + timedelta(seconds=t)).strftime("%H:%M:%S") if self.start else f"t={t:.0f} s"

    def junction(self, tls):
        if not tls:
            return "a junction"
        name = self.j.get(tls)
        return f"{tls} ({name})" if name and name != tls else str(tls)

    def vehicle(self, v):
        v = str(v or "")
        if v.startswith("bus_"):
            line, _, n = v[4:].rpartition("_")
            return f"bus {n} of line {line.replace('_', ' ')}"
        for prefix, name in (("ambulance", "ambulance"), ("police", "police car"), ("fire", "fire truck")):
            if v.startswith(prefix) and v[len(prefix):].isdigit():
                return f"{name} {v[len(prefix):]}"
        return v or "a vehicle"

    def edge(self, e):
        e = str(e or "")
        name = self.edges.get(e)
        parts = e.split("_")
        direction = f" ({parts[0]} → {parts[1]})" if len(parts) == 2 else ""
        return f"{name}{direction}" if name else e

    def lane(self, l):
        l = str(l or "")
        edge, _, idx = l.rpartition("_")
        return f"lane {idx} of {self.edge(edge)}" if edge else l

    def crossing(self, c):
        c = str(c or "").lstrip(":")
        tls, _, n = c.partition("_c")
        return f"crossing {n} at {self.junction(tls)}" if n else c

    # ---------------------------------------------------------------- sentences
    def sentence(self, e):
        d, J = e.get("details", {}), self.junction(e.get("tls"))
        V = self.vehicle(d.get("vehicle"))
        gap, head = d.get("gap_s"), d.get("scheduled_headway_s", 240)
        templates = {
            "MAX_PRESSURE_SWITCH": lambda: f"{J} switched the green to the busier direction "
                                           f"(pressure {d.get('pressure_old', 0):.0f} → {d.get('pressure_new', 0):.0f}).",
            "CORRIDOR_PLATOON": lambda: f"{J} switched the green to let a group of cars arriving from the "
                                        f"neighbouring junction through (corridor coordination).",
            "PREDICTIVE_SWITCH": lambda: f"{J} switched early: its 60-second forecast predicted less waiting "
                                         f"({d.get('predicted_wait_switch', 0)} vs {d.get('predicted_wait_keep', 0)} vehicle-seconds).",
            "RL_POLICY_SWITCH": lambda: f"{J} switched the green on the learned policy's advice"
                                        + (" (starvation guard: someone had waited too long)." if d.get("method") == "starvation guard" else "."),
            "ACTUATED_GAP_OUT": lambda: f"{J}, in backup mode, ended a green after no more cars arrived ({sec(d.get('green_s'))} of green).",
            "ACTUATED_MAX_OUT": lambda: f"{J}, in backup mode, ended a green that reached its maximum length.",
            "FIXED_CYCLE": lambda: f"{J}, on its fixed backup plan, moved to the next phase.",
            "MODE_MAX_PRESSURE": lambda: f"{J} is back to normal smart control: all its sensors are working.",
            "MODE_ACTUATED": lambda: f"{J} switched to a backup mode because sensors on its exit roads stopped working.",
            "MODE_FIXED": lambda: f"{J} switched to its fixed backup plan because sensors on its approaches stopped working.",
            "EMERGENCY_REQUEST": lambda: f"{cap(V)} asked {J} for a green light, arriving in about {sec(d.get('eta_s'))}.",
            "EMERGENCY_PREPARE": lambda: f"The supermaster warned {J} that {V} will arrive in about {sec(d.get('eta_s'))}.",
            "EMERGENCY_GRANTED_SWITCH": lambda: f"{J} turned the light green for {V}; the road ahead had room.",
            "EMERGENCY_GRANTED_HOLD": lambda: f"{J} kept the light green for {V}, which was already on a green approach.",
            "EMERGENCY_DENIED_EXIT_FULL": lambda: f"{J} could not give {V} a green: the road ahead "
                                                  f"({self.lane(d.get('exit_lane'))}) was {pct(d.get('exit_occupancy'))} full, "
                                                  f"so a green would only have pushed it into the queue.",
            "EMERGENCY_DENIED_OTHER_EMERGENCY": lambda: f"{J} served {self.vehicle(d.get('served'))} first, so {V} had to wait.",
            "RECOVERY_STARTED": lambda: f"{cap(V)} passed {J}; normal control resumed "
                                        f"({d.get('queue_now', '?')} cars waiting, {d.get('queue_before', '?')} before the emergency).",
            "RECOVERED": lambda: f"Traffic at {J} was back to normal {sec(d.get('recovery_s'))} after the emergency vehicle passed.",
            "RECOVERY_INCOMPLETE": lambda: f"Traffic at {J} had not recovered within 10 minutes of the emergency.",
            "TRANSIT_REQUEST_LATE_BUS": lambda: f"{cap(V)} was running late ({sec(gap)} since the previous bus, scheduled every "
                                                f"{sec(head)}), so bus priority was requested at {J}.",
            "BUS_NOT_LATE": lambda: f"{cap(V)} reached {J} on time ({sec(gap)} after the previous bus, scheduled every "
                                    f"{sec(head)}), so no priority was needed.",
            "BUS_NO_REFERENCE": lambda: f"{cap(V)} reached {J}, but no earlier bus of its line had passed yet, so its delay "
                                        f"could not be judged: no priority requested.",
            "TRANSIT_GRANTED_EXTEND": lambda: f"{J} held its green a little longer for late {V}.",
            "TRANSIT_GRANTED_SWITCH": lambda: f"{J} switched the green for late {V}.",
            "TRANSIT_DENIED_EMERGENCY": lambda: f"{J} could not help late {V}: an emergency vehicle had priority.",
            "TRANSIT_DENIED_EXIT_FULL": lambda: f"{J} could not help late {V}: the road ahead was full.",
            "TRANSIT_DENIED_MIN_GREEN": lambda: f"{J} could not switch for late {V} yet: the current green had only just started.",
            "PED_SERVICE_REQUEST": lambda: f"{d.get('people_waiting', '?')} pedestrian(s) had waited {sec(d.get('longest_wait_s'))} at "
                                           f"{self.crossing(d.get('crossing'))}, so a walk signal was requested.",
            "PED_SERVICE_GRANTED": lambda: f"{J} gave a walk signal at {self.crossing(d.get('crossing'))}"
                                           + (f" after {sec(d.get('waited_s'))} of waiting." if d.get("waited_s") else "."),
            "PED_SERVICE_DEFERRED": lambda: f"{J} postponed a walk signal at {self.crossing(d.get('crossing'))}: the current green "
                                            f"had only just started or an emergency had priority.",
            "CLEARANCE_EXTENDED": lambda: f"{J} delayed the next green because someone was still on "
                                          f"{', '.join(self.crossing(c) for c in d.get('crossings', [])) or 'a crossing'}.",
            "CLEARANCE_CAP_REACHED": lambda: f"{J} reached its 30-second limit for waiting on a crossing; someone may still have been crossing.",
            "DATA_STALE": lambda: f"A detector on {self.lane(d.get('lane'))} stopped sending data "
                                  f"(last update {sec(d.get('last_update_s_ago'))} ago); it is marked unreliable.",
            "DATA_FRESH": lambda: f"The detector on {self.lane(d.get('lane'))} is sending data again.",
            "INCIDENT_SUSPECTED": lambda: f"A vehicle appears stuck on {self.lane(d.get('lane'))}, blocking a lane "
                                          f"({pct(d.get('confidence'))} confidence). The cause is not known.",
            "INCIDENT_CLEARED": lambda: f"{cap(self.lane(d.get('lane')))} is no longer blocked.",
            "CONGESTION_DETECTED": lambda: f"Heavy traffic on {self.edge(d.get('edge'))}: {d.get('stopped_vehicles', '?')} vehicles stopped.",
            "CONGESTION_CLEARED": lambda: f"Traffic on {self.edge(d.get('edge'))} is flowing again.",
            "REROUTE_ADVISORY": lambda: f"Drivers heading through {self.edge(d.get('edge'))} would save about "
                                        f"{sec(d.get('projected_saving_s'))} with a detour. Advice only; nobody was rerouted.",
            "REROUTE_NOT_WORTH": lambda: f"No detour around {self.edge(d.get('edge'))} would save meaningful time.",
            "WEATHER_RAIN": lambda: f"Rain reported ({pct(d.get('intensity'))} intensity): every junction lengthened its yellow "
                                    f"and crossing times; traffic expected about {pct(1 - d.get('expected_speed_factor', 1))} slower.",
            "WEATHER_CLEAR": lambda: "The rain stopped; normal signal timings restored.",
            "WEATHER_FLOOD": lambda: f"Flood alert: {self.edge(d.get('edge'))} is impassable; detours will avoid it.",
            "CORRIDOR_DIRECTION": lambda: f"Main traffic direction is now {d.get('direction', '?')}; corridor coordination follows it.",
            "OPERATOR_APPROVED": lambda: f"The operator approved the copilot suggestion: \"{d.get('suggestion', '')}\" (recorded, not applied automatically).",
            "OPERATOR_DISMISSED": lambda: f"The operator dismissed the copilot suggestion: \"{d.get('suggestion', '')}\".",
            "FORECAST_UPDATE": lambda: f"Forecast for {str(d.get('forecast_for', ''))[11:16] or 'the next half hour'}: traffic at "
                                       f"{pct(d.get('level'))} of the usual peak, {pct(d.get('inbound_share'))} heading into the centre.",
        }
        fn = templates.get(e["reason"])
        try:
            return fn() if fn else REASON_CODES.get(e["reason"], e["reason"])
        except Exception:                        # never fail on an odd entry
            return REASON_CODES.get(e["reason"], e["reason"])

    def describe(self, e):
        return f"{self.clock(e['t'])} · {self.sentence(e)}"

    def enrich(self, entries):
        return [{**e, "text": self.sentence(e), "clock": self.clock(e["t"])} for e in entries]
