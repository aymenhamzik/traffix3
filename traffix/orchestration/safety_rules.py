"""
Safety rules: hard rules between each master's decision and the executor.
Never learned. No master, directive or emergency request can get around them.

  1. Clearance  - a walk signal never ends while someone is still on the
                  crossing (up to MAX_CLEARANCE_HOLD, then it is logged).
  2. Exit check - green is pointless (and blocks the junction) if the exit
                  lane is full. Used for emergency and bus priority.
  3. Stale data - a junction whose data A4 marks stale drops to a mode that
                  does not need that data: max-pressure -> actuated -> fixed.
  4. Minimum green and yellow time (yellow is applied by the executor).
"""
from ..core import config

S = config.agents()["safety"]

VEHICLE_SPACE = 7.5   # metres per queued vehicle (5 m car + 2.5 m gap)


class SafetyRules:
    def __init__(self, models, sensors, bus, log):
        self.models, self.sensors, self.bus, self.log = models, sensors, bus, log

    # ---------------------------------------------------------------- 3. data mode
    def data_mode(self, tls):
        """Uses the sensor agents' DATA_STALE publications."""
        m = self.models[tls]
        stale = {p.subject for p in self.bus.published("DATA_STALE")}
        if any(l in stale for l in m.incoming_lanes):
            return "fixed"
        if any(l in stale for l in m.outgoing_lanes):
            return "actuated"
        return "max_pressure"

    # ---------------------------------------------------------------- 4. min green
    @staticmethod
    def min_green_ok(time_in_green, emergency=False):
        # Emergency may cut a minimum green short, never clearance or yellow.
        return emergency or time_in_green >= S["min_green"]

    # ---------------------------------------------------------------- 2. exit check
    def exit_ok(self, tls, index):
        link = self.models[tls].links[index]
        r = self.sensors.lane(link.out_lane)
        ratio = r.vehicles * VEHICLE_SPACE / max(r.length, 1.0)
        return ratio < S["exit_full_ratio"], link.out_lane, ratio

    # ---------------------------------------------------------------- 1. clearance
    def crossings_needing_clearance(self, tls, from_state, to_state):
        m = self.models[tls]
        return [c for c in m.crossings
                if m.crossing_green(from_state, c) and not m.crossing_green(to_state, c)]

    def clearance_done(self, tls, crossings, elapsed, now, ctx):
        """Called every second during a clearance interval. Returns True when
        the conflicting green may start. ctx is a per-transition dict."""
        holds = {r.subject for r in self.bus.inbox(tls, now, "CLEARANCE_HOLD")}
        occupied = [c for c in crossings
                    if self.sensors.on_crossing.get(c) or c in holds]
        if elapsed < 2 + ctx.get("extra_clearance", 0):   # longer in rain (weather directive)
            return False
        if not occupied:
            return True
        if elapsed >= S["max_clearance_hold"]:
            people = [p for c in occupied for p, _ in self.sensors.on_crossing.get(c, [])]
            self.log.log(now, "SafetyRules", "hold", "CLEARANCE_CAP_REACHED", tls=tls,
                         crossings=occupied, people_still_crossing=people,
                         held_seconds=elapsed)
            return True
        design = max(self.models[tls].crossings[c]["length"] for c in occupied) \
            / S["clearance_speed"]
        if elapsed > design and not ctx.get("extended"):
            ctx["extended"] = True
            people = [p for c in occupied for p, _ in self.sensors.on_crossing.get(c, [])]
            self.log.log(now, "SafetyRules", "hold", "CLEARANCE_EXTENDED", tls=tls,
                         crossings=occupied, people_still_crossing=people,
                         requested_by="pedestrian agent" if any(c in holds for c in occupied) else "sensor",
                         design_clearance_s=round(design, 1))
        return False
