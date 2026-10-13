"""
Builds a schematic model of central Tunis.

  Avenue Habib Bourguiba (main corridor, west -> east):
    Bab Bhar -- [B1 Rue de Rome] -- [B2 Theatre crossing] -- [B3 Av. de Paris /
    Av. de Carthage] -- [B4 Place du 14 Janvier, Av. Mohamed V] -- Tunis Marine
  Avenue Farhat Hached (parallel, south) with junctions F1, F3, F4.

IMPORTANT: this is a schematic built from the main axes of the city centre.
Distances and lane counts are approximate and some side streets are left out.
For the exact street geometry, run scripts/import_osm.py on your own machine
(it downloads OpenStreetMap data); every other script works on either network.

Usage:  python scripts/build_network.py
"""
import os
import subprocess

import sys

import sumo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from traffix.core import config  # noqa: E402
import traffix.demand.generator  # noqa: E402,F401

NET_DIR = config.path("data", "networks")
YELLOW = config.agents()["safety"]["yellow"]

BIN = os.path.join(os.environ.get("SUMO_HOME", sumo.SUMO_HOME), "bin")

# id: (x, y, type, name)   x = metres east, y = metres north
NODES = {
    "B1": (0, 0, "traffic_light", "Rue de Rome x Av. de France / Bourguiba"),
    "B2": (300, 0, "traffic_light", "Theatre municipal pedestrian crossing"),
    "B3": (550, 0, "traffic_light", "Av. de Paris / Av. de Carthage x Bourguiba"),
    "B4": (950, 0, "traffic_light", "Place du 14 Janvier 2011 (Av. Mohamed V)"),
    "F1": (0, -400, "traffic_light", "Rue de Rome x Av. Farhat Hached"),
    "F3": (550, -400, "traffic_light", "Av. de Carthage x Av. Farhat Hached"),
    "F4": (950, -400, "traffic_light", "Av. Mohamed V (south) x Av. Farhat Hached"),
    # entry / exit points at the edge of the model
    "bab_bhar": (-300, 0, "priority", "Bab Bhar"),
    "tunis_marine": (1350, 0, "priority", "Tunis Marine"),
    "rome_n": (0, 300, "priority", "Rue de Rome (north)"),
    "paris_n": (550, 300, "priority", "Av. de Paris (north)"),
    "mv_n": (950, 300, "priority", "Av. Mohamed V (north)"),
    "fh_w": (-300, -400, "priority", "Av. Farhat Hached (west)"),
    "fh_e": (1350, -400, "priority", "Av. Farhat Hached (east)"),
    "rome_s": (0, -700, "priority", "Rue de Rome (south)"),
    "carthage_s": (550, -700, "priority", "Av. de Carthage (south)"),
    "mv_s": (950, -700, "priority", "Av. Mohamed V (south)"),
}

# (from, to, lanes, street name). Each road is built in both directions.
ROADS = [
    ("bab_bhar", "B1", 2, "Avenue de France"),
    ("B1", "B2", 2, "Avenue Habib Bourguiba"),
    ("B2", "B3", 2, "Avenue Habib Bourguiba"),
    ("B3", "B4", 2, "Avenue Habib Bourguiba"),
    ("B4", "tunis_marine", 2, "Avenue Habib Bourguiba"),
    ("fh_w", "F1", 2, "Avenue Farhat Hached"),
    ("F1", "F3", 2, "Avenue Farhat Hached"),
    ("F3", "F4", 2, "Avenue Farhat Hached"),
    ("F4", "fh_e", 2, "Avenue Farhat Hached"),
    ("rome_n", "B1", 1, "Rue de Rome"),
    ("B1", "F1", 1, "Rue de Rome"),
    ("F1", "rome_s", 1, "Rue de Rome"),
    ("paris_n", "B3", 2, "Avenue de Paris"),
    ("B3", "F3", 2, "Avenue de Carthage"),
    ("F3", "carthage_s", 2, "Avenue de Carthage"),
    ("mv_n", "B4", 3, "Avenue Mohamed V"),
    ("B4", "F4", 2, "Avenue Mohamed V"),
    ("F4", "mv_s", 2, "Avenue Mohamed V"),
]
SPEED = 13.89  # 50 km/h urban limit


