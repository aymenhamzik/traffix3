"""
The whole training pipeline (about 30-60 minutes on a laptop):

  python scripts/train.py              data, models, traffic-light tuning, reinforcement learning
  python scripts/train.py --skip-data  reuse data/training/*.csv
  python scripts/train.py --skip-tune  skip the max-pressure tuning
  python scripts/train.py --skip-rl    skip reinforcement learning
  python scripts/train.py --only-rl    reinforcement learning only (rounds: --rl-rounds 3)
"""
import argparse
import json

import _path  # noqa: F401
from traffix.training import datagen, rl, train_models, tune

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--skip-data", action="store_true")
    p.add_argument("--skip-tune", action="store_true")
    p.add_argument("--trials", type=int, default=8)
    p.add_argument("--skip-rl", action="store_true")
    p.add_argument("--only-rl", action="store_true")
    p.add_argument("--only-predictive", action="store_true")
    p.add_argument("--rl-rounds", type=int, default=3)
    a = p.parse_args()
    if a.only_predictive:
        print("Tuning the predictive traffic light agent...")
        print(tune.tune_predictive(a.trials))
        raise SystemExit
    if a.only_rl:
        print("Reinforcement learning (Fitted Q-Iteration)...")
        print(rl.train(a.rl_rounds))
        raise SystemExit
    if not a.skip_data:
        print("1/4 Generating training data (2025 dates)...")
        print(datagen.generate())
    print("2/4 Training models...")
    print(json.dumps(train_models.train_all(), indent=1))
    if not a.skip_tune:
        print("3/4 Tuning traffic light, corridor and predictive-agent parameters...")
        print(tune.tune(a.trials))
        print(tune.tune_predictive(a.trials))
    if not a.skip_rl:
        print("4/4 Reinforcement learning for the traffic light agent...")
        print(rl.train(a.rl_rounds))
    print("Models saved in models/")
