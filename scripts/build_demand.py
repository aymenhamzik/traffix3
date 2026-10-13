"""
Builds traffic for every scenario in config/scenarios.yaml and every seed.

  python scripts/build_demand.py
  python scripts/build_demand.py --scenario rain heavy
"""
import argparse

import _path  # noqa: F401
from traffix.core import config
from traffix.demand.generator import DemandGenerator

if __name__ == "__main__":
    sc = config.scenarios()
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", nargs="+", default=list(sc), choices=list(sc))
    p.add_argument("--seeds", nargs="+", type=int, default=config.simulation()["seeds"])
    a = p.parse_args()
    gen = DemandGenerator(config.network_files()[0])
    for name in a.scenario:
        for seed in a.seeds:
            _, meta = gen.build(name, sc[name], seed, config.path("data", "generated"))
            print(f"  {name:18s} seed {seed}: starts {meta['start']}, {meta['vehicles']} vehicles")
