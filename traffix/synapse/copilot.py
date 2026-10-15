"""
Operator copilot (Synapse layer) for Kamel's page.

  summary(lang)   short situation summary + suggested actions, each citing log entries
  report(lang)    an incident report drafted from the decision log, with citations
  decide(...)     the operator approves or dismisses a suggestion: RECORDED in the log,
                  never applied automatically (the masters stay the only writers)

With an API key Claude writes them (JSON, citations checked); without one, rules and
templates produce them, in English, French or Arabic.
"""
import json

from ..core import config
from ..core.narrate import Narrator
from . import llm
from .i18n import COPILOT, LANG_NAMES, phrase

ROUTINE = {"MAX_PRESSURE_SWITCH", "CORRIDOR_PLATOON", "PREDICTIVE_SWITCH", "RL_POLICY_SWITCH",
           "ACTUATED_GAP_OUT", "ACTUATED_MAX_OUT", "FIXED_CYCLE", "BUS_NOT_LATE", "BUS_NO_REFERENCE",
           "NOTIFICATION_SENT", "FORECAST_UPDATE", "EMERGENCY_REQUEST", "EMERGENCY_PREPARE"}

SYSTEM = """You are the operator copilot of a SIMULATED traffic control room for central Tunis.
Use ONLY the data given. Answer in {language}. Return ONLY JSON:
{{"summary": "<3 sentences max>", "suggestions": [{{"title": "<action, imperative>", "why": "<one sentence>", "citations": [<log ids>]}}]}}
At most 4 suggestions, most urgent first; [] if nothing needs attention. Every suggestion must cite
log entry ids from the data. Never state a cause the data does not give (a blocked lane is a
pattern, not a confirmed crash). Suggestions are advice: the operator decides; nothing is applied
automatically."""

REPORT = """You write a short incident report for a SIMULATED traffic control room in central Tunis,
in {language}, from ONLY the decision log entries given. Structure: title, what happened (time
order), how the system responded, open issues. Cite every fact with its entry id like [#123].
Never invent causes or numbers. Plain text, at most 250 words."""


