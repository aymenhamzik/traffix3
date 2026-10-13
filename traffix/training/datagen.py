"""
Generates labelled training data by running simulations on TRAINING dates
(2025), separate from the 2026 test scenarios. One batch feeds every model.

Writes CSV files to data/training/:
  incident.csv        lane snapshots, label = lane blocked by the hidden incident
  sensor_health.csv   detector timing features, label = detector frozen by the hidden fault
  ambulance_eta.csv   approach snapshots, label = seconds until passing the junction
  bus_eta.csv         same for buses
  bus_lateness.csv    gap now -> gap at the next junction
  edge_travel_time.csv road readings now -> travel time one minute later
  pedestrian.csv      waiting groups, label = wait went over 60 s
  rain_speed.csv      rain intensity -> network speed factor
  arrivals.csv        upstream junction state -> vehicles entering an approach in the next 30 s
"""
import csv
import os
from collections import defaultdict

from ..core import config
from ..demand.generator import DemandGenerator
from ..evaluation.runner import run_one
from ..agents.network.incident_detection import lane_features
from ..agents.junction.observation import arrival_features

DATA = config.path("data", "training")
ROUTES = config.path("data", "generated", "training")

TRAINING_SCENARIOS = {
    "tr_morning": {"start": "2025-10-14 08:00", "duration": 1800},
    "tr_evening": {"start": "2025-11-18 17:00", "duration": 1800},
    "tr_incident_a": {"start": "2025-10-21 17:00", "duration": 1800,
                      "events": {"incident": {"edge": "B2_B3", "lane": 1, "at": 300, "duration": 900},
                                 "sensor_fault": {"tls": "F3", "at": 1300, "duration": 300}}},
    "tr_incident_b": {"start": "2025-09-16 08:00", "duration": 1800,
                      "events": {"incident": {"edge": "F1_F3", "lane": 2, "at": 400, "duration": 900}}},
    "tr_emergency": {"start": "2025-10-15 11:00", "duration": 1800, "events": {"ambulances": {"count": 6}}},
    "tr_rain": {"start": "2025-11-12 08:00", "duration": 1800,
                "events": {"rain": {"at": 300, "intensity": 0.4, "heavy_at": 1000, "heavy_intensity": 1.0}}},
    "tr_rain_incident": {"start": "2025-12-09 17:00", "duration": 1800,
                         "events": {"rain": {"at": 200, "intensity": 0.7},
                                    "incident": {"edge": "B4_B3", "lane": 1, "at": 500, "duration": 800}}},
    "tr_heavy": {"start": "2025-09-16 08:00", "duration": 1800, "demand_multiplier": 1.5},
    "tr_rush": {"start": "2025-10-14 07:15", "duration": 1800},
    "tr_ramadan": {"start": "2025-03-12 sunset-01:30", "duration": 1800,
                   "events": {"ambulances": {"count": 3}}},
}


