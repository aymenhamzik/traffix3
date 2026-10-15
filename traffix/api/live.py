"""
Live mode: runs ONE simulation in a background thread, paced for watching,
and keeps a snapshot of everything the persona pages need.
"""
import json
import os
import threading
import time
from datetime import datetime

import sumo
import sumolib

from ..core import config
from ..core.decision_log import DecisionLog
from ..core.narrate import Narrator
from ..synapse.alert_writer import AlertWriter
from ..synapse.copilot import Copilot
from ..agents.network.rerouting import shortest
from ..demand.generator import BUS_LINES, DemandGenerator, classify_edges
from ..orchestration.system import TraffixSystem
from ..simulation.backend import traci
from ..simulation.network_model import load_models
from ..simulation.world import World

SUMO_HOME = os.environ.get("SUMO_HOME", sumo.SUMO_HOME)


def _point_back(shape, dist, side):
    """Point `dist` metres before the end of a polyline, shifted `side` metres to the right."""
    import math
    (x1, y1), (x2, y2) = shape[-2], shape[-1]
    L = math.hypot(x2 - x1, y2 - y1) or 1.0
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    d = min(dist, L * 0.8)
    return x2 - ux * d + uy * side, y2 - uy * d - ux * side


def network_geometry(net_file):
    import xml.etree.ElementTree as ET
    from sumolib.geomhelper import positionAtShapeOffset
    net = sumolib.net.readNet(net_file)
    nodes = [{"id": n.getID(), "x": n.getCoord()[0], "y": n.getCoord()[1],
              "signal": n.getType() == "traffic_light"} for n in net.getNodes()]
    edges, signals, crossings = [], [], []
    for e in net.getEdges():
        if e.getFunction() == "crossing":
            tls = e.getID().lstrip(":").split("_c")[0]
            crossings.append({"id": e.getID(), "tls": tls, "shape": [list(p) for p in e.getLanes()[0].getShape()]})
            continue
        if e.getFunction() or not e.allows("passenger") and not e.allows("bus"):
            continue
        lanes = [l for l in e.getLanes() if l.allows("passenger") or l.allows("bus")]
        bus_only = any(l.allows("bus") and not l.allows("passenger") for l in lanes)
        edges.append({"id": e.getID(), "from": e.getFromNode().getID(), "to": e.getToNode().getID(),
                      "name": e.getName(), "lanes": len(lanes), "bus_lane": bus_only,
                      "shape": [list(p) for p in e.getShape()],
                      "lane_shapes": [[list(p) for p in l.getShape()] for l in lanes],
                      "sidewalks": [[list(p) for p in l.getShape()] for l in e.getLanes()
                                    if l.allows("pedestrian") and not l.allows("passenger") and not l.allows("bus")]})
        if e.getToNode().getType() == "traffic_light":
            x, y = _point_back(e.getShape(), 42, 2 + 3.2 * len(lanes))
            signals.append({"tls": e.getToNode().getID(), "edge": e.getID(), "x": x, "y": y})
    stops = []
    stops_file = net_file.replace(".net.xml", ".stops.xml")
    if os.path.exists(stops_file):
        for b in ET.parse(stops_file).getroot().findall("busStop"):
            lane = net.getLane(b.get("lane"))
            x, y = positionAtShapeOffset(lane.getShape(), (float(b.get("startPos")) + float(b.get("endPos"))) / 2)
            p = b.find("param")
            stops.append({"id": b.get("id"), "name": b.get("name"), "x": x, "y": y,
                          "lines": b.get("lines").split(), "junction": p.get("value") if p is not None else ""})
    xs = [n["x"] for n in nodes]
    ys = [n["y"] for n in nodes]
    return {"nodes": nodes, "edges": edges, "signals": signals, "crossings": crossings, "bus_stops": stops,
            "bounds": [min(xs), min(ys), max(xs), max(ys)]}


