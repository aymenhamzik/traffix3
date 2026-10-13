"""
Predictive traffic light agent (model predictive control). One per junction.

Instead of "which phase has the most pressure NOW?", it asks "if I choose this,
how much waiting will there be over the next 60 seconds?":

  1. predicts arrivals on every approach, slot by slot (5 s slots):
       - vehicles already moving towards the stop line (distance / speed)
       - vehicles the UPSTREAM junction will send: a trained model
         (models/arrivals.joblib) predicts entries in the next 30 s from the
         upstream junction's phase and queue, recent flow and the demand forecast
  2. checks room ahead: departures slow down when the DOWNSTREAM exit is full
  3. simulates a few plans with a fast queue model:
       keep the current green / switch now to phase k / switch in 10 s
     including the time lost to yellow and pedestrian clearance when switching
  4. proposes the first step of the plan with the least predicted waiting,
     and re-plans one second later (receding horizon)

It still only PROPOSES; the master and the safety rules decide. Without fresh
data it falls back to max-pressure (then actuated, then fixed-time).
"""
import json
import os

from ...core import config
from .observation import arrival_features, phase_lanes
from .traffic_light import TrafficLightAgent

SLOT, HORIZON = 5, 12            # 12 slots of 5 s = 60 s look-ahead
SAT_FLOW = 0.5                   # vehicles per second per lane while green (1,800/h)
PED_PERSON = 1.0                 # a waiting pedestrian weighs like a waiting car


class PredictiveTrafficLightAgent(TrafficLightAgent):
    name = "predictive_light"
    model_file = "arrivals.joblib"

    def __init__(self, ctx, tls, master):
        super().__init__(ctx, tls, master)
        self.arrival_model = self._load(self.model_file)
        self.edges = sorted({l.in_edge for l in self.m.vehicle_links})
        self.first_seen = {e: {} for e in self.edges}
        self.lost = config.agents()["safety"]["yellow"] + 2
        self.pp = dict(config.agents()["predictive"])
        tuned = config.path(self.cfg["models_dir"], "predictive_params.json")
        if ctx.use_models and os.path.exists(tuned):
            self.pp.update(json.load(open(tuned)))

    def _track(self, now):
        for e in self.edges:
            seen = self.first_seen[e]
            for l in self.m.incoming_lanes:
                if l.rsplit("_", 1)[0] == e:
                    for v in self.sensors.lane(l).ids:
                        seen.setdefault(v, now)
            for v in [v for v, t in seen.items() if now - t > 60]:
                del seen[v]

    def _entry_rates(self, now):
        """Entries per second expected on each approach. One batched model call every 5 s."""
        if now - getattr(self, "_rates_t", -99) < SLOT and hasattr(self, "_rates"):
            return self._rates
        recent = {e: sum(1 for t in self.first_seen[e].values() if now - t <= 30) for e in self.edges}
        if self.arrival_model is not None:
            X = [arrival_features(self.ctx, e, recent[e]) for e in self.edges]
            pred = self.arrival_model.predict(X)
            self._rates = {e: max(float(p), 0.0) / 30.0 for e, p in zip(self.edges, pred)}
        else:
            self._rates = {e: recent[e] / 30.0 for e in self.edges}
        self._rates_t = now
        return self._rates

    def _arrivals(self, now):
        """Expected arrivals at each lane's stop line, per slot."""
        out = {}
        for l in self.m.incoming_lanes:
            r = self.sensors.lane(l)
            slots = [0.0] * HORIZON
            for dist, speed in r.approach:
                k = int(dist / max(speed, 3.0) / SLOT)
                if k < HORIZON:
                    slots[k] += 1
            e = l.rsplit("_", 1)[0]
            rate = self._entry_rates(now).get(e, 0.0)
            n_lanes = sum(1 for x in self.m.incoming_lanes if x.rsplit("_", 1)[0] == e)
            travel = int(r.length / 12.0 / SLOT)
            for k in range(travel, HORIZON):
                slots[k] += rate * SLOT / max(n_lanes, 1)
            out[l] = slots
        return out

    def _cost(self, plan, arrivals, serve, room, peds):
        """Total vehicle-seconds of waiting (+ pedestrians) if the junction follows `plan`."""
        q = {l: float(self.sensors.lane(l).halting) for l in arrivals}
        cost = 0.0
        for k, phase in enumerate(plan):
            for l, a in arrivals.items():
                q[l] += a[k]
                if phase is not None and l in serve[phase]:
                    q[l] = max(0.0, q[l] - self.pp["sat_flow"] * SLOT * room[l])
                cost += q[l] * SLOT
            if phase is not None:
                # a waiting pedestrian costs more the longer they have already waited
                cost += self.pp["ped_person"] * sum(n * SLOT * (1 + (w + k * SLOT) / self.pp["ped_urgency"])
                                         for c, (n, w) in peds.items() if not self.m.crossing_green(phase, c))
        return cost

    def step(self, now):
        self._track(now)
        st = self.master.signal_status()
        if self.master.mode != "max_pressure":
            return super().step(now)                  # stale data: simpler modes
        green, tg = st["green"], st["time_in_green"]
        if st["busy"] or tg < self.cfg["safety"]["min_green"]:
            return
        arrivals = self._arrivals(now)
        serve = {ph: set(phase_lanes(self.m, ph)) for ph in self.m.green_phases}
        room = {}
        for l in arrivals:
            outs = [x.out_lane for x in self.m.vehicle_links if x.in_lane == l]
            full = max((self._downstream(o) * 7.5 / max(self.sensors.lane(o).length, 1)) for o in outs) if outs else 0
            room[l] = 0.2 if full > 0.85 else 1.0     # exit nearly full: little can leave
        peds = {c: self.sensors.waiting_at.get(c, (0, 0.0)) for c in self.m.crossings}
        lost = max(1, round(self.lost / SLOT))
        plans = {("keep",): [green] * HORIZON}
        for ph in self.m.green_phases:
            if ph != green:
                plans[("now", ph)] = [None] * lost + [ph] * (HORIZON - lost)
                plans[("later", ph)] = [green] * 2 + [None] * lost + [ph] * (HORIZON - 2 - lost)
        costs = {k: self._cost(p, arrivals, serve, room, peds) for k, p in plans.items()}
        best = min(costs, key=costs.get)
        if best[0] == "now" and costs[best] < costs[("keep",)] * (1 - self.pp["min_gain"]):
            self.send("PROPOSAL", self.tls, now, subject=best[1], reason="PREDICTIVE_SWITCH",
                      predicted_wait_keep=round(costs[("keep",)]), predicted_wait_switch=round(costs[best]),
                      horizon_s=SLOT * HORIZON,
                      arrivals_from="model" if self.arrival_model is not None else "recent flow")
