"""
Corridor coordination agent (network). Makes neighbouring junctions cooperate.

When a master releases a platoon towards a neighbour, this agent tells the
neighbour (CORRIDOR_BIAS directive) so its traffic light agent can favour that
approach while the platoon arrives: a green wave built from live traffic.
Learned: the platoon weight is tuned by training/tune_traffic_light.py.
It also follows the demand forecast's dominant direction (inbound in the
morning, outbound in the evening) and logs when it changes.
"""
import json
import os

from ...core import config
from ..base import Agent


class CorridorAgent(Agent):
    name = "corridor"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.p = dict(self.cfg["corridor"])
        tuned = config.path(self.cfg["models_dir"], "traffic_light_params.json")
        if ctx.use_models and os.path.exists(tuned):
            self.p["platoon_weight"] = json.load(open(tuned)).get("platoon_weight",
                                                                   self.p["platoon_weight"])
        self.direction = None

    def step(self, now):
        share = self.bus.forecast.get("inbound_share", 0.5)
        direction = "inbound" if share > 0.55 else "outbound" if share < 0.45 else "balanced"
        if direction != self.direction:
            self.direction = direction
            self.log.log(now, self.label, "directive", "CORRIDOR_DIRECTION", direction=direction,
                         forecast_inbound_share=share)
        for tls, st in self.bus.status.items():
            for edge in st.get("released_edges", []):
                down = self.sensors.edge_to_node.get(edge)
                if down not in self.ctx.models or down == tls:
                    continue
                lanes = [l for l in self.sensors.lanes if l.rsplit("_", 1)[0] == edge]
                moving = sum(max(0, self.sensors.lane(l).vehicles - self.sensors.lane(l).halting)
                             for l in lanes)
                if moving:
                    self.send("CORRIDOR_BIAS", down, now, ttl=self.p["horizon"], subject=edge,
                              weight=round(self.p["platoon_weight"] * moving, 2), from_junction=tls)
