"""
The decision log: every grant, denial, abstention and mode change, each with
a reason code from the fixed list below. A decision without a valid reason
code raises an error, so reason-code coverage is 100% by construction.

Format: one JSON object per line (JSONL), e.g.
  {"id": 412, "t": 1203.0, "agent": "A1@B3", "event": "deny",
   "reason": "EMERGENCY_DENIED_EXIT_FULL", "tls": "B3",
   "details": {"vehicle": "ambulance2", "exit_lane": "B3_B4_1", "occupancy": 0.91}}
"""
import json

REASON_CODES = {
    # Master: normal control (traffic light agent proposals)
    "MAX_PRESSURE_SWITCH": "Switched to the phase with the highest pressure (queued vehicles minus queued vehicles downstream).",
    "PREDICTIVE_SWITCH": "Predictive agent: simulating the next 60 s showed switching now gives less total waiting than keeping the green.",
    "RL_POLICY_SWITCH": "Reinforcement learning agent: its learned policy valued switching higher than keeping the green.",
    "CORRIDOR_PLATOON": "Held or gave green for a platoon arriving from the neighbouring junction (corridor coordination).",
    "ACTUATED_GAP_OUT": "Fallback actuated mode: no more vehicles arriving on green, so the phase ended.",
    "ACTUATED_MAX_OUT": "Fallback actuated mode: green reached its maximum length.",
    "FIXED_CYCLE": "Fallback fixed-time mode: the timed phase ended.",
    "MODE_MAX_PRESSURE": "Junction returned to max-pressure: all its sensor data is fresh.",
    "MODE_ACTUATED": "Downstream data is stale, so the junction uses actuated control (incoming lanes only).",
    "MODE_FIXED": "Incoming data is stale, so the junction uses its fixed-time plan (local control).",
    # Emergency
    "EMERGENCY_REQUEST": "The emergency agent asked for green for an approaching emergency vehicle.",
    "EMERGENCY_PREPARE": "The emergency route coordinator warned this junction that an ambulance is coming.",
    "EMERGENCY_GRANTED_SWITCH": "The master switched to the emergency vehicle's phase; the exit had space.",
    "EMERGENCY_GRANTED_HOLD": "The emergency vehicle's movement was already green; the master held it.",
    "EMERGENCY_DENIED_EXIT_FULL": "Denied: the exit lane was full, so green would only move the queue.",
    "EMERGENCY_DENIED_OTHER_EMERGENCY": "Denied: another emergency vehicle with an earlier arrival was being served.",
    "RECOVERY_STARTED": "Emergency vehicle passed; the master returned to normal control.",
    "RECOVERED": "Queues at the junction returned to their level before the emergency.",
    "RECOVERY_INCOMPLETE": "Queues had not returned to the pre-emergency level within the time limit.",
    # Transit
    "TRANSIT_REQUEST_LATE_BUS": "The transit agent asked for priority: this bus is running late.",
    "BUS_NOT_LATE": "The transit agent abstained: the bus is on time or early, so it gets no priority.",
    "BUS_NO_REFERENCE": "The transit agent abstained: no previous bus of this line seen yet.",
    "TRANSIT_GRANTED_EXTEND": "The master extended the current green for a late bus.",
    "TRANSIT_GRANTED_SWITCH": "The master switched to the late bus's phase.",
    "TRANSIT_DENIED_EMERGENCY": "Denied: an emergency vehicle has priority at this junction.",
    "TRANSIT_DENIED_EXIT_FULL": "Denied: the bus's exit lane was full.",
    "TRANSIT_DENIED_MIN_GREEN": "Denied for now: the current green has not reached its minimum time.",
    # Pedestrians
    "PED_SERVICE_REQUEST": "The pedestrian agent asked for a walk signal: people are waiting too long.",
    "PED_SERVICE_GRANTED": "The master switched to a phase that gives waiting pedestrians a walk signal.",
    "PED_SERVICE_DEFERRED": "Deferred: an emergency vehicle has priority or minimum green not reached.",
    # Safety rules
    "CLEARANCE_EXTENDED": "A pedestrian was still on the crossing, so the conflicting green was held.",
    "CLEARANCE_CAP_REACHED": "The clearance hold reached its maximum; a pedestrian may still be crossing.",
    # Data health and incidents
    "DATA_STALE": "Sensor agent: this lane's detector stopped updating; its data is marked stale.",
    "DATA_FRESH": "Sensor agent: this lane's detector is updating again.",
    "INCIDENT_SUSPECTED": "Incident agent: a lane-blockage pattern was found. This is a pattern, not a confirmed cause.",
    "CONGESTION_DETECTED": "Incident agent: many vehicles have been stopped on this road for a while (congestion, not an incident).",
    "CONGESTION_CLEARED": "Incident agent: the congestion on this road has cleared.",
    "INCIDENT_CLEARED": "Incident agent: the lane-blockage pattern is no longer present.",
    # Rerouting, weather, corridor, forecast
    "REROUTE_ADVISORY": "Rerouting agent projected that an alternative route saves time. Advisory only; not applied.",
    "REROUTE_NOT_WORTH": "Rerouting agent found no alternative that saves meaningful time.",
    "WEATHER_RAIN": "Weather agent: rain reported; masters asked for longer yellow and clearance.",
    "WEATHER_CLEAR": "Weather agent: rain stopped; normal timings restored.",
    "WEATHER_FLOOD": "Weather agent: flood alert on a road; rerouting asked to avoid it.",
    "CORRIDOR_DIRECTION": "Corridor agent: dominant direction changed; masters asked to favour it.",
    "FORECAST_UPDATE": "Demand forecasting agent published its forecast for the coming hour.",
    "DIRECTIVE_APPLIED": "The master applied a supermaster directive.",
    # Operator decisions on copilot suggestions (recorded, never applied automatically)
    "OPERATOR_APPROVED": "The operator approved a copilot suggestion (recorded; the system does not apply it automatically).",
    "OPERATOR_DISMISSED": "The operator dismissed a copilot suggestion.",
    # Notifications
    "NOTIFICATION_SENT": "Notification agent sent a message to a persona page.",
}

DECISION_EVENTS = {"grant", "deny", "abstain", "switch", "mode", "hold", "request",
                   "publish", "advisory", "recovery", "directive", "notify"}


class DecisionLog:
    def __init__(self, path=None):
        self.path = path
        self.entries = []

    def log(self, t, agent, event, reason, tls=None, **details):
        if reason not in REASON_CODES:
            raise ValueError(f"Unknown reason code {reason!r}: every decision needs one")
        if event not in DECISION_EVENTS:
            raise ValueError(f"Unknown event {event!r}")
        entry = {"id": len(self.entries) + 1, "t": round(float(t), 1), "agent": agent,
                 "event": event, "reason": reason, "tls": tls,
                 "details": {k: (round(v, 2) if isinstance(v, float) else v)
                             for k, v in details.items()}}
        self.entries.append(entry)
        return entry["id"]

    def save(self):
        if self.path:
            with open(self.path, "w") as f:
                for e in self.entries:
                    f.write(json.dumps(e) + "\n")

    def count(self, reason=None, event=None):
        return sum(1 for e in self.entries
                   if (reason is None or e["reason"] == reason)
                   and (event is None or e["event"] == event))


def load(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]
