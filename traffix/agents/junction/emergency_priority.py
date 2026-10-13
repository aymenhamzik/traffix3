"""
Emergency priority agent (one per junction). ASKS for green for ambulances.

Requests expire by themselves once the vehicle has passed.
Learned (models/ambulance_eta.joblib): predicts the ambulance's real arrival
time at the stop line from distance, speed and the queue on its lane.
"""
from ..base import Agent


class EmergencyPriorityAgent(Agent):
    name = "emergency_priority"
    model_file = "ambulance_eta.joblib"

    def __init__(self, ctx, tls, master):
        super().__init__(ctx, tls)
        self.announced = set()

    def eta(self, v):
        if self.model is not None:
            return float(self.model.predict([[v.distance, v.speed, v.lane_halting]])[0])
        return v.distance / max(v.speed, 1.0)

    def step(self, now):
        for v in self.sensors.approaching.get(self.tls, []):
            if v.kind != "emergency" or v.distance > self.cfg["emergency"]["detect_distance"]:
                continue
            eta = self.eta(v)
            req = self.send("EMERGENCY", self.tls, now, subject=v.id, link_index=v.link_index,
                            eta=round(eta, 1), distance=round(v.distance, 1))
            if v.id not in self.announced:
                self.announced.add(v.id)
                self.log.log(now, self.label, "request", "EMERGENCY_REQUEST", tls=self.tls,
                             vehicle=v.id, eta_s=eta, distance_m=v.distance,
                             link_index=v.link_index, request_id=req.id)
