# TraffiX v2 · Hierarchical multi-agent traffic control for central Tunis

Junction agents advise. Each junction's **master** decides and is the only writer of its light.
A **supermaster** with eight network agents coordinates the masters. Seven persona pages show the result.

> Simulation on a schematic network of central Tunis. Calendar values are project assumptions.
> We do not claim lives saved, measured air quality or a Tunis deployment.

## 1. Setup (once)

    python -m pip install -r requirements.txt
    python scripts/setup.py

`setup.py` builds the network and the traffic, and retrains the models if they are missing or were
saved with a different scikit-learn version (models only load in the version that saved them).
The included models were trained with **scikit-learn 1.9.1**, which `requirements.txt` pins.
If a model can't be loaded, the agent prints one message and uses its rule-based fallback;
the simulation never crashes because of a model file.

Frontend: a built copy is in `frontend/dist`. Only to edit it: install Node.js, then `cd frontend` and `npm install`.

## 2. Run

Live demo with the persona pages:

    python scripts/run_live.py            # open http://localhost:8000, pick a scenario and an agent, press Start

Experiments for the report (about 1 hour; don't run at the same time as the live demo on 8 GB):

    python scripts/run_experiments.py     # 5 controllers x 12 scenarios x 3 seeds
    python scripts/analyze.py             # persona tables, t-tests, charts in results/

Other commands:

    python tests/test_core.py             # quick tests
    python scripts/check_architecture.py  # proves the hierarchy rules hold
    python scripts/train.py               # full retraining incl. traffic-light tuning (~15 min)
    python scripts/train.py --skip-tune   # models only (~3-5 min)
    python scripts/run_experiments.py --scenario morning_peak --seeds 1     # one quick scenario
    python scripts/ask.py results/logs/decisions_traffix_emergency_1.jsonl "Why did ambulance1 get green at F4?"

While editing the frontend, also run `npm run dev` in `frontend/` and open http://localhost:5173;
afterwards `npm run build` so port 8000 serves the new version.

## 3. Folder structure

```
config/                 every assumption, in YAML (edit these, not the code)
  simulation.yaml       seeds, controllers, demand volumes, Tunis coordinates
  calendar.yaml         month, weekday, hourly, Ramadan and Eid factors
  scenarios.yaml        the 12 scenarios (date + time + hidden events)
  agents.yaml           safety rules, thresholds, priority order
data/networks/          Tunis network files
traffix/
  core/                 config loader, message bus, decision log, priority order
  simulation/           SUMO connection, sensors, executor (the only light writer), world events
  demand/               calendar model, Hijri dates, sunset, trip generator
  agents/junction/      traffic_light, pedestrian, transit_priority, emergency_priority, sensor_health
  agents/network/       demand_forecast, incident_detection, rerouting, emergency_route, corridor,
                        transit_monitor, weather, notification, explainer (Synapse)
  orchestration/        master.py, supermaster.py, safety_rules.py, system.py
  training/             data generation, model training, traffic-light tuning
  evaluation/           monitor (persona metrics), runner, analysis
  api/                  FastAPI backend + live mode for the frontend
frontend/               React app: overview + 7 persona pages
models/                 trained models + metrics.json
scripts/                every command above
results/                experiment CSVs, charts, decision logs
```

### Bus stops and bus lanes
`build_network.py` places a bus stop before every signalised junction on each bus line (buses dwell
`bus_stop_dwell` seconds, set in `config/simulation.yaml`). Bus lanes are optional: list roads in
`bus_lanes` (for example `[B1_B2, B2_B3, B3_B4, B4_B3, B3_B2, B2_B1]`), then rerun
`build_network.py`, `setup.py`, training and experiments. A bus lane removes a lane from cars, so
compare results with and without it.

## 4. The hierarchy

| Level | Component | Role |
|---|---|---|
| Junction (x7) | 5 agents | traffic light (proposes phase), pedestrian, transit priority, emergency priority, sensor health |
| Junction (x7) | traffic light variants | **max-pressure** (default), **predictive / MPC**, **reinforcement learning**: choose with the controller |
| Junction (x7) | **Master** | resolves requests in a fixed order (safety > emergency > supermaster directive > transit > pedestrian > normal), the only writer of its light |
| Network | **Supermaster** | runs 8 network agents every 5 s, sends directives, never writes a light |
| Network | 8 agents | demand forecasting, incident detection, rerouting, emergency route, corridor coordination, transit monitoring, weather, notification |
| Analyst | Explainer | Synapse: cites the decision log or abstains; no path to the simulation |

Safety rules (pedestrian clearance, yellow, minimum green, exit check) and the priority order are **never learned**.
Neighbouring masters share queues directly; the frontend talks only to the supermaster's API.

### The Synapse layer: language agents (English, French, Arabic)
Three agents read the system and write text, never lights (`traffix/synapse/`, checked by
`check_architecture.py`):
- **Explainer** (analyst page): answers "why?" from the decision log in the chosen language.
  With an API key it becomes a tool-using language-model agent (Claude or Groq) (search the log, live state, results);
  every citation is checked, otherwise it abstains.
- **Alert writer** (every persona page): each notification has built-in English, French and
  Arabic texts; with a key, the language model rewrites them for each persona. A rewrite that changes any
  number is rejected.
- **Operator copilot** (operator page): situation summary, suggested actions citing log entries,
  incident report drafts. Approve / Dismiss is **recorded in the decision log, never applied**.

Without a key everything uses templates (offline). To use a language model, set ONE key in the same
PowerShell window, then start the demo:

    $env:ANTHROPIC_API_KEY="your-key"      # Claude (Anthropic)
    $env:GROQ_API_KEY="your-key"           # or Groq (Llama models)
    python scripts/run_live.py

`provider: auto` in `config/agents.yaml` uses whichever key is set (Anthropic first). Groq model names
are in the same file (`groq_*_model`); check console.groq.com/docs/models if one is retired.

Models and timings: `config/agents.yaml > synapse`. Pick the language with EN / FR / عربي in the top bar.

## 5. Data and assumptions

Demand = base x hour x weekday x month, from `config/calendar.yaml`:
morning peak 08:00-09:00 (70% inbound), evening peak 17:00-18:00 (65% outbound), September 1.15,
July 0.75, August 0.70. Ramadan replaces the daily profile (pre-iftar rush 90 min before the computed
sunset); Eids and holidays replace the weekday factor. Hijri dates come from the `hijridate` library.

**Agents never read these values.** They learn them from the traffic they observe; scenario events
(incidents, floods, frozen sensors) are hidden from them too. `check_architecture.py` enforces this.

## 6. Training (train on 2025 dates, test on 2026)

| Agent | Model | Result vs the rule it replaces |
|---|---|---|
| Demand forecast | gradient boosting | Ramadan 2026 error 0.027 vs 0.103 for a "same date as last year" baseline |
| Incident detection | classifier | F1 0.85 vs 0.56 |
| Sensor health | classifier | F1 0.99 vs 0.98 |
| Pedestrian | classifier | F1 0.80 (only 41 long-wait examples: fragile) |
| Ambulance ETA | regression | 14 s vs 34 s error |
| Bus ETA | regression | 6 s vs 12 s |
| Bus lateness | regression | 9 s vs 35 s |
| Road travel time | regression | 3.6 s vs 18 s |
| Rain effect | regression | 0.05 vs 0.20 |
| Arrivals (predictive agent) | regression | 1.16 vs 1.60 vehicles per 30 s |
| Notification | decision tree | reproduces our own rules (no real user data) |
| Traffic light (max-pressure) + corridor | parameter tuning | 5% lower car + pedestrian wait than defaults |
| Traffic light (predictive / MPC) | arrival model + parameter tuning | 12% better than its defaults |
| Traffic light (reinforcement learning) | Fitted Q-Iteration (gradient-boosted trees) | see `models/metrics.json > rl_traffic_light` |
| Explainer | pretrained language model | (no training) |

### The three traffic light agents
- **Max-pressure** (`traffix`): greedy; green to the phase with most queued vehicles minus queued vehicles downstream.
- **Predictive / MPC** (`traffix_predictive`): predicts arrivals for the next 60 s from upstream junctions
  (platoons released, queues), vehicles already approaching and the demand forecast; checks room downstream;
  simulates keep / switch now / switch in 10 s and proposes the plan with the least predicted waiting.
- **Reinforcement learning** (`traffix_rl`): Fitted Q-Iteration (Ernst et al., 2005), one policy shared by all
  junctions, same neighbour/forecast observation, cooperative reward (own + neighbours' waiting). Learns *when*
  to switch; overrides max-pressure only when its learned values clearly disagree; starvation guard at 60 s.

Retrain: `python scripts/train.py --only-predictive` (~5 min) and `python scripts/train.py --only-rl` (~10 min).
Compare: `python scripts/run_experiments.py --controller traffix traffix_predictive traffix_rl`.
In the live demo, pick the agent in the top bar.

**Honest result so far:** max-pressure remains the best traffic light agent on this network; the RL agent is
close, the predictive agent behind. Max-pressure is known to be hard to beat on small networks.

## 7. Earlier results (at 2,600 vehicles/h; rerun the experiments for the current 4,000 vehicles/h)

| Car wait (s) | fixed | actuated | junction only | rules | **traffix** |
|---|---|---|---|---|---|
| morning peak | 37.0 | 20.4 | 19.2 | 18.6 | **18.3** |
| evening peak | 34.4 | 18.7 | 18.5 | 17.7 | **18.1** |
| emergency | 33.7 | 16.2 | 16.4 | 16.2 | **16.3** |
| Ramadan pre-iftar | 36.6 | 22.3 | 22.1 | 22.8 | **21.0** |
| combined | 33.0 | 18.7 | 16.8 | 22.1 | **20.9** |
| rain + flood | 125.5 | 110.9 | 127.7 | 141.2 | **124.0** |

Clearance truncations (green starting while someone is still crossing): 700-1,240 per hour for SUMO's
plans, **0** for every TraffiX variant. Pedestrian waits are lower than actuated in every scenario.

**Honest findings to report**
- Morning peak: TraffiX cuts car waiting by 10% vs actuated (significant over 3 seeds).
- The trained models help most in the Ramadan rush (21.0 s vs 22.8 s rule-based).
- **Combined scenario: junction-only beats the full hierarchy.** The weather agent's longer yellow and
  clearance cost more than they gain. A clear target for tuning `config/agents.yaml > weather`.
- **Rain with a flooded street congests every controller**; TraffiX is worse than actuated for cars there.

