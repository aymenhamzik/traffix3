"""
Evaluation monitor: measures what each persona cares about, identically for
every controller (fixed, actuated, TraffiX). Read-only; not part of control.

  Ferjani  pedestrian mean/P95/max wait, clearance truncations
  Faycel   completed vs unfinished trips, P95/max duration, stops
  Mamadou  bus headway variation, share of long gaps
  Touhami  ambulance travel time and delay, delay to other traffic
"""
import statistics
import xml.etree.ElementTree as ET
from collections import defaultdict

from ..core import config
from ..simulation.backend import traci
from ..simulation.world import STALL_ID

LATE_FACTOR = config.agents()["transit"]["late_factor"]
HEADWAY = config.simulation()["demand"]["bus_headway"]


def p95(xs):
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, int(0.95 * len(s)))]


class Monitor:
    def __init__(self, models):
        self.models = models
        self.prev_state = {}
        self.ped_wait = defaultdict(float)
        self.ped_type = {}
        self.truncations = 0
        self.truncations_slow = 0
        self.buses = {}                    # bus id -> checkpoint edge
        self.bus_line = {}
        self.bus_passes = defaultdict(list)

    def step(self, now):
        for p in traci.person.getIDList():
            if p not in self.ped_type:
                self.ped_type[p] = traci.person.getTypeID(p)
            if traci.person.getSpeed(p) < 0.1:
                self.ped_wait[p] += 1

        # a conflicting vehicle green starting while someone is on the crossing
        for tls, m in self.models.items():
            state = traci.trafficlight.getRedYellowGreenState(tls)
            prev = self.prev_state.get(tls)
            if prev and prev != state:
                newly = {i for i, (a, b) in enumerate(zip(prev, state))
                         if b in "Gg" and a not in "Gg" and m.links[i] and not m.links[i].is_crossing}
                for crossing, conf in m.conflicts.items():
                    if newly & set(conf):
                        for person in traci.edge.getLastStepPersonIDs(crossing):
                            self.truncations += 1
                            if self.ped_type.get(person) == "ped_slow":
                                self.truncations_slow += 1
            self.prev_state[tls] = state

        for v in traci.simulation.getDepartedIDList():
            if v.startswith("bus_"):
                route = traci.vehicle.getRoute(v)
                self.buses[v] = route[len(route) // 2]
                self.bus_line[v] = traci.vehicle.getLine(v)
        for v in list(self.buses):
            if traci.vehicle.getRoadID(v) == self.buses[v]:
                self.bus_passes[self.bus_line[v]].append(now)
                del self.buses[v]
        for v in traci.simulation.getArrivedIDList():
            self.buses.pop(v, None)

    def results(self, tripinfo_file, expected_vehicles):
        root = ET.parse(tripinfo_file).getroot()
        cars, buses, ambulances = [], [], []
        for t in root.findall("tripinfo"):
            if t.get("id") == STALL_ID:
                continue
            vt = t.get("vType")
            (buses if vt == "bus" else ambulances if vt in ("ambulance", "police", "fire_truck") else cars).append(t)
        arrived_peds = [p.get("id") for p in root.findall("personinfo")]

        def col(rows, attr):
            return [float(r.get(attr)) for r in rows]

        dur, wait = col(cars, "duration"), col(cars, "waitingTime")
        co2 = sum(float(t.find("emissions").get("CO2_abs")) for t in cars) / 1000.0  # g
        ped_w = [self.ped_wait[p] for p in arrived_peds]
        gaps = [b - a for times in self.bus_passes.values()
                for a, b in zip(sorted(times), sorted(times)[1:])]
        completed = len(cars) + len(buses) + len(ambulances)
        mean = statistics.mean
        return {
            # Faycel
            "veh_completed": len(cars),
            "veh_unfinished": max(0, expected_vehicles - completed),
            "veh_mean_travel_s": mean(dur) if dur else 0,
            "veh_p95_travel_s": p95(dur),
            "veh_max_travel_s": max(dur) if dur else 0,
            "veh_mean_wait_s": mean(wait) if wait else 0,
            "veh_p95_wait_s": p95(wait),
            "veh_mean_stops": mean(col(cars, "waitingCount")) if cars else 0,
            "veh_mean_time_loss_s": mean(col(cars, "timeLoss")) if cars else 0,
            "co2_g_per_trip": co2 / max(1, len(cars)),
            # Ferjani
            "ped_completed": len(arrived_peds),
            "ped_mean_wait_s": mean(ped_w) if ped_w else 0,
            "ped_p95_wait_s": p95(ped_w),
            "ped_max_wait_s": max(ped_w) if ped_w else 0,
            "clearance_truncations": self.truncations,
            "clearance_truncations_slow": self.truncations_slow,
            # Mamadou
            "bus_mean_travel_s": mean(col(buses, "duration")) if buses else 0,
            "bus_headway_cv": (statistics.pstdev(gaps) / mean(gaps)) if len(gaps) > 1 else 0,
            "bus_long_gap_share": (sum(g > LATE_FACTOR * HEADWAY
                                       for g in gaps) / len(gaps)) if gaps else 0,
            # Touhami
            "ambulance_n": len(ambulances),
            "ambulance_mean_travel_s": mean(col(ambulances, "duration")) if ambulances else None,
            "ambulance_mean_wait_s": mean(col(ambulances, "waitingTime")) if ambulances else None,
            "ambulance_mean_time_loss_s": mean(col(ambulances, "timeLoss")) if ambulances else None,
        }
