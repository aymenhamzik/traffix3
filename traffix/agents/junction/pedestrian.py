"""
Pedestrian agent (one per junction). ASKS for walk signals and clearance holds.

Rule: request a walk signal once someone has waited longer than max_wait.
Learned (models/pedestrian.joblib): a classifier predicts, from the current
queue and signal state, whether this group is heading for a long wait
(over 60 s), so it can ask earlier.
"""
from ..base import Agent


class PedestrianAgent(Agent):
    name = "pedestrian"
    model_file = "pedestrian.joblib"

    def __init__(self, ctx, tls, master):
        super().__init__(ctx, tls)
        self.master, self.m = master, ctx.models[tls]
        self.episode = set()

    def features(self, crossing, count, wait):
        st = self.master.signal_status()
        queue = sum(self.sensors.lane(l).halting for l in self.m.incoming_lanes)
        return [count, wait, st["time_in_green"], queue]

    def step(self, now):
        max_wait = self.cfg["pedestrian"]["max_wait"]
        for c in self.m.crossings:
            count, wait = self.sensors.waiting_at.get(c, (0, 0.0))
            if count == 0:
                self.episode.discard(c)
                continue
            if self.model is not None:
                ask = wait >= 10 and self.model.predict_proba([self.features(c, count, wait)])[0][1] > 0.5
            else:
                ask = wait > max_wait
            if ask:
                self.send("PED_SERVICE", self.tls, now, subject=c, wait=round(wait, 1), people=count)
                if c not in self.episode:
                    self.episode.add(c)
                    self.log.log(now, self.label, "request", "PED_SERVICE_REQUEST", tls=self.tls,
                                 crossing=c, people_waiting=count, longest_wait_s=wait,
                                 method="model" if self.model is not None else "rule")
        for c in self.m.crossings:
            if self.sensors.on_crossing.get(c):
                self.send("CLEARANCE_HOLD", self.tls, now, subject=c,
                          people=len(self.sensors.on_crossing[c]))
