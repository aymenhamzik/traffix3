"""
Sensor health agent (one per junction). PUBLISHES whether its detectors are fresh.

Rule: a reading older than stale_after seconds is stale.
Learned (models/sensor_health.joblib): a classifier trained on detector timing
(time since last update, time since the values changed) with labels from
injected detector faults.
Stale stays stale until the detector really updates again.
"""
from ...core.messages import Message
from ..base import Agent


class SensorHealthAgent(Agent):
    name = "sensor_health"
    model_file = "sensor_health.joblib"

    def __init__(self, ctx, tls, master):
        super().__init__(ctx, tls)
        m = ctx.models[tls]
        self.lanes = sorted(set(m.incoming_lanes + m.outgoing_lanes))

    def stale(self, r, now):
        age = r.age(now)
        if self.model is not None and age > 2:
            return self.model.predict([[age, now - r.last_change]])[0] == 1
        return age > self.cfg["safety"]["stale_after"]

    def step(self, now):
        for lane in self.lanes:
            r = self.sensors.readings.get(lane)
            if r is None:
                continue
            published = self.bus.is_published("DATA_STALE", lane)
            if self.stale(r, now) and not published:
                self.bus.publish(Message(self.label, "DATA_STALE", "all", now, now + 1e9, lane,
                                         details={"age": r.age(now)}))
                self.log.log(now, self.label, "publish", "DATA_STALE", tls=self.tls, lane=lane,
                             last_update_s_ago=r.age(now))
            elif published and r.age(now) <= 1:
                self.bus.unpublish("DATA_STALE", lane)
                self.log.log(now, self.label, "publish", "DATA_FRESH", tls=self.tls, lane=lane)