class Copilot:
    def __init__(self, live):
        self.live = live
        c = config.agents()["synapse"]
        self.model, self.every = "copilot", c["copilot_every"]
        self.cache = {}

    def _narrator(self):
        return getattr(self.live, "narrator", None) or Narrator()

    def important(self, limit=60):
        es = [e for e in self.live.log.entries[-4000:] if e["reason"] not in ROUTINE]
        return es[-limit:]

    def context(self):
        s, n = self.live.state(), self._narrator()
        return {"clock": s.get("clock"), "scenario": s.get("scenario"),
                "vehicles": s.get("counts", {}).get("vehicles"), "pedestrians": s.get("counts", {}).get("pedestrians"),
                "junctions": [{"id": j["id"], "mode": j["mode"], "queue": j["queue"], "emergency": j["preempt"]}
                              for j in s.get("junctions", [])],
                "incidents": s.get("incidents", []), "congestion": s.get("congestion", []),
                "floods": s.get("floods", []), "stale_detectors": [x["subject"] for x in s.get("stale", [])],
                "weather": s.get("weather", {}), "forecast": s.get("forecast", {}),
                "log": [{"id": e["id"], "text": n.describe(e)} for e in self.important()]}

    # ------------------------------------------------------------------ summary
    def summary(self, lang="en"):
        s = self.live.state()
        bucket = int(s.get("t", 0) // self.every)
        key = (lang, bucket, len(self.live.log.entries) // 200)
        if key in self.cache:
            return self.cache[key]
        result = None
        if llm.available():
            try:
                reply, _ = llm.chat(self.model, SYSTEM.format(language=LANG_NAMES[lang]),
                                    json.dumps(self.context(), ensure_ascii=False, default=str), max_tokens=900)
                data = llm.extract_json(reply)
                valid = {e["id"] for e in self.live.log.entries}
                if isinstance(data, dict) and isinstance(data.get("summary"), str):
                    sugg = [x for x in data.get("suggestions", []) if isinstance(x, dict) and x.get("title")
                            and all(c in valid for c in x.get("citations", []))]
                    result = {"summary": data["summary"], "suggestions": sugg, "engine": "llm"}
            except Exception as e:
                print(f"[Synapse copilot] {e.__class__.__name__}: {e}")
        result = result or self._rules(s, lang)
        for i, x in enumerate(result["suggestions"]):
            x["id"] = f"{bucket}-{i}"
        result["clock"] = s.get("clock")
        self.cache[key] = result
        return result

    def _rules(self, s, lang):
        weather = phrase(COPILOT, "rain", lang, rain=s["weather"]["rain"]) if s.get("weather", {}).get("rain") \
            else phrase(COPILOT, "dry", lang)
        emergency = sum(1 for v in s.get("vehicles", []) if v["kind"] in ("ambulance", "police", "fire"))
        summary = phrase(COPILOT, "summary", lang, vehicles=s.get("counts", {}).get("vehicles", 0),
                         people=s.get("counts", {}).get("pedestrians", 0), incidents=len(s.get("incidents", [])),
                         jams=len(s.get("congestion", [])), stale=len(s.get("stale", [])),
                         emergency=emergency, weather=weather)
        log = self.important(400)
        cite = lambda reason, **match: [e["id"] for e in log if e["reason"] == reason
                                        and all(e["details"].get(k) == v for k, v in match.items())][-3:]
        sugg = []
        for st in s.get("stale", [])[:2]:
            sugg.append({"title": phrase(COPILOT, "s_stale", lang, lane=st["subject"]),
                         "citations": cite("DATA_STALE", lane=st["subject"])})
        for inc in s.get("incidents", [])[:2]:
            sugg.append({"title": phrase(COPILOT, "s_incident", lang, edge=inc["subject"],
                                         confidence=inc.get("confidence", 0)),
                         "citations": cite("INCIDENT_SUSPECTED", edge=inc["subject"])})
        jams = s.get("congestion", [])
        if len(jams) >= 2:
            worst = max(jams, key=lambda j: j.get("stopped_vehicles", 0))
            sugg.append({"title": phrase(COPILOT, "s_jam", lang, n=len(jams), edge=worst["subject"]),
                         "citations": cite("CONGESTION_DETECTED", edge=worst["subject"])})
        denied = [e for e in log if e["reason"] == "EMERGENCY_DENIED_EXIT_FULL"][-1:]
        if denied:
            sugg.append({"title": phrase(COPILOT, "s_denied", lang, tls=denied[0]["tls"]),
                         "citations": [denied[0]["id"]]})
        if s.get("weather", {}).get("rain"):
            sugg.append({"title": phrase(COPILOT, "s_rain", lang), "citations": cite("WEATHER_RAIN")})
        return {"summary": summary, "suggestions": sugg[:4], "engine": "rules",
                "empty_text": phrase(COPILOT, "s_none", lang)}

    # ------------------------------------------------------------------ report
    def report(self, lang="en"):
        n, entries = self._narrator(), self.important(80)
        if llm.available():
            try:
                text, _ = llm.chat(self.model, REPORT.format(language=LANG_NAMES[lang]),
                                   "\n".join(f"[#{e['id']}] {n.describe(e)}" for e in entries), max_tokens=900)
                if text:
                    return {"report": text, "engine": "llm"}
            except Exception as e:
                print(f"[Synapse copilot] {e.__class__.__name__}: {e}")
        lines = [phrase(COPILOT, "report_title", lang) + f" · {self.live.state().get('clock', '')}",
                 phrase(COPILOT, "report_events", lang) + (" " + COPILOT["english_note"][lang] if lang != "en" else "")]
        lines += [f"- {n.describe(e)} [#{e['id']}]" for e in entries[-15:]]
        return {"report": "\n".join(lines), "engine": "rules"}

    # ------------------------------------------------------------------ operator decision
    def decide(self, suggestion_id, title, decision, now):
        reason = "OPERATOR_APPROVED" if decision == "approve" else "OPERATOR_DISMISSED"
        return self.live.log.log(now, "operator", "grant" if decision == "approve" else "abstain", reason,
                                 suggestion=title, suggestion_id=suggestion_id, applied=False)
