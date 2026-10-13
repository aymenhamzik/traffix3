"""
Turns results/r_*.csv into persona tables, significance tests and charts.

Three comparisons answer three questions:
  traffix vs actuated        does the system beat a strong standard controller?
  traffix vs junction_only   what does the supermaster (cooperation) add?
  traffix vs traffix_rules   what do the trained models add?
"""
import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats

from ..core import config

OUT = config.path("results")
CTRL = ["fixed", "actuated", "junction_only", "traffix_rules", "traffix", "traffix_predictive", "traffix_rl"]
COLORS = {"fixed": "#9e9e9e", "actuated": "#5c8ac9", "junction_only": "#e3a046",
          "traffix_rules": "#8fbcb8", "traffix": "#1f6f6b", "traffix_predictive": "#9b6bd1",
          "traffix_rl": "#d1608a"}
PERSONA_METRICS = [
    ("Ferjani (pedestrian)", "ped_mean_wait_s", "pedestrian wait (s)"),
    ("Ferjani (pedestrian)", "clearance_truncations", "clearance truncations"),
    ("Faycel (car driver)", "veh_mean_wait_s", "car wait (s)"),
    ("Faycel (car driver)", "veh_p95_travel_s", "P95 trip (s)"),
    ("Faycel (car driver)", "veh_unfinished", "unfinished trips"),
    ("Bus driver / Mamadou", "bus_headway_cv", "bus headway variation"),
    ("Bus driver / Mamadou", "bus_mean_travel_s", "bus trip (s)"),
    ("Touhami (ambulance)", "ambulance_mean_travel_s", "ambulance trip (s)"),
    ("Touhami (ambulance)", "ambulance_mean_wait_s", "ambulance stopped (s)"),
    ("Sustainability", "co2_g_per_trip", "CO2 per trip (g)"),
]


def load():
    main = os.path.join(OUT, "results.csv")
    if os.path.exists(main):                       # the full run from run_experiments.py
        return pd.read_csv(main)
    files = sorted(glob.glob(os.path.join(OUT, "r_*.csv")))
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True) if files else None


def paired(df, col, a, b, scen):
    x = df[(df.scenario == scen) & (df.controller == a)].sort_values("seed")[col]
    y = df[(df.scenario == scen) & (df.controller == b)].sort_values("seed")[col]
    if len(x) < 2 or len(x) != len(y) or x.isna().all():
        return None
    p = stats.ttest_rel(x, y).pvalue
    return x.mean(), y.mean(), (x.mean() - y.mean()) / max(y.mean(), 1e-9) * 100, p


def run():
    df = load()
    if df is None:
        print("No results yet: run scripts/run_experiments.py first")
        return
    scen = list(dict.fromkeys(df.scenario))
    rows = []
    for persona, col, label in PERSONA_METRICS:
        for s in scen:
            for c in CTRL:
                v = df[(df.scenario == s) & (df.controller == c)][col].dropna()
                if len(v):
                    rows.append({"persona": persona, "measure": label, "scenario": s, "controller": c,
                                 "mean": round(v.mean(), 2), "std": round(v.std(), 2)})
    summary = pd.DataFrame(rows)
    summary.to_csv(os.path.join(OUT, "summary_by_persona.csv"), index=False)
    pd.set_option("display.width", 220, "display.max_rows", 400)
    for col, label in [("veh_mean_wait_s", "Car wait (s)"), ("ped_mean_wait_s", "Pedestrian wait (s)"),
                       ("clearance_truncations", "Clearance truncations")]:
        print(f"\n{label}")
        print(df.pivot_table(index="scenario", columns="controller", values=col, sort=False)
              .reindex(columns=[c for c in CTRL if c in df.controller.unique()]).round(1))

    print("\nSignificance (paired t-tests over seeds; * = p < 0.05)")
    tests = []
    for a, b, q in [("traffix", "actuated", "vs actuated"), ("traffix", "junction_only", "supermaster adds"),
                    ("traffix", "traffix_rules", "models add"),
                    ("traffix_predictive", "traffix", "predictive vs max-pressure"),
                    ("traffix_rl", "traffix", "RL vs max-pressure")]:
        for col in ("veh_mean_wait_s", "ped_mean_wait_s", "ambulance_mean_travel_s"):
            for s in scen:
                r = paired(df, col, a, b, s)
                if r:
                    tests.append({"comparison": q, "metric": col, "scenario": s, "traffix": round(r[0], 2),
                                  "other": round(r[1], 2), "change_%": round(r[2], 1), "p": round(r[3], 4)})
    t = pd.DataFrame(tests)
    t.to_csv(os.path.join(OUT, "significance.csv"), index=False)
    if len(t):
        print(t[t.p < 0.05].to_string(index=False))

    panels = [("ped_mean_wait_s", "Ferjani: pedestrian wait (s)"),
              ("clearance_truncations", "Ferjani: clearance truncations"),
              ("veh_mean_wait_s", "Faycel: car wait (s)"), ("veh_p95_travel_s", "Faycel: P95 trip (s)"),
              ("bus_headway_cv", "Buses: headway variation"), ("co2_g_per_trip", "CO2 per trip (g)")]
    present = [c for c in CTRL if c in df.controller.unique()]
    fig, axes = plt.subplots(3, 2, figsize=(16, 13))
    w = 0.8 / len(present)
    for ax, (col, title) in zip(axes.flat, panels):
        for i, c in enumerate(present):
            g = df[df.controller == c].groupby("scenario")[col]
            m, sd = g.mean().reindex(scen), g.std().reindex(scen)
            ax.bar([j + (i - len(present) / 2 + 0.5) * w for j in range(len(scen))], m, w,
                   yerr=sd, capsize=2, color=COLORS[c], label=c)
        ax.set_xticks(range(len(scen)))
        ax.set_xticklabels(scen, rotation=30, ha="right", fontsize=8)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.3)
    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=len(present), bbox_to_anchor=(0.5, 0.97))
    fig.suptitle("TraffiX on a schematic central-Tunis network. Simulation, not a Tunis measurement.")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(OUT, "persona_charts.png"), dpi=120)
    print("\nSaved results/summary_by_persona.csv, significance.csv, persona_charts.png")
