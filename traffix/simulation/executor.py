"""
Executor: THE ONLY CODE THAT CHANGES A TRAFFIC LIGHT.

A1 asks the executor for a new green. The executor then runs the safe
transition, one second at a time:

  GREEN --> CLEARANCE (walk signal off, vehicles keep green, until the
            crossing is empty: the safety mask decides)
        --> YELLOW (3 s for every vehicle movement losing green)
        --> new GREEN

scripts/check_architecture.py fails if any other file writes a light.
The masters call it; nothing else may.
"""
from ..core import config
from .backend import traci

YELLOW = config.agents()["safety"]["yellow"]


class Executor:
    def __init__(self, models, mask, log):
        self.models, self.mask, self.log = models, mask, log
        self.st = {}
        self._written = {}

    def start(self, now):
        self.now = now
        for tls, m in self.models.items():
            self.st[tls] = {"green": m.green_phases[0], "since": now, "phase": "green"}
            self._write(tls, m.green_phases[0])

    # ---------------------------------------------------------------- for A1
    def status(self, tls):
        s = self.st[tls]
        return {"green": s["green"], "busy": s["phase"] != "green",
                "time_in_green": self.now - s["since"] if s["phase"] == "green" else 0}

    def request(self, tls, target, now, emergency=False, extra_yellow=0, extra_clearance=0):
        s = self.st[tls]
        if s["phase"] != "green" or target == s["green"]:
            return False
        if not self.mask.min_green_ok(now - s["since"], emergency):
            return False
        crossings = self.mask.crossings_needing_clearance(tls, s["green"], target)
        s.update(target=target, t0=now, crossings=crossings,
                 ctx={"extra_clearance": extra_clearance},
                 yellow=YELLOW + extra_yellow, phase="clearance" if crossings else "yellow")
        return True

    # ---------------------------------------------------------------- every second
    def step(self, now):
        self.now = now
        for tls, s in self.st.items():
            m = self.models[tls]
            if s["phase"] == "clearance":
                state = list(s["green"])
                for c in s["crossings"]:
                    for i in m.crossings[c]["indices"]:
                        state[i] = "r"          # "don't walk"; vehicles keep green
                self._write(tls, "".join(state))
                if self.mask.clearance_done(tls, s["crossings"], now - s["t0"], now, s["ctx"]):
                    s.update(phase="yellow", t0=now)
            if s["phase"] == "yellow":
                if now - s["t0"] < s["yellow"]:
                    self._write(tls, self._yellow(m, s["green"], s["target"]))
                else:
                    s.update(phase="green", green=s["target"], since=now)
                    self._write(tls, s["green"])

    @staticmethod
    def _yellow(m, cur, target):
        out = []
        for i, (c, t) in enumerate(zip(cur, target)):
            link = m.links[i]
            if c in "Gg" and t not in "Gg":
                out.append("r" if link and link.is_crossing else "y")
            elif link and link.is_crossing and t not in "Gg":
                out.append("r")
            else:
                out.append(c if c in "Gg" else "r")
        return "".join(out)

    def _write(self, tls, state):
        if self._written.get(tls) != state:
            traci.trafficlight.setRedYellowGreenState(tls, state)
            self._written[tls] = state
