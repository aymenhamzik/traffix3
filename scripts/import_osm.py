"""
Imports the REAL street network of central Tunis from OpenStreetMap.
Run this on your own machine (it needs internet access to openstreetmap.org).

  python scripts/import_osm.py                       # default: Bourguiba area
  python scripts/import_osm.py --bbox 10.160,36.790,10.195,36.810

Then use it for everything else:
  Windows (PowerShell):  $env:TRAFFIX_NETWORK="tunis_osm"
  Mac / Linux:           export TRAFFIX_NETWORK=tunis_osm
  python scripts/build_demand.py
  python scripts/run_experiments.py

The agents read junctions, phases and crossings from whatever network is
loaded, so no code changes are needed. Bus lines and the incident location
fall back to automatic choices on this network (see build_demand.py).
Check the result in sumo-gui (netedit can fix odd junctions by hand).
"""
import argparse
import os
import subprocess
import sys

import sumo

import _path  # noqa: F401
from traffix.core import config

NET_DIR = config.path("data", "networks")
YELLOW = config.agents()["safety"]["yellow"]

SUMO_HOME = os.environ.get("SUMO_HOME", sumo.SUMO_HOME)
TOOLS = os.path.join(SUMO_HOME, "tools")
# west, south, east, north: Avenue Habib Bourguiba from Bab Bhar to beyond
# Place du 14 Janvier, with Av. de Paris, Av. de Carthage, Av. Mohamed V and
# Av. Farhat Hached. Widen it if you want more of the city.
DEFAULT_BBOX = "10.168,36.793,10.192,36.806"

NETCONVERT_OPTS = [
    "--geometry.remove", "--roundabouts.guess", "--ramps.guess",
    "--junctions.join", "--tls.guess-signals", "--tls.discard-simple", "--tls.join",
    "--sidewalks.guess", "--crossings.guess",
    "--keep-edges.by-vclass", "passenger,pedestrian,bus",
    "--remove-edges.isolated", "--no-turnarounds", "true",
    "--tls.yellow.time", str(YELLOW),
    "--output.street-names",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", default=DEFAULT_BBOX, help="west,south,east,north")
    args = ap.parse_args()
    os.makedirs(NET_DIR, exist_ok=True)

    print("Downloading OpenStreetMap data for", args.bbox)
    subprocess.run([sys.executable, os.path.join(TOOLS, "osmGet.py"),
                    "--bbox", args.bbox, "--prefix", os.path.join(NET_DIR, "tunis_osm")], check=True)
    osm = os.path.join(NET_DIR, "tunis_osm_bbox.osm.xml")
    if not os.path.exists(osm):
        osm = os.path.join(NET_DIR, "tunis_osm.osm.xml")

    for tls_type, out in (("static", os.path.join(NET_DIR, "tunis_osm.net.xml")),
                          ("actuated", os.path.join(NET_DIR, "tunis_osm_actuated.net.xml"))):
        subprocess.run([os.path.join(SUMO_HOME, "bin", "netconvert"), "--osm-files", osm,
                        "--tls.default-type", tls_type, "-o", out] + NETCONVERT_OPTS,
                       check=True)
        print("Built", out)
    print("\nNext:  set TRAFFIX_NETWORK=tunis_osm, then build_demand.py and run_experiments.py")


if __name__ == "__main__":
    main()
