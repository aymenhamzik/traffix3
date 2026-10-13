"""
Reinforcement learning for the traffic light agent: Fitted Q-Iteration.
(Ernst, Geurts & Wehenkel, "Tree-based batch mode reinforcement learning", JMLR 2005)

Loop, repeated for several rounds (approximate policy iteration):
  1. COLLECT  run simulations on 2025 training scenarios. Each junction records
              (state, action, reward, next state) every 5 s. Round 1 copies
              max-pressure with random exploration; later rounds follow the
              current policy with some exploration.
  2. FIT      Q(s, a) <- reward + gamma * max_a' Q(s', a'), repeated K times with a
              gradient-boosted tree regressor, on all experience gathered so far.
  3. SAVE     models/rl_q.joblib; the next round collects with the improved policy.
gamma = 0.9 per 5-s decision: the agent values about the next minute.
"""
import json
import os
import random

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from ..agents.junction import rl_light
from ..core import config
from ..demand.generator import DemandGenerator
from ..evaluation.runner import run_one
from .datagen import ROUTES, TRAINING_SCENARIOS

MODEL = config.path(config.agents()["models_dir"], "rl_q.joblib")
GAMMA, K_ITER = 0.9, 12
SCENARIOS = ["tr_morning", "tr_evening", "tr_incident_a", "tr_ramadan", "tr_heavy", "tr_rush"]


def collect(round_no, seeds):
    rl_light.BUFFER.clear()
    rl_light.EXPLORE.update(collect=True, epsilon=0.3 if round_no == 0 else 0.1,
                            teacher=(round_no == 0))
    waits = []
    for sc in SCENARIOS:
        for seed in seeds:
            r = run_one("traffix_rl", sc, seed, route_dir=ROUTES, save_log=False)
            waits.append(r["veh_mean_wait_s"] + r["ped_mean_wait_s"])
    rl_light.EXPLORE.update(collect=False, epsilon=0.0, teacher=False)
    return list(rl_light.BUFFER), float(np.mean(waits))


def fit(data):
    S = np.array([d[0] for d in data])
    A = np.array([d[1] for d in data])
    R = np.array([d[2] for d in data])
    S2 = np.array([d[3] for d in data])
    N2 = np.array([d[4] for d in data])
    X = np.hstack([S, A[:, None].astype(float)])
    target = R.copy()
    q = None
    for _ in range(K_ITER):
        q = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.1, random_state=0).fit(X, target)
        nxt = np.column_stack([q.predict(np.hstack([S2, np.full((len(S2), 1), float(a))]))
                               for a in range(rl_light.N_ACTIONS)])
        target = R + GAMMA * nxt.max(axis=1)
    return q


def train(rounds=3, seeds=(1,)):
    gen = DemandGenerator(config.network_files()[0])
    for sc in SCENARIOS:
        for seed in seeds:
            gen.build(sc, TRAINING_SCENARIOS[sc], seed, ROUTES)
    random.seed(0)
    data, history = [], []
    for rnd in range(rounds):
        new, score = collect(rnd, seeds)
        data += new
        history.append({"round": rnd + 1, "behaviour": "max-pressure + exploration" if rnd == 0 else "learned policy + exploration",
                        "wait_car_plus_ped_s": round(score, 2), "transitions": len(data)})
        print(f"  round {rnd + 1}: collected {len(new)} transitions, car+ped wait {score:.2f}s", flush=True)
        joblib.dump(fit(data), MODEL)
    _, final = collect_eval(seeds)
    history.append({"round": "final", "behaviour": "learned policy, no exploration",
                    "wait_car_plus_ped_s": round(final, 2)})
    teacher = evaluate_teacher(seeds)
    history.append({"round": "reference", "behaviour": "max-pressure alone (traffix)",
                    "wait_car_plus_ped_s": round(teacher, 2)})
    meta = config.path(config.agents()["models_dir"], "metrics.json")
    m = json.load(open(meta)) if os.path.exists(meta) else {}
    m["rl_traffic_light"] = {"method": "Fitted Q-Iteration, HistGradientBoosting", "gamma": GAMMA,
                             "rounds": history}
    json.dump(m, open(meta, "w"), indent=1)
    return history


def collect_eval(seeds):
    waits = []
    for sc in SCENARIOS:
        for seed in seeds:
            r = run_one("traffix_rl", sc, seed, route_dir=ROUTES, save_log=False)
            waits.append(r["veh_mean_wait_s"] + r["ped_mean_wait_s"])
    return None, float(np.mean(waits))


def evaluate_teacher(seeds):
    waits = [run_one("traffix", sc, seed, route_dir=ROUTES, save_log=False) for sc in SCENARIOS for seed in seeds]
    return float(np.mean([r["veh_mean_wait_s"] + r["ped_mean_wait_s"] for r in waits]))
