"""
Starts the backend for the frontend (live demo).

  python scripts/run_live.py                       then open http://localhost:8000
  python scripts/run_live.py --scenario rain --speed 6
  python scripts/run_live.py --gui       also opens SUMO's window showing the SAME run as the browser

During development, run the React dev server too (see frontend/README.md).
"""
import argparse

import uvicorn

import _path  # noqa: F401
from traffix.api import server

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default=None, help="start this scenario immediately")
    p.add_argument("--speed", type=float, default=4.0, help="simulated seconds per real second")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--gui", action="store_true",
                   help="open SUMO's own window for the same simulation the browser shows")
    p.add_argument("--controller", default="traffix",
                   help="traffix (max-pressure), traffix_predictive, traffix_rl, traffix_rules, junction_only")
    a = p.parse_args()
    server.SETTINGS["gui"] = a.gui
    if a.scenario:
        server.start(a.scenario, a.speed, controller=a.controller)
    uvicorn.run(server.app, host="127.0.0.1", port=a.port)
