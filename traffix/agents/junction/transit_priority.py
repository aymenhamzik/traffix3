"""
Transit priority agent (one per junction). ASKS for priority for LATE buses only.

Lateness comes from the network's transit monitoring agent when the
supermaster runs; without it (junction_only), a local rule compares the gap
since the previous bus of the line with the scheduled headway.
Learned (models/bus_eta.joblib): predicts when the bus will actually reach the
stop line, so the request is sent just in time rather than holding green early.
"""
from ...core import config
from ..base import Agent


class TransitPriorityAgent(Agent):
    name = "transit_priority"
    model_file = "bus_eta.joblib"

    def __init__(self, ctx, tls, master):
        super().__init__(ctx, tls)
        self.headway = config.simulation()["demand"]["bus_headway"]
        self.prev, self.last_pass, self.decided = set(), {}, {}

    def eta(self, v):
        if self.model is not None:
            return float(self.model.predict([[v.distance, v.speed, v.lane_halting]])[0])
        return v.distance / max(v.speed, 2.0)

    def step(self, now):
        buses = {v.id: v for v in self.sensors.approaching.get(self.tls, []) if v.kind == "bus"}
        for b in self.prev - set(buses):
            line = self.decided.get(b, (None, None, None))[2]
            if line:
                self.last_pass[line] = now
        self.prev = set(buses)
        tc = self.cfg["transit"]
        for v in buses.values():
            if v.distance > tc["detect_distance"]:
                continue
            if v.id not in self.decided:
                late_pub = self.bus.publications.get(("TRANSIT_LATE", v.id))
                status = self.bus.publications.get(("TRANSIT_STATUS", v.id))
                known_gap = status is not None and status.details.get("gap_s") is not None
                if late_pub is not None or known_gap:
                    late = late_pub is not None
                    gap = late_pub.details["gap"] if late_pub else status.details["gap_s"]
                elif v.line in self.last_pass:
                    gap = now - self.last_pass[v.line]
                    late = gap > tc["late_factor"] * self.headway
                else:
                    self.decided[v.id] = (False, None, v.line)
                    self.log.log(now, self.label, "abstain", "BUS_NO_REFERENCE", tls=self.tls,
                                 vehicle=v.id, line=v.line)
                    continue
                self.decided[v.id] = (late, gap, v.line)
                self.log.log(now, self.label, "request" if late else "abstain",
                             "TRANSIT_REQUEST_LATE_BUS" if late else "BUS_NOT_LATE", tls=self.tls,
                             vehicle=v.id, line=v.line, gap_s=gap, scheduled_headway_s=self.headway)
            late, gap, _ = self.decided[v.id]
            if late and self.eta(v) <= 30:
                self.send("TRANSIT", self.tls, now, subject=v.id, link_index=v.link_index,
                          gap=round(gap or 0, 1), eta=round(self.eta(v), 1))
