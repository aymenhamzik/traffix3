"""
Static description of each signalized junction, read from the network file.
Pure data, no simulation access: safe for every agent to use.

For each junction we know:
  links[i]          what signal index i controls (incoming lane -> outgoing lane)
  vehicle_links     indices that control vehicles
  crossings         crossing edge -> {indices, crossed edges, length}
  green_phases      the distinct green states of the junction's signal plan
  conflicts[c]      vehicle indices whose green conflicts with crossing c
"""
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass
class Link:
    index: int
    in_lane: str
    out_lane: str
    in_edge: str
    out_edge: str
    is_crossing: bool


@dataclass
class TLSModel:
    id: str
    name: str
    links: list
    green_phases: list               # state strings
    crossings: dict = field(default_factory=dict)
    conflicts: dict = field(default_factory=dict)

    @property
    def vehicle_links(self):
        return [l for l in self.links if l and not l.is_crossing]

    @property
    def incoming_lanes(self):
        return sorted({l.in_lane for l in self.vehicle_links})

    @property
    def outgoing_lanes(self):
        return sorted({l.out_lane for l in self.vehicle_links})

    def phases_serving(self, index):
        """Green phases in which signal `index` is green, protected ('G') first."""
        g = [p for p in self.green_phases if p[index] == "G"]
        return g + [p for p in self.green_phases if p[index] == "g"]

    def crossing_green(self, state, crossing):
        return any(state[i] in "Gg" for i in self.crossings[crossing]["indices"])


def _vehicle_green_key(state, links):
    return tuple(i for i, s in enumerate(state)
                 if s in "Gg" and links[i] and not links[i].is_crossing)


def load_models(net_file):
    root = ET.parse(net_file).getroot()
    crossing_info = {}
    for e in root.findall("edge"):
        if e.get("function") == "crossing":
            lane = e.find("lane")
            crossing_info[e.get("id")] = {
                "crossed": set(e.get("crossingEdges", "").split()),
                "length": float(lane.get("length")), "indices": []}

    names = {}
    for j in root.findall("junction"):
        for p in j.findall("param"):
            if p.get("key") == "name":
                names[j.get("id")] = p.get("value")

    links_by_tls = {}
    for c in root.findall("connection"):
        tl = c.get("tl")
        if tl is None:
            continue
        idx = int(c.get("linkIndex"))
        frm, to = c.get("from"), c.get("to")
        is_cross = to in crossing_info
        link = Link(idx, f"{frm}_{c.get('fromLane')}", f"{to}_{c.get('toLane')}",
                    frm, to, is_cross)
        links_by_tls.setdefault(tl, {})[idx] = link

    models = {}
    for tl in root.findall("tlLogic"):
        tid = tl.get("id")
        states = [p.get("state") for p in tl.findall("phase")]
        n = len(states[0])
        links = [links_by_tls.get(tid, {}).get(i) for i in range(n)]

        # Distinct green phases: no yellow, at least one vehicle green.
        # If two phases give the same vehicle greens (netconvert adds a short
        # "crossing red" phase), keep the one where pedestrians also walk.
        best = {}
        for s in states:
            if "y" in s:
                continue
            key = _vehicle_green_key(s, links)
            ped_green = sum(1 for i, ch in enumerate(s)
                            if ch in "Gg" and links[i] and links[i].is_crossing)
            if not key and not ped_green:
                continue
            if key not in best or ped_green > best[key][0]:
                best[key] = (ped_green, s)
        greens = [s for _, s in best.values()]

        crossings, conflicts = {}, {}
        for l in links:
            if l and l.is_crossing:
                cid = l.out_edge
                info = crossings.setdefault(cid, {
                    "indices": [], "crossed": crossing_info[cid]["crossed"],
                    "length": crossing_info[cid]["length"]})
                info["indices"].append(l.index)
        for cid, info in crossings.items():
            conflicts[cid] = [l.index for l in links if l and not l.is_crossing
                              and (l.in_edge in info["crossed"] or l.out_edge in info["crossed"])]
        models[tid] = TLSModel(tid, names.get(tid, tid), links, greens, crossings, conflicts)
    return models
