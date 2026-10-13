"""
One-time setup, safe to run again:
  1. builds the Tunis network
  2. builds the traffic for every scenario
  3. trains the models if they are missing or were saved with another
     scikit-learn version (the tuned traffic-light settings are kept)

  python scripts/setup.py
"""
import os
import subprocess
import sys

import _path  # noqa: F401
from traffix.agents.base import models_usable
from traffix.core import config

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script, *args):
    print(f"\n> python scripts/{script} {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, os.path.join(HERE, script), *args], check=True)


if __name__ == "__main__":
    net = config.network_files()[0]
    if not os.path.exists(net) or not os.path.exists(net.replace(".net.xml", ".stops.xml")):
        run("build_network.py")
    else:
        print("Network already built.")
    run("build_demand.py")
    ok, msg = models_usable()
    if ok:
        print("\nTrained models match your scikit-learn version.")
    else:
        print(f"\n{msg}")
        run("train.py", "--skip-tune")
    print("\nSetup complete. Next:  python scripts/run_live.py   then open http://localhost:8000")