class Recorder:
    def __init__(self, events):
        self.ev = events or {}
        self.rows = defaultdict(list)
        self.approach = {}               # (veh, tls) -> list of (t, dist, speed, halting)
        self.passed = {}
        self.bus_gap = {}                # (veh, tls) -> (t, gap, dist, speed, halting)
        self.bus_pass = defaultdict(list)
        self.edge_hist = defaultdict(list)
        self.peds = {}
        self.first_seen = defaultdict(dict)         # edge -> {vehicle: first time seen}
        self.arrival_snaps = []                     # (t, edge, features)

    def __call__(self, now, system):
        s = system.sensors
        approach_edges = {l.in_edge for m in system.ctx.models.values() for l in m.vehicle_links}
        for lane, r in s.readings.items():
            e = lane.rsplit("_", 1)[0]
            if e in approach_edges:
                for v in r.ids:
                    self.first_seen[e].setdefault(v, now)
        if int(now) % 10 == 0 and now >= 60:
            for e in approach_edges:
                recent = sum(1 for t in self.first_seen[e].values() if now - 30 < t <= now)
                self.arrival_snaps.append((now, e, arrival_features(system.ctx, e, recent)))
        inc = self.ev.get("incident")
        blocked = None
        if inc and inc["at"] + 20 <= now <= inc["at"] + inc["duration"]:
            blocked = f'{inc["edge"]}_{inc["lane"]}'
        fault = self.ev.get("sensor_fault")
        frozen = set()
        if fault and fault["at"] <= now <= fault["at"] + fault["duration"]:
            frozen = set(system.ctx.models[fault["tls"]].incoming_lanes)
        if int(now) % 5 == 0:
            for lane, r in s.readings.items():
                if r.halting and r.age(now) <= 2:
                    self.rows["incident"].append(lane_features(s, lane) + [int(lane == blocked)])
                self.rows["sensor_health"].append([r.age(now), now - r.last_change, int(lane in frozen)])
        current = set()
        for tls, vs in s.approaching.items():
            for v in vs:
                current.add((v.id, tls))
                self.approach.setdefault((v.id, tls), []).append((now, v.distance, v.speed, v.lane_halting, v.kind))
                if v.kind == "bus":
                    st = system.supermaster.transit.state.get(v.id) if system.supermaster else None
                    if st and st.get("gap_s") is not None and (v.id, tls) not in self.bus_gap:
                        self.bus_gap[(v.id, tls)] = (now, st["gap_s"], v.distance, v.speed, v.lane_halting, v.line)
        for key in list(self.approach):
            if key not in current and key not in self.passed:
                self.passed[key] = now
                if key[0].startswith("bus_"):
                    self.bus_pass[(key[1], key[0].rsplit("_", 1)[0])].append(now)
        if int(now) % 30 == 0:
            tt = s.edge_travel_times()
            for edge, t_edge in tt.items():
                lanes = [l for l in s.lanes if l.rsplit("_", 1)[0] == edge]
                if lanes:
                    rs = [s.lane(l) for l in lanes]
                    self.edge_hist[edge].append((now, [sum(r.occupancy for r in rs) / len(rs),
                                                       sum(r.halting for r in rs), min(r.speed for r in rs),
                                                       s.edge_length[edge], s.weather.get("rain", 0.0)], t_edge))
            speeds = [r.speed / 13.89 for r in s.readings.values() if r.vehicles > r.halting]
            if speeds:
                self.rows["rain_speed"].append([s.weather.get("rain", 0.0), sum(speeds) / len(speeds)])
        for c, (count, wait) in s.waiting_at.items():
            if count:
                ep = self.peds.setdefault(c, {"snaps": [], "max": 0})
                ep["max"] = max(ep["max"], wait)
                if 10 <= wait <= 40 and int(now) % 3 == 0:
                    m = next(x for x in system.masters if x.tls == s.crossing_tls[c])
                    ep["snaps"].append(m.pedestrian_agent.features(c, count, wait))
            elif c in self.peds:
                ep = self.peds.pop(c)
                label = int(ep["max"] > 60)
                self.rows["pedestrian"] += [f + [label] for f in ep["snaps"]]

    def finish(self):
        for (vid, tls), snaps in self.approach.items():
            if (vid, tls) in self.passed:
                name = "ambulance_eta" if snaps[0][4] == "emergency" else "bus_eta"
                for t, d, sp, h, _ in snaps[::2]:
                    self.rows[name].append([d, sp, h, self.passed[(vid, tls)] - t])
        for (vid, tls), (t, gap, d, sp, h, line) in self.bus_gap.items():
            later = [x for x in self.bus_pass.get((tls, f"bus_{line}"), []) if x > t]
            if (vid, tls) in self.passed:
                prev = [x for x in self.bus_pass.get((tls, f"bus_{line}"), []) if x < self.passed[(vid, tls)]]
                if prev:
                    self.rows["bus_lateness"].append([gap, d, sp, h, self.passed[(vid, tls)] - prev[-1]])
        last = max((t for seen in self.first_seen.values() for t in seen.values()), default=0)
        for t, e, f in self.arrival_snaps:
            if t + 30 <= last:
                n = sum(1 for ft in self.first_seen[e].values() if t < ft <= t + 30)
                self.rows["arrivals"].append(f + [n])
        for edge, hist in self.edge_hist.items():
            for (t0, f, _), (t1, _, tt1) in zip(hist, hist[2:]):
                self.rows["edge_travel_time"].append(f + [min(tt1, 600)])
        return self.rows


HEADERS = {
    "incident": ["isolated_stops", "halting", "vehicles", "speed", "neighbour_speed", "occupancy", "rain", "label"],
    "sensor_health": ["age", "since_change", "label"],
    "ambulance_eta": ["distance", "speed", "lane_halting", "seconds_to_pass"],
    "bus_eta": ["distance", "speed", "lane_halting", "seconds_to_pass"],
    "bus_lateness": ["gap_now", "distance", "speed", "lane_halting", "gap_at_junction"],
    "edge_travel_time": ["occupancy", "halting", "min_speed", "length", "rain", "travel_time_later"],
    "pedestrian": ["people", "wait", "time_in_green", "vehicle_queue", "label"],
    "rain_speed": ["rain", "speed_factor"],
    "arrivals": ["upstream_is_signal", "upstream_releasing", "upstream_queue", "upstream_moving",
                 "entries_last_30s", "forecast_level", "road_length", "entries_next_30s"],
}


def generate(seeds=(1, 2)):
    os.makedirs(DATA, exist_ok=True)
    gen = DemandGenerator(config.network_files()[0])
    all_rows = defaultdict(list)
    for name, scen in TRAINING_SCENARIOS.items():
        for seed in seeds:
            _, meta = gen.build(name, scen, seed, ROUTES)
            rec = Recorder(meta["events"])
            run_one("traffix_rules", name, seed, route_dir=ROUTES, hooks=[rec], save_log=False)
            rows = rec.finish()
            for k, v in rows.items():
                all_rows[k] += v
            print(f"  {name} seed {seed}: " + ", ".join(f"{k} {len(v)}" for k, v in rows.items()), flush=True)
    for k, header in HEADERS.items():
        with open(os.path.join(DATA, f"{k}.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(all_rows.get(k, []))
    return {k: len(v) for k, v in all_rows.items()}
