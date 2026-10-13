"""
Reinforcement learning traffic light agent. One per junction, ONE shared policy.

Method: Fitted Q-Iteration (Ernst, Geurts & Wehenkel, 2005), batch reinforcement
learning with gradient-boosted trees (training/rl.py). The model Q(state, action)
estimates the discounted future reward of each choice, so the agent learns to
act for what comes NEXT, not just the current second.

  state   36 numbers (agents/junction/observation.py): own queues, arriving
          vehicles, room downstream, platoons released by upstream junctions,
          queues at upstream junctions, pedestrians, forecast, rain
  action  WHEN to switch: 0 = keep the current green, 1 = switch to the phase
          max-pressure ranks best among the others (the RL agent learns timing,
          max-pressure supplies the candidate phase)
  safety  conservative improvement: it only overrides max-pressure's choice when
          its learned values clearly favour the other action (margin); a
          starvation guard switches after 60 s of green if anyone waits elsewhere
  reward  less waiting at this junction AND at its neighbours (cooperative),
          small penalty per switch

Decides every 5 s. Still only PROPOSES: the master and the safety rules decide.
Without a trained model (models/rl_q.joblib) it behaves like max-pressure.
"""
import random

import numpy as np

from ...core import config
from .observation import MAX_PHASES, build_obs
from .traffic_light import TrafficLightAgent

DECIDE_EVERY = 5

# Training hooks (set by training/rl.py, single process): exploration and experience buffer
EXPLORE = {"epsilon": 0.0, "teacher": False, "collect": False}
BUFFER = []


N_ACTIONS = 2          # 0 keep, 1 switch to max-pressure's best other phase
MARGIN = 0.05          # value advantage needed to disagree with max-pressure
MAX_GREEN = 60         # starvation guard (s)


def q_input(obs, action):
    return np.concatenate([obs, [float(action)]])


class RLTrafficLightAgent(TrafficLightAgent):
    name = "rl_light"
    model_file = "rl_q.joblib"

    def __init__(self, ctx, tls, master):
        super().__init__(ctx, tls, master)
        self.q = self._load(self.model_file)
        self.prev = None                 # (obs, action, n_phases) waiting for its reward
        self.reward = 0.0
        self.ped_w = self.p["ped_weight"]
        near = ({ctx.sensors.edge_from_node.get(l.in_edge) for l in self.m.vehicle_links}
                | {ctx.sensors.edge_to_node.get(l.out_edge) for l in self.m.vehicle_links})
        self.neighbours = sorted(near & (set(ctx.models) - {tls}))

    def _own_wait(self):
        s = self.sensors
        return (sum(s.lane(l).halting for l in self.m.incoming_lanes)
                + self.ped_w * sum(s.waiting_at.get(c, (0, 0))[0] for c in self.m.crossings))

    def _step_reward(self):
        nb = [self.bus.status[n]["queue_total"] for n in self.neighbours if n in self.bus.status]
        return -(self._own_wait() + 0.5 * (sum(nb) / len(nb) if nb else 0.0)) / 10.0

    def values(self, obs):
        X = np.vstack([q_input(obs, a) for a in range(N_ACTIONS)])
        return [float(v) for v in self.q.predict(X)]

    def step(self, now):
        if self.master.mode != "max_pressure":
            return super().step(now)
        if self.q is None and not EXPLORE["teacher"]:
            return super().step(now)                    # no model: max-pressure
        self.reward += self._step_reward()
        if int(now) % DECIDE_EVERY:
            return
        st = self.master.signal_status()
        green, tg = st["green"], st["time_in_green"]
        pr = {ph: self.pressure(ph) for ph in self.m.green_phases}
        others = [ph for ph in self.m.green_phases if ph != green]
        if not others:
            return
        best_other = max(others, key=pr.get)
        obs = np.append(build_obs(self.ctx, self.m, st),
                        [(pr[best_other] - pr.get(green, 0.0)) / 10])
        if EXPLORE["collect"] and self.prev is not None:       # training: store the experience
            p_obs, p_act, _ = self.prev
            BUFFER.append((p_obs, p_act, self.reward / DECIDE_EVERY, obs, N_ACTIONS))
        self.reward = 0.0
        teacher = 1 if pr[best_other] > pr.get(green, 0.0) + self.p["switch_margin"] else 0
        method, details = "policy", {}
        if random.random() < EXPLORE["epsilon"]:
            action, method = random.randrange(N_ACTIONS), "explore"
        elif self.q is None:
            action, method = teacher, "teacher"
        else:
            v = self.values(obs)
            action = teacher if abs(v[1] - v[0]) < MARGIN else int(v[1] > v[0])
            details = {"value_switch": round(v[1], 3), "value_keep": round(v[0], 3),
                       "max_pressure_choice": "switch" if teacher else "keep"}
        waiting_elsewhere = sum(self._phase_demand(ph) for ph in others) > 0
        if tg >= MAX_GREEN and waiting_elsewhere:
            action, method = 1, "starvation guard"
        busy = st["busy"] or tg < self.cfg["safety"]["min_green"]
        if action == 1 and not busy:
            self.send("PROPOSAL", self.tls, now, subject=best_other, reason="RL_POLICY_SWITCH",
                      method=method, **details)
        self.prev = (obs, action if not busy else 0, N_ACTIONS)

    def _phase_demand(self, ph):
        return self._demand(ph)
