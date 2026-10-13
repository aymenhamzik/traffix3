"""
What a forward-looking traffic light agent sees: its own junction, where traffic
is heading, and the neighbouring junctions. Shared by the predictive agent, the
reinforcement learning agent and their training. Pure functions: no SUMO access.

Observation (36 numbers, same layout at every junction so one policy fits all):
  for each of up to 4 green phases:
    queue        vehicles stopped on the approaches this phase serves
    arriving     vehicles moving towards the stop line on those approaches
    downstream   vehicles queued on the exits (is there room ahead?)
    released     share of those approaches whose UPSTREAM junction is sending a platoon now
    upstream_q   vehicles queued at the upstream junction that will come this way
    pedestrians  people waiting for this phase's walk signal
    current      1 if this is the current green
    valid        1 if the junction has this phase
  then: time in green, demand forecast level, forecast inbound share, rain
"""
import numpy as np

MAX_PHASES = 4
OBS_SIZE = MAX_PHASES * 8 + 4   # the RL agent appends one more: pressure advantage of switching


def phase_lanes(m, phase):
    return sorted({l.in_lane for l in m.vehicle_links if phase[l.index] in "Gg"})


def upstream_info(ctx, edge):
    """Is the upstream junction releasing traffic into `edge`, and how much is queued there for it?"""
    sensors, bus = ctx.sensors, ctx.bus
    up = sensors.edge_from_node.get(edge)
    if up not in ctx.models:
        return 0.0, 0.0, 0.0, 0.0
    st = bus.status.get(up, {})
    released = 1.0 if edge in st.get("released_edges", []) else 0.0
    feeding = [l.in_lane for l in ctx.models[up].vehicle_links if l.out_edge == edge]
    q = sum(sensors.lane(x).halting for x in set(feeding) if x in sensors.readings)
    mv = sum(sensors.lane(x).vehicles - sensors.lane(x).halting for x in set(feeding) if x in sensors.readings)
    return 1.0, released, float(q), float(mv)


def build_obs(ctx, m, status):
    s = ctx.sensors
    green = status["green"]
    obs = []
    for k in range(MAX_PHASES):
        if k >= len(m.green_phases):
            obs += [0.0] * 8
            continue
        ph = m.green_phases[k]
        lanes = phase_lanes(m, ph)
        outs = sorted({l.out_lane for l in m.vehicle_links if ph[l.index] in "Gg"})
        edges = sorted({l.in_edge for l in m.vehicle_links if ph[l.index] in "Gg"})
        ups = [upstream_info(ctx, e) for e in edges]
        peds = sum(s.waiting_at.get(c, (0, 0))[0] for c in m.crossings if m.crossing_green(ph, c))
        obs += [sum(s.lane(l).halting for l in lanes) / 10,
                sum(len(s.lane(l).approach) for l in lanes) / 10,
                sum(s.lane(l).halting for l in outs) / 10,
                (sum(u[1] for u in ups) / len(ups)) if ups else 0.0,
                sum(u[2] for u in ups) / 10,
                peds / 10, 1.0 if ph == green else 0.0, 1.0]
    f = ctx.bus.forecast
    obs += [min(status["time_in_green"], 120) / 60, f.get("level") or 0.8,
            f.get("inbound_share", 0.5), s.weather.get("rain", 0.0)]
    return np.array(obs, dtype=float)


def arrival_features(ctx, edge, recent_entries):
    """Inputs of the arrival model: how many vehicles will enter this approach in the next 30 s."""
    is_sig, released, up_q, up_mv = upstream_info(ctx, edge)
    f = ctx.bus.forecast
    return [is_sig, released, up_q, up_mv, recent_entries, f.get("level") or 0.8,
            ctx.sensors.edge_length.get(edge, 200.0)]


ARRIVAL_FEATURES = ["upstream_is_signal", "upstream_releasing", "upstream_queue", "upstream_moving",
                    "entries_last_30s", "forecast_level", "road_length"]
