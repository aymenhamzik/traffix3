"""
Master: one per junction. The arbiter and the ONLY writer of its light.

Every second the master:
  1. lets its five junction agents observe and post (requests, proposal)
  2. sets its control mode from data health (via the safety rules)
  3. resolves everything in the fixed priority order:
       safety > emergency > supermaster directive > transit > pedestrian > normal
  4. sends the winning action through the safety rules to the executor
  5. publishes its status for neighbours and the supermaster
"""
from ..agents.junction.emergency_priority import EmergencyPriorityAgent
from ..agents.junction.pedestrian import PedestrianAgent
from ..agents.junction.predictive_light import PredictiveTrafficLightAgent
from ..agents.junction.rl_light import RLTrafficLightAgent
from ..agents.junction.sensor_health import SensorHealthAgent
from ..agents.junction.traffic_light import TrafficLightAgent
from ..agents.junction.transit_priority import TransitPriorityAgent
from ..core import config

MODE_REASON = {"max_pressure": "MODE_MAX_PRESSURE", "actuated": "MODE_ACTUATED", "fixed": "MODE_FIXED"}
RECOVERY_LIMIT = 600


LIGHT_AGENTS = {"max_pressure": TrafficLightAgent, "predictive": PredictiveTrafficLightAgent,
                "rl": RLTrafficLightAgent}


