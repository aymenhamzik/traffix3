"""
Notification agent (network). Turns events into messages for the 7 persona pages.

Sources: publications (incidents, congestion, floods, rain, late buses, stale
data, Route B, ambulance routes, the demand forecast) and new decision-log entries (emergency grants and denials, walk signals,
clearance holds, bus priority). Learned (models/notification.joblib): a
classifier deciding which personas an event is relevant to. Its labels come
from rules we wrote (no real users click on alerts), so it learns our
assumptions back: useful for the pipeline, not evidence of user preference.
"""
from ...synapse.i18n import LANGS, alert_text
from ..base import Agent

PERSONAS = ["pedestrian", "car_driver", "bus_passenger", "bus_driver",
            "emergency_crew", "operator", "analyst"]

# event type -> (personas it is relevant to, severity, text template)
RULES = {
    "INCIDENT": ({"car_driver", "operator", "emergency_crew", "bus_driver"}, "warning",
                 "Lane blocked on {edge} (confidence {confidence:.0%}). Cause not determined."),
    "FLOOD": ({"car_driver", "pedestrian", "bus_driver", "bus_passenger", "operator"}, "danger",
              "Flood alert: {edge} is impassable."),
    "RAIN": ({"car_driver", "pedestrian", "bus_driver", "operator"}, "info",
             "Rain: expect traffic about {slow:.0%} slower. Signal timings lengthened."),
    "ROUTE_B": ({"car_driver"}, "info", "Route B around {edge} saves about {saving_s} s."),
    "CONGESTION": ({"car_driver", "bus_driver", "bus_passenger", "operator"}, "warning",
                   "Heavy traffic on {edge}: {stopped_vehicles} vehicles stopped near {junction}."),
    "PEAK_FORECAST": ({"car_driver", "bus_driver", "bus_passenger", "operator"}, "info",
                      "Busy period expected around {when} ({direction} traffic). Allow extra time."),
    "AMBULANCE_NEAR": ({"car_driver", "pedestrian", "bus_driver"}, "danger",
                       "{kind} reaching {tls} in about {eta_s:.0f} s: keep the junction clear."),
    "TRANSIT_LATE": ({"bus_driver", "bus_passenger", "operator"}, "warning",
                     "{vehicle} on line {line} is late (gap {gap:.0f} s)."),
    "DATA_STALE": ({"operator"}, "warning", "Detector {lane} stopped updating; junction on local control."),
    "EMERGENCY_GRANTED": ({"emergency_crew", "operator"}, "info", "Green given to {vehicle} at {tls}."),
    "EMERGENCY_DENIED": ({"emergency_crew", "operator", "analyst"}, "danger",
                         "Priority denied to {vehicle} at {tls}: exit lane full."),
    "EMERGENCY_PREPARE": ({"emergency_crew"}, "info", "{tls} is preparing for {vehicle} (arrival in {eta_s:.0f} s)."),
    "WALK_GRANTED": ({"pedestrian"}, "info", "Walk signal given at {tls} after a long wait."),
    "CLEARANCE": ({"pedestrian", "analyst"}, "info", "Green held at {tls} until the crossing was clear."),
    "TRANSIT_GRANTED": ({"bus_driver", "bus_passenger"}, "info", "Priority given to late bus {vehicle} at {tls}."),
}
EVENT_TYPES = list(RULES)
LOG_EVENTS = {"EMERGENCY_GRANTED_SWITCH": "EMERGENCY_GRANTED", "EMERGENCY_GRANTED_HOLD": "EMERGENCY_GRANTED",
              "EMERGENCY_DENIED_EXIT_FULL": "EMERGENCY_DENIED", "EMERGENCY_PREPARE": "EMERGENCY_PREPARE",
              "PED_SERVICE_GRANTED": "WALK_GRANTED", "CLEARANCE_EXTENDED": "CLEARANCE",
              "TRANSIT_GRANTED_SWITCH": "TRANSIT_GRANTED", "TRANSIT_GRANTED_EXTEND": "TRANSIT_GRANTED"}


def relevance_features(event_type, persona):
    x = [0] * (len(EVENT_TYPES) + len(PERSONAS))
    x[EVENT_TYPES.index(event_type)] = 1
    x[len(EVENT_TYPES) + PERSONAS.index(persona)] = 1
    return x