def write_plain_files():
    os.makedirs(NET_DIR, exist_ok=True)
    with open(os.path.join(NET_DIR, "tunis_centre.nod.xml"), "w") as f:
        f.write("<nodes>\n")
        for nid, (x, y, typ, name) in NODES.items():
            f.write(f'  <node id="{nid}" x="{x}" y="{y}" type="{typ}">'
                    f'<param key="name" value="{name}"/></node>\n')
        f.write("</nodes>\n")
    with open(os.path.join(NET_DIR, "tunis_centre.edg.xml"), "w") as f:
        f.write("<edges>\n")
        bus_lanes = set(config.simulation().get("bus_lanes") or [])
        for a, b, lanes, name in ROADS:
            for u, v in ((a, b), (b, a)):
                eid = f"{u}_{v}"
                if eid in bus_lanes and lanes >= 2:       # right lane reserved for buses
                    f.write(f'  <edge id="{eid}" from="{u}" to="{v}" numLanes="{lanes}" speed="{SPEED}" '
                            f'name="{name}"><lane index="0" allow="bus emergency"/></edge>\n')
                else:
                    f.write(f'  <edge id="{eid}" from="{u}" to="{v}" '
                            f'numLanes="{lanes}" speed="{SPEED}" name="{name}"/>\n')
        f.write("</edges>\n")


def netconvert(tls_type, out):
    cmd = [
        os.path.join(BIN, "netconvert"),
        "-n", os.path.join(NET_DIR, "tunis_centre.nod.xml"),
        "-e", os.path.join(NET_DIR, "tunis_centre.edg.xml"),
        "--sidewalks.guess", "true",       # pavements on every road
        "--crossings.guess", "true",       # zebra crossings at junctions
        "--tls.default-type", tls_type,
        "--tls.yellow.time", str(YELLOW),
        "--no-turnarounds", "true",
        "--junctions.corner-detail", "5",
        "-o", out,
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def write_bus_stops(net_file):
    """One stop on each bus line, just before every signalised junction it reaches."""
    import sumolib
    from traffix.demand.generator import BUS_LINES
    net = sumolib.net.readNet(net_file)
    stops = {}
    for line, first, last in BUS_LINES:
        if not (net.hasEdge(first) and net.hasEdge(last)):
            continue
        path, _ = net.getShortestPath(net.getEdge(first), net.getEdge(last), vClass="bus")
        for e in path or []:
            if e.getToNode().getType() != "traffic_light":
                continue
            lane = next(l for l in e.getLanes() if l.allows("bus"))
            end = max(10.0, lane.getLength() - 30)
            st = stops.setdefault(e.getID(), {"lane": lane.getID(), "start": max(0.0, end - 20), "end": end,
                                              "junction": e.getToNode().getID(), "lines": []})
            st["lines"].append(line)
    out = net_file.replace(".net.xml", ".stops.xml")
    with open(out, "w") as f:
        f.write("<additional>\n")
        for edge, st in stops.items():
            name = NODES.get(st["junction"], (0, 0, 0, st["junction"]))[3]
            f.write(f'  <busStop id="stop_{edge}" lane="{st["lane"]}" startPos="{st["start"]:.1f}" '
                    f'endPos="{st["end"]:.1f}" lines="{" ".join(st["lines"])}" name="{name}">'
                    f'<param key="junction" value="{st["junction"]}"/></busStop>\n')
        f.write("</additional>\n")
    print(f"Wrote {len(stops)} bus stops to {out}")


if __name__ == "__main__":
    write_plain_files()
    static, actuated = (os.path.join(NET_DIR, "tunis_centre.net.xml"),
                        os.path.join(NET_DIR, "tunis_centre_actuated.net.xml"))
    netconvert("static", static)
    netconvert("actuated", actuated)
    write_bus_stops(static)
    print("Built", static, "and", actuated)