class Master:
    def __init__(self, ctx, tls, safety, executor, light="max_pressure"):
        self.ctx, self.tls, self.m = ctx, tls, ctx.models[tls]
        self.bus, self.log, self.sensors = ctx.bus, ctx.log, ctx.sensors
        self.safety, self.ex = safety, executor
        self.name = f"master@{tls}"
        self.mode = "max_pressure"
        self.sensor_agent = SensorHealthAgent(ctx, tls, self)
        self.emergency_agent = EmergencyPriorityAgent(ctx, tls, self)
        self.transit_agent = TransitPriorityAgent(ctx, tls, self)
        self.pedestrian_agent = PedestrianAgent(ctx, tls, self)
        self.light_agent = LIGHT_AGENTS[light](ctx, tls, self)
        self.agents = [self.sensor_agent, self.emergency_agent, self.transit_agent,
                       self.pedestrian_agent, self.light_agent]
        self.logged, self.preempt, self.recovery = set(), None, None
        self.queue_before, self.transit_hold = 0, None
        self.min_green = config.agents()["safety"]["min_green"]

    # ------------------------------------------------------------ helpers
    def signal_status(self):
        return self.ex.status(self.tls)

    def _once(self, now, event, reason, key, **d):
        if (key, reason) not in self.logged:
            self.logged.add((key, reason))
            self.log.log(now, self.name, event, reason, tls=self.tls, **d)

    def _queue(self):
        return sum(self.sensors.lane(l).halting for l in self.m.incoming_lanes)

    def _timing(self, now):
        w = self.bus.inbox(self.tls, now, "WEATHER_TIMING")
        return (w[0].details["extra_yellow"], w[0].details["extra_clearance"]) if w else (0, 0)

    def _switch(self, now, target, emergency=False):
        ey, ec = self._timing(now)
        return self.ex.request(self.tls, target, now, emergency, ey, ec)

    # ------------------------------------------------------------ main loop
    def step(self, now):
        mode = self.safety.data_mode(self.tls)
        if mode != self.mode:
            self.mode = mode
            self.log.log(now, self.name, "mode", MODE_REASON[mode], tls=self.tls)
        for a in self.agents:
            a.step(now)
        st = self.signal_status()
        if not st["busy"]:
            if not self._emergency(now, st):
                self._track_recovery(now)
                if not self._transit(now, st):
                    if not self._pedestrians(now, st):
                        self._normal(now, st)
        self._publish_status(now)

    def _publish_status(self, now):
        st = self.signal_status()
        green = st["green"]
        self.bus.status[self.tls] = {
            "t": now, "green": green, "mode": self.mode, "busy": st["busy"],
            "incoming_queue": {l: self.sensors.lane(l).halting for l in self.m.incoming_lanes},
            "queue_total": self._queue(),
            "released_edges": sorted({l.out_edge for l in self.m.vehicle_links if green[l.index] in "Gg"}),
            "preempt": self.preempt.subject if self.preempt else None,
            "name": self.m.name}

    # ------------------------------------------------------------ emergency
    def _emergency(self, now, st):
        local = self.bus.inbox(self.tls, now, "EMERGENCY")
        local_ids = {r.subject for r in local}
        prepare = [d for d in self.bus.inbox(self.tls, now, "EMERGENCY_PREPARE") if d.subject not in local_ids]
        reqs = sorted(local + prepare, key=lambda r: r.details.get("eta", 0))
        if not reqs:
            if self.preempt:
                self.log.log(now, self.name, "recovery", "RECOVERY_STARTED", tls=self.tls,
                             vehicle=self.preempt.subject, queue_before=self.queue_before,
                             queue_now=self._queue())
                self.recovery, self.preempt = now, None
            return False
        req = reqs[0]
        via = "supermaster directive" if req.kind == "EMERGENCY_PREPARE" else "junction agent"
        for other in reqs[1:]:
            if other.subject != req.subject:
                self._once(now, "deny", "EMERGENCY_DENIED_OTHER_EMERGENCY", other.subject,
                           vehicle=other.subject, served=req.subject)
        for t in self.bus.inbox(self.tls, now, "TRANSIT"):
            self._once(now, "deny", "TRANSIT_DENIED_EMERGENCY", t.subject, vehicle=t.subject)
        if self.preempt is None:
            self.queue_before = self._queue()
        if st["green"][req.link_index] in "Gg":
            self._once(now, "grant", "EMERGENCY_GRANTED_HOLD", req.subject, vehicle=req.subject,
                       eta_s=req.details.get("eta"), via=via)
            self.preempt = req
            return True
        ok, lane, ratio = self.safety.exit_ok(self.tls, req.link_index)
        if not ok:
            self._once(now, "deny", "EMERGENCY_DENIED_EXIT_FULL", req.subject, vehicle=req.subject,
                       exit_lane=lane, exit_occupancy=ratio, via=via)
            return False
        target = self.m.phases_serving(req.link_index)[0]
        if self._switch(now, target, emergency=True):
            self._once(now, "grant", "EMERGENCY_GRANTED_SWITCH", req.subject, vehicle=req.subject,
                       eta_s=req.details.get("eta"), exit_lane=lane, exit_occupancy=ratio, via=via)
            self.preempt = req
        return True

    def _track_recovery(self, now):
        if self.recovery is None:
            return
        elapsed = now - self.recovery
        if self._queue() <= self.queue_before * 1.1 + 2:
            self.log.log(now, self.name, "recovery", "RECOVERED", tls=self.tls, recovery_s=elapsed)
            self.recovery = None
        elif elapsed > RECOVERY_LIMIT:
            self.log.log(now, self.name, "recovery", "RECOVERY_INCOMPLETE", tls=self.tls,
                         queue_before=self.queue_before, queue_now=self._queue())
            self.recovery = None

    # ------------------------------------------------------------ transit
    def _transit(self, now, st):
        reqs = self.bus.inbox(self.tls, now, "TRANSIT")
        if not reqs:
            self.transit_hold = None
            return False
        req = reqs[0]
        if st["green"][req.link_index] in "Gg":
            self.transit_hold = self.transit_hold or now
            if now - self.transit_hold <= config.agents()["transit"]["max_extension"]:
                self._once(now, "grant", "TRANSIT_GRANTED_EXTEND", req.subject, vehicle=req.subject,
                           gap_s=req.details.get("gap"))
                return True
            return False
        if st["time_in_green"] < self.min_green:
            self._once(now, "deny", "TRANSIT_DENIED_MIN_GREEN", req.subject, vehicle=req.subject)
            return False
        ok, lane, ratio = self.safety.exit_ok(self.tls, req.link_index)
        if not ok:
            self._once(now, "deny", "TRANSIT_DENIED_EXIT_FULL", req.subject, vehicle=req.subject,
                       exit_lane=lane, exit_occupancy=ratio)
            return False
        if self._switch(now, self.m.phases_serving(req.link_index)[0]):
            self._once(now, "grant", "TRANSIT_GRANTED_SWITCH", req.subject, vehicle=req.subject,
                       gap_s=req.details.get("gap"))
            return True
        return False

    # ------------------------------------------------------------ pedestrians
    def _pedestrians(self, now, st):
        for req in self.bus.inbox(self.tls, now, "PED_SERVICE"):
            if self.m.crossing_green(st["green"], req.subject):
                continue
            if st["time_in_green"] < self.min_green:
                self._once(now, "deny", "PED_SERVICE_DEFERRED", (req.subject, req.id), crossing=req.subject)
                continue
            options = [p for p in self.m.green_phases if self.m.crossing_green(p, req.subject)]
            target = max(options, key=self.light_agent.pressure)
            if self._switch(now, target):
                self._once(now, "grant", "PED_SERVICE_GRANTED", (req.subject, req.id), crossing=req.subject,
                           waited_s=req.details.get("wait"), people=req.details.get("people"))
                return True
        return False

    # ------------------------------------------------------------ normal control
    def _normal(self, now, st):
        for p in self.bus.inbox(self.tls, now, "PROPOSAL"):
            if p.t < now:
                continue                       # only this second's proposal
            if self._switch(now, p.subject):
                d = {k: v for k, v in p.details.items() if k != "reason"}
                self.log.log(now, self.name, "switch", p.details["reason"], tls=self.tls,
                             mode=self.mode, **d)
            return
