"""
Rerouting agent (network). ADVISES a Route B; never reroutes anyone itself.

Reacts to incidents, flood alerts and congestion. Learned (models/edge_travel_time.joblib):
predicts how long each road will take from its current readings, instead of
SUMO's instantaneous estimate. Advisories feed the driver page.
"""
import heapq

from ..base import Agent


def shortest(graph, start, goal, tt, avoid=()):
    """Fastest path (list of edges) and its time, using travel times tt. Pure function:
    also used by the trip planner on the driver page."""
    avoid = set(avoid)
    dist, heap = {start: tt.get(start, 0.0)}, [(tt.get(start, 0.0), start, [start])]
    while heap:
        d, e, path = heapq.heappop(heap)
        if e == goal:
            return d, path
        if d > dist.get(e, float("inf")):
            continue
        for nxt in graph.get(e, []):
            if nxt in avoid:
                continue
            nd = d + tt.get(nxt, 1e6)
            if nd < dist.get(nxt, float("inf")):
                dist[nxt] = nd
                heapq.heappush(heap, (nd, nxt, path + [nxt]))
    return None, None


class ReroutingAgent(Agent):
    name = "rerouting"
    model_file = "edge_travel_time.joblib"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.advised = set()

    def travel_times(self):
        tt = self.sensors.edge_travel_times()
        if self.model is not None:
            rain = self.sensors.weather.get("rain", 0.0)
            for edge in tt:
                lanes = [l for l in self.sensors.lanes if l.rsplit("_", 1)[0] == edge]
                if lanes:
                    rs = [self.sensors.lane(l) for l in lanes]
                    f = [sum(r.occupancy for r in rs) / len(rs), sum(r.halting for r in rs),
                         min(r.speed for r in rs), self.sensors.edge_length[edge], rain]
                    tt[edge] = max(1.0, float(self.model.predict([f])[0]))
        for p in self.bus.published("FLOOD"):
            tt[p.subject] = 1e6
        return tt

    def step(self, now):
        blocked = [(p.subject, p) for p in self.bus.published("INCIDENT")
                   if p.details["confidence"] >= self.cfg["incident"]["min_confidence"]]
        blocked += [(p.subject, p) for p in self.bus.published("FLOOD")]
        blocked += [(p.subject, p) for p in self.bus.published("CONGESTION")]
        for edge, pub in blocked:
            key = (edge, pub.t)
            if key in self.advised:
                continue
            vehicles = self.sensors.vehicles_planning(edge, limit=20)
            if not vehicles:
                continue
            self.advised.add(key)
            tt = self.travel_times()
            tt_now = dict(tt)
            tt_now[edge] = self.sensors.edge_travel_times().get(edge, tt.get(edge, 0)) \
                if pub.kind != "FLOOD" else 1e6
            savings, example = [], None
            for _v, rest in vehicles:
                cur = sum(tt_now.get(e, 0) for e in rest[1:])
                alt, path = self._shortest(rest[0], rest[-1], edge, tt)
                if path:
                    savings.append(min(cur - alt, 3600))
                    example = example or path
            avg = sum(savings) / len(savings) if savings else 0.0
            if savings and avg >= self.cfg["rerouting"]["min_saving"]:
                self.bus.publish(pub.__class__(self.label, "ROUTE_B", "driver", now, now + 900, edge,
                                               details={"route_b": example, "saving_s": round(avg)}))
                self.log.log(now, self.label, "advisory", "REROUTE_ADVISORY", edge=edge,
                             vehicles_affected=len(vehicles), projected_saving_s=avg,
                             route_b=" > ".join(example), applied=False)
            else:
                self.log.log(now, self.label, "advisory", "REROUTE_NOT_WORTH", edge=edge,
                             vehicles_affected=len(vehicles), projected_saving_s=avg)

    def _shortest(self, start, goal, avoid, tt):
        d, path = shortest(self.sensors.graph, start, goal, tt, {avoid})
        return (d - tt.get(start, 0.0), path) if path else (None, None)
