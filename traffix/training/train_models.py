"""
Trains every learnable model and reports how it does on held-out data.

  demand_forecast   trained on 2025, tested on 2026 (Ramadan moves ~11 days:
                    the test checks the model learned "Ramadan", not "March")
  incident, pedestrian            classifiers (held-out 25%)
  ambulance_eta, bus_eta, bus_lateness, edge_travel_time, rain_speed   regressors
  sensor_health     classifier: frozen detector or not (labels from injected faults)
  notification      classifier on rule-made relevance labels
Each model is compared with the simple rule it replaces.
"""
import json
import os
import random
from datetime import datetime, timedelta

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import f1_score, mean_absolute_error, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier

from ..agents.network.notification import EVENT_TYPES, PERSONAS, RULES, relevance_features
from ..core import config
from ..demand import hijri
from ..demand.calendar_model import CalendarModel
from .features import calendar_features

DATA = config.path("data", "training")
MODELS = config.path(config.agents()["models_dir"])


def _save(name, model):
    os.makedirs(MODELS, exist_ok=True)
    joblib.dump(model, os.path.join(MODELS, f"{name}.joblib"))


def forecast_dataset(year, rng):
    cal, X, level, share, ram = CalendarModel(), [], [], [], []
    t = datetime(year, 1, 1)
    while t.year == year:
        lv, sh, _ = cal.level(t)
        X.append(calendar_features(t))
        level.append(lv * rng.gauss(1, 0.06))           # observed counts are noisy
        share.append(min(1, max(0, sh + rng.gauss(0, 0.03))))
        ram.append(hijri.info(t.date())["ramadan"])
        t += timedelta(minutes=30)
    return np.array(X), np.array(level), np.array(share), np.array(ram)


def train_forecast():
    rng = random.Random(0)
    Xtr, ytr, str_, _ = forecast_dataset(2025, rng)
    Xte, yte, ste, ram = forecast_dataset(2026, rng)
    lvl = HistGradientBoostingRegressor(max_iter=300, random_state=0).fit(Xtr, ytr)
    shr = HistGradientBoostingRegressor(max_iter=200, random_state=0).fit(Xtr, str_)
    pred = lvl.predict(Xte)
    # naive baseline: average 2025 level for the same month, weekday and hour (memorises the dates)
    key = lambda x: (int(x[2]), int(x[1]), int(x[0] * 2))
    sums = {}
    for x, y in zip(Xtr, ytr):
        k = key(x)
        sums.setdefault(k, []).append(y)
    avg = {k: float(np.mean(v)) for k, v in sums.items()}
    naive = np.array([avg.get(key(x), ytr.mean()) for x in Xte])
    _save("demand_forecast", {"level": lvl, "inbound_share": shr})
    return {"test_year": 2026,
            "mae_level": round(mean_absolute_error(yte, pred), 3),
            "mae_level_naive_same_date": round(mean_absolute_error(yte, naive), 3),
            "mae_level_ramadan": round(mean_absolute_error(yte[ram], pred[ram]), 3),
            "mae_level_ramadan_naive": round(mean_absolute_error(yte[ram], naive[ram]), 3),
            "mae_inbound_share": round(mean_absolute_error(ste, shr.predict(Xte)), 3)}


def _csv(name):
    """Training table; rows with missing values (e.g. a bus with no earlier bus to compare) are dropped."""
    p = os.path.join(DATA, f"{name}.csv")
    return pd.read_csv(p).dropna() if os.path.exists(p) else None


def train_classifier(name, rule=None):
    df = _csv(name)
    if df is None or df["label"].nunique() < 2:
        return {"skipped": "not enough labelled data"}
    return train_classifier_df(name, df, rule)


def train_classifier_df(name, df, rule=None):
    X, y = df.drop(columns="label").values, df["label"].values
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=0, stratify=y)
    clf = HistGradientBoostingClassifier(max_iter=200, class_weight="balanced", random_state=0).fit(Xtr, ytr)
    p = clf.predict(Xte)
    out = {"rows": len(df), "positives": int(y.sum()), "precision": round(precision_score(yte, p), 3),
           "recall": round(recall_score(yte, p), 3), "f1": round(f1_score(yte, p), 3)}
    if rule is not None:
        rp = rule(Xte)
        out["rule_f1"] = round(f1_score(yte, rp), 3)
    _save(name, clf)
    return out


def train_regressor(name, rule=None, save_as=None):
    df = _csv(name)
    if df is None or len(df) < 30:
        return {"skipped": "not enough data"}
    X, y = df.iloc[:, :-1].values, df.iloc[:, -1].values
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=0)
    reg = HistGradientBoostingRegressor(max_iter=200, random_state=0).fit(Xtr, ytr)
    out = {"rows": len(df), "mae": round(mean_absolute_error(yte, reg.predict(Xte)), 2)}
    if rule is not None:
        out["rule_mae"] = round(mean_absolute_error(yte, rule(Xte)), 2)
    _save(save_as or name, reg)
    return out


def train_sensor_health():
    """Classifier on detector timing: is this detector frozen? (labels from injected faults)"""
    df = _csv("sensor_health")
    if df is None or df["label"].nunique() < 2:
        return {"skipped": "no fault examples"}
    pos, neg = df[df.label == 1], df[df.label == 0]
    df = pd.concat([pos, neg.sample(min(len(neg), 60000), random_state=0)])
    out = train_classifier_df("sensor_health", df, rule=lambda X: (X[:, 0] > 10).astype(int))
    return out


def train_notification():
    X = [relevance_features(e, p) for e in EVENT_TYPES for p in PERSONAS]
    y = [int(p in RULES[e][0]) for e in EVENT_TYPES for p in PERSONAS]
    clf = DecisionTreeClassifier(random_state=0).fit(X, y)
    _save("notification", clf)
    return {"rows": len(X), "training_accuracy": round(clf.score(X, y), 3),
            "note": "labels are our own rules; the model reproduces them"}


def train_all():
    m = {"demand_forecast": train_forecast()}
    m["incident"] = train_classifier("incident", rule=lambda X: (X[:, 0] >= 1).astype(int))
    m["pedestrian"] = train_classifier("pedestrian", rule=lambda X: (X[:, 1] > 45).astype(int))
    eta_rule = lambda X: X[:, 0] / np.maximum(X[:, 1], 1.0)
    m["ambulance_eta"] = train_regressor("ambulance_eta", rule=eta_rule)
    m["bus_eta"] = train_regressor("bus_eta", rule=lambda X: X[:, 0] / np.maximum(X[:, 1], 2.0))
    m["bus_lateness"] = train_regressor("bus_lateness", rule=lambda X: X[:, 0])
    m["edge_travel_time"] = train_regressor("edge_travel_time",
                                            rule=lambda X: X[:, 3] / np.maximum(X[:, 2], 1.0))
    m["rain_speed"] = train_regressor("rain_speed", rule=lambda X: 1 - 0.2 * X[:, 0])
    m["arrivals"] = train_regressor("arrivals", rule=lambda X: X[:, 4])   # rule: same as last 30 s
    m["sensor_health"] = train_sensor_health()
    m["notification"] = train_notification()
    import sklearn
    import platform
    m["_versions"] = {"scikit-learn": sklearn.__version__, "numpy": np.__version__,
                      "python": platform.python_version()}
    with open(os.path.join(MODELS, "metrics.json"), "w") as f:
        json.dump(m, f, indent=1)
    return m