class LiveRun:
    def __init__(self, scenario, seed=1, speed=4.0, controller="traffix", gui=False):
        self.scenario, self.seed, self.speed, self.controller = scenario, seed, speed, controller
        self.gui = gui          # also show THIS run in SUMO's own window
        self.lock = threading.Lock()
        self.snapshot = {"status": "starting"}
        self.log = DecisionLog()
        self.running = False
        net = config.network_files()[0]
        self.geometry = network_geometry(net)
        self.geometry_links = None
        self._static(net)
        gen = DemandGenerator(net)
        self.routes, self.meta = gen.build(scenario, config.scenarios()[scenario], seed,
                                           config.path("data", "generated", "live"))

    def _static(self, net_file):
        """Trip planner data that never changes: road graph, free-flow times, places, bus lines."""
        net = sumolib.net.readNet(net_file)
        self.graph = {e.getID(): [o.getID() for o in e.getOutgoing()]
                      for e in net.getEdges() if not e.getFunction()}
        self.free_tt = {e.getID(): e.getLength() / max(e.getSpeed(), 0.1)
                        for e in net.getEdges() if not e.getFunction()}
        self.edge_name = {e.getID(): e.getName() or e.getID() for e in net.getEdges() if not e.getFunction()}
        self.edge_to = {e.getID(): e.getToNode().getID() for e in net.getEdges() if not e.getFunction()}
        names = {}
        for n in net.getNodes():
            nm = n.getParam("name") if hasattr(n, "getParam") else None
            names[n.getID()] = nm or n.getID()
        entries, exits, _ = classify_edges(net)
        self.places = {"from": [{"edge": e.getID(), "name": names[e.getFromNode().getID()]} for e in entries],
                       "to": [{"edge": e.getID(), "name": names[e.getToNode().getID()]} for e in exits]}
        self.lines, self.line_edges = {}, {}
        for line, first, last in BUS_LINES:
            if net.hasEdge(first) and net.hasEdge(last):
                path, _ = net.getShortestPath(net.getEdge(first), net.getEdge(last), vClass="bus")
                if path:
                    self.lines[line] = [e.getToNode().getID() for e in path
                                        if e.getToNode().getType() == "traffic_light"]
                    self.line_edges[line] = [e.getID() for e in path]
        self.geometry["lines"] = self.line_edges

    def plan_trip(self, from_edge, to_edge):
        """Fastest route now, its delay vs normal, the alerts on it, and an alternative.
        Uses only the latest snapshot: never touches SUMO from the web thread."""
        snap = self.state()
        tt = {**self.free_tt, **snap.get("edge_tt", {})}
        problems = {}
        for kind in ("incidents", "floods", "congestion"):
            for p in snap.get(kind, []):
                problems.setdefault(p["subject"], []).append(kind[:-1] if kind != "congestion" else "congestion")
        for p in snap.get("floods", []):
            tt[p["subject"]] = 1e6
        t_now, route = shortest(self.graph, from_edge, to_edge, tt)
        if not route:
            return {"error": "no route between these places"}
        t_free = sum(self.free_tt.get(e, 0) for e in route)
        junctions = [self.edge_to[e] for e in route[:-1]]
        alerts = []
        for e in route:
            for kind in problems.get(e, []):
                alerts.append({"kind": kind, "edge": e, "street": self.edge_name[e]})
        for amb in snap.get("ambulances", []):
            hits = [j for j, eta in amb["junctions"] if j in junctions]
            if hits:
                alerts.append({"kind": "ambulance", "vehicle": amb["subject"], "junction": hits[0]})
        if snap.get("weather", {}).get("rain"):
            alerts.append({"kind": "rain", "intensity": snap["weather"]["rain"]})
        alt = None
        avoid = [e for e in route if e in problems and e not in (from_edge, to_edge)]
        if avoid:
            t_alt, alt_route = shortest(self.graph, from_edge, to_edge, tt, avoid)
            if alt_route and alt_route != route:
                alt = {"edges": alt_route, "time_s": round(t_alt), "saving_s": round(t_now - t_alt),
                       "streets": self._streets(alt_route)}
        return {"edges": route, "streets": self._streets(route), "time_s": round(t_now),
                "normal_s": round(t_free), "delay_s": round(t_now - t_free), "junctions": junctions,
                "alerts": alerts, "alternative": alt, "clock": snap.get("clock")}

    def _streets(self, route):
        out = []
        for e in route:
            n = self.edge_name[e]
            if not out or out[-1] != n:
                out.append(n)
        return out

    def start(self):
        self.copilot = Copilot(self)
        self.alert_writer = AlertWriter(self)
        self.alert_writer.start()
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.running = False
        if hasattr(self, "alert_writer"):
            self.alert_writer.stop()

    def _run(self):
        net = config.network_files()[0]
        stops = net.replace(".net.xml", ".stops.xml")
        binary = os.path.join(SUMO_HOME, "bin", "sumo-gui" if self.gui else "sumo")
        gui_opts = ["--start", "--quit-on-end", "--delay", "0"] if self.gui else []
        traci.start([binary, "-n", net, "-r", self.routes] + gui_opts
                    + (["-a", stops] if os.path.exists(stops) else []) + [
                     "--time-to-teleport", "300", "--ignore-route-errors", "true",
                     "--no-step-log", "true", "--no-warnings", "true", "--seed", str(self.seed)])
        models = load_models(net)
        start = datetime.strptime(self.meta["start"], "%Y-%m-%d %H:%M")
        self.narrator = Narrator({t: m.name for t, m in models.items()}, self.edge_name, start)
        self.system = TraffixSystem(self.controller, models, net, self.log, start)
        self.system.start(0)
        world = World(self.meta["events"], models, self.system.sensors)
        end = self.meta["duration"]
        try:
            while self.running and traci.simulation.getTime() < end:
                t0 = time.time()
                traci.simulationStep()
                now = traci.simulation.getTime()
                world.step(now)
                self.system.step(now)
                if int(now) % 5 == 0 or not hasattr(self, "_tt"):
                    sm = self.system.supermaster
                    self._tt = sm.rerouting.travel_times() if sm else self.system.sensors.edge_travel_times()
                snap = self._snapshot(now, models)
                with self.lock:
                    self.snapshot = snap
                time.sleep(max(0.0, 1.0 / self.speed - (time.time() - t0)))
        finally:
            traci.close()
            with self.lock:
                self.snapshot["status"] = "finished"

    def _snapshot(self, now, models):
        s, bus = self.system.sensors, self.system.bus
        kinds = {"car": "car", "moto": "moto", "bus": "bus", "ambulance": "ambulance",
                 "police": "police", "fire_truck": "fire"}
        vehicles = []
        for v in traci.vehicle.getIDList():
            x, y = traci.vehicle.getPosition(v)
            vt = traci.vehicle.getTypeID(v)
            vehicles.append({"id": v, "x": round(x, 1), "y": round(y, 1), "kind": kinds.get(vt, "car"),
                             "angle": round(traci.vehicle.getAngle(v)),
                             "line": traci.vehicle.getLine(v) if vt == "bus" else "",
                             "speed": round(traci.vehicle.getSpeed(v), 1)})
        people = []
        for p in traci.person.getIDList()[:800]:
            x, y = traci.person.getPosition(p)
            people.append([round(x, 1), round(y, 1), 1 if traci.person.getTypeID(p) == "ped_slow" else 0])
        signals = {}
        for tls, m in models.items():
            state = traci.trafficlight.getRedYellowGreenState(tls)
            per_edge = {}
            for l in m.vehicle_links:
                c = state[l.index]
                cur = per_edge.get(l.in_edge, "r")
                per_edge[l.in_edge] = "G" if c in "Gg" or cur == "G" else "y" if c in "yY" or cur == "y" else "r"
            signals[tls] = per_edge
        junctions = []
        for tls, st in bus.status.items():
            m = models[tls]
            junctions.append({
                "id": tls, "name": m.name, "mode": st["mode"], "queue": st["queue_total"],
                "preempt": st["preempt"],
                "crossings": [{"id": c, "walk": m.crossing_green(st["green"], c),
                               "waiting": s.waiting_at.get(c, (0, 0))[0],
                               "longest_wait": round(s.waiting_at.get(c, (0, 0))[1]),
                               "on_crossing": len(s.on_crossing.get(c, []))} for c in m.crossings]})
        pubs = lambda k: [{"subject": p.subject, "t": p.t, **p.details} for p in bus.published(k)]
        return {
            "status": "running", "scenario": self.scenario, "controller": self.controller, "t": now,
            "clock": self.system.ctx.clock(now).strftime("%Y-%m-%d %H:%M:%S"),
            "duration": self.meta["duration"], "junctions": junctions, "vehicles": vehicles, "people": people,
            "signals": signals,
            "incidents": pubs("INCIDENT"), "floods": pubs("FLOOD"), "route_b": pubs("ROUTE_B"),
            "congestion": pubs("CONGESTION"), "ambulances": pubs("AMBULANCE_ROUTE"),
            "edge_tt": {e: round(min(v, 1e5), 1) for e, v in self._tt.items()},
            "lines": self.lines,
            "stale": pubs("DATA_STALE"), "weather": s.weather, "forecast": bus.forecast,
            "buses": self.system.supermaster.transit.state if self.system.supermaster else {},
            "notifications": bus.notifications[-150:],
            "decisions": self.narrator.enrich(self.log.entries[-60:]),
            "emergency_decisions": self.narrator.enrich([e for e in self.log.entries[-3000:]
                                                         if e["reason"].startswith(("EMERGENCY", "RECOVER"))][-40:]),
            "transit_decisions": self.narrator.enrich([e for e in self.log.entries[-3000:]
                                                       if e["reason"].startswith(("TRANSIT", "BUS_"))][-150:]),
            "counts": {"vehicles": len(vehicles), "pedestrians": traci.person.getIDCount(),
                       "decisions": len(self.log.entries)}}

    def state(self):
        with self.lock:
            return dict(self.snapshot)