class NotificationAgent(Agent):
    name = "notification"
    model_file = "notification.joblib"
    KEEP = 400

    def __init__(self, ctx):
        super().__init__(ctx)
        self.seen, self.log_pos, self.next_id = set(), 0, 1
        n = len(relevance_features(EVENT_TYPES[0], PERSONAS[0]))
        if self.model is not None and getattr(self.model, "n_features_in_", n) != n:
            print("[TraffiX] notification model is out of date (alert types changed); using rules. "
                  "Run  python scripts/train.py --skip-tune")
            self.model = None

    def relevant(self, event_type, persona):
        if self.model is not None:
            return bool(self.model.predict([relevance_features(event_type, persona)])[0])
        return persona in RULES[event_type][0]

    def emit(self, now, event_type, key, ref=None, where=None, **fields):
        """where: {"edges": [...], "junctions": [...], "line": ...} lets each persona page keep
        only the alerts on its own trip, stop or line."""
        if key in self.seen:
            return
        self.seen.add(key)
        _, severity, template = RULES[event_type]
        try:
            text = template.format(**fields)
        except (KeyError, ValueError):
            text = event_type
        simple = {k: v for k, v in fields.items() if isinstance(v, (str, int, float))}
        texts = {lang: alert_text(event_type, lang, simple) or text for lang in LANGS}
        for persona in PERSONAS:
            if self.relevant(event_type, persona):
                self.bus.notifications.append({"id": self.next_id, "t": now,
                                               "time": self.ctx.clock(now).strftime("%H:%M:%S"),
                                               "persona": persona, "type": event_type,
                                               "severity": severity, "text": text, "texts": texts,
                                               "fields": simple, "ref": ref, "where": where or {}})
                self.next_id += 1
        del self.bus.notifications[:-self.KEEP]

    def step(self, now):
        to_node = self.sensors.edge_to_node
        for p in self.bus.published("INCIDENT"):
            self.emit(now, "INCIDENT", ("INC", p.subject, p.t), edge=p.subject,
                      where={"edges": [p.subject], "junctions": [to_node.get(p.subject)]}, **p.details)
        for p in self.bus.published("CONGESTION"):
            self.emit(now, "CONGESTION", ("JAM", p.subject, p.t), edge=p.subject,
                      where={"edges": [p.subject], "junctions": [p.details.get("junction")]}, **p.details)
        for p in self.bus.published("FLOOD"):
            self.emit(now, "FLOOD", ("FLOOD", p.subject), edge=p.subject,
                      where={"edges": [p.subject], "junctions": [to_node.get(p.subject)]})
        for p in self.bus.published("AMBULANCE_ROUTE"):
            for tls, eta in p.details["junctions"]:
                if eta <= self.cfg["notification"]["ambulance_horizon"]:
                    self.emit(now, "AMBULANCE_NEAR", ("AMB", p.subject, tls), tls=tls, eta_s=eta,
                              kind=p.details.get("kind", "ambulance").capitalize(), where={"junctions": [tls]})
        f = self.bus.forecast
        if f.get("level") and f["level"] >= self.cfg["notification"]["peak_level"]:
            share = f.get("inbound_share", 0.5)
            direction = "inbound" if share > 0.55 else "outbound" if share < 0.45 else "two-way"
            self.emit(now, "PEAK_FORECAST", ("PEAK", f.get("for", "")[:13]), when=f.get("for", "")[11:16],
                      direction=direction)
        for p in self.bus.published("WEATHER"):
            if p.details["intensity"] > 0:
                self.emit(now, "RAIN", ("RAIN", p.details["intensity"]),
                          slow=1 - p.details["expected_speed_factor"])
        for p in self.bus.published("ROUTE_B"):
            self.emit(now, "ROUTE_B", ("RB", p.subject, p.t), edge=p.subject,
                      where={"edges": [p.subject]}, **p.details)
        for p in self.bus.published("TRANSIT_LATE"):
            self.emit(now, "TRANSIT_LATE", ("LATE", p.subject), vehicle=p.subject,
                      where={"line": p.details.get("line")}, **p.details)
        for p in self.bus.published("DATA_STALE"):
            self.emit(now, "DATA_STALE", ("STALE", p.subject, p.t), lane=p.subject)
        entries = self.log.entries[self.log_pos:]
        self.log_pos = len(self.log.entries)
        for e in entries:
            ev = LOG_EVENTS.get(e["reason"])
            if ev:
                d = dict(e["details"])
                d.setdefault("eta_s", 0)
                key = (ev, d.get("vehicle"), e.get("tls")) if d.get("vehicle") else ("LOG", e["id"])
                line = d.get("vehicle", "")[4:].rsplit("_", 1)[0] if str(d.get("vehicle", "")).startswith("bus_") else None
                self.emit(now, ev, key, ref=e["id"], tls=e.get("tls"),
                          where={"junctions": [e.get("tls")], "line": line}, **d)
