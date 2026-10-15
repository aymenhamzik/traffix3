"""
Explainer agent (Synapse) - explains the decision log, with citations, or abstains.
Pretrained: uses a language model (Anthropic API) when a key is set; no extra training.

Read by Tahani (the incident-report reader). Synapse has NO path to the
simulation: it imports neither the backend, the sensors nor the executor
(scripts/check_architecture.py verifies this). It only reads a finished log file.

Two engines:
  "llm"      a language model (Anthropic API) is given ONLY the matching log
             entries and must cite them as [#id] or answer ABSTAIN.
             Every cited id is checked against the log; an answer citing an
             entry that does not exist is rejected and becomes an abstention.
  "template" no API key needed: a deterministic explanation built from the
             same entries and the plain-language reason codes.
"""
import json
import os
import re

from ...core.decision_log import REASON_CODES
from ...core.narrate import Narrator
from ...synapse import llm as synapse_llm
from ...synapse.i18n import EXPLAIN, LANG_NAMES, phrase

KEYWORDS = {
    "ambulance": ["EMERGENCY", "RECOVER"], "emergency": ["EMERGENCY", "RECOVER"],
    "bus": ["TRANSIT", "BUS"], "pedestrian": ["PED", "CLEARANCE"],
    "crossing": ["PED", "CLEARANCE"], "walk": ["PED", "CLEARANCE"],
    "incident": ["INCIDENT", "REROUTE"], "accident": ["INCIDENT", "REROUTE"],
    "sensor": ["DATA_", "MODE_"], "stale": ["DATA_", "MODE_"], "data": ["DATA_", "MODE_"],
    "reroute": ["REROUTE"], "route": ["REROUTE"],
    "denied": ["DENIED", "DEFERRED", "NOT_LATE", "NO_REFERENCE"],
    "refused": ["DENIED", "DEFERRED", "NOT_LATE"], "why": [],
}

SYSTEM_PROMPT = """You explain decisions of a simulated traffic-signal system to an incident-report reader.
Rules:
- Use ONLY the log entries provided. Cite every factual claim with its entry id, like [#412].
- Reason codes come with official plain-language meanings; use them.
- Never guess a cause the log does not state (e.g. A4 detects a pattern, not a crash).
- This is a simulation, not a real Tunis deployment. Do not claim lives saved.
- If the entries do not answer the question, reply exactly: ABSTAIN: <one sentence saying what is missing>.
Answer in at most 6 sentences, in the language of the question."""


ROUTINE = ("MAX_PRESSURE_SWITCH", "ACTUATED_GAP_OUT", "ACTUATED_MAX_OUT", "FIXED_CYCLE")


def select_entries(entries, question, limit=12):
    """Pick the log entries relevant to the question, most relevant first,
    returned in time order. Returns (entries, reason_if_empty)."""
    q = question.lower()
    # accept "ambulance 0", "fire truck 1", "police car 2", "bus L1 east 3" as well as the ids
    q = re.sub(r"fire\s*truck\s*(\d+)", r"fire\1", q)
    q = re.sub(r"police\s*car\s*(\d+)", r"police\1", q)
    q = re.sub(r"(ambulance|police|fire)\s+(\d+)", r"\1\2", q)
    q = re.sub(r"bus\s+(?:of\s+line\s+)?(l\d)[\s_]+(east|west|north|south)[\s_]+(\d+)", r"bus_\1_\2_\3", q)
    ids = {int(x) for x in re.findall(r"#(\d+)", q)}
    vehicles = set(re.findall(r"(ambulance\d+|police\d+|fire\d+|bus_\w+|ped\d+|veh\d+)", q))
    tls = {m.upper() for m in re.findall(r"\b([bf]\d)\b", q)}
    times = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*s\b", q)]
    codes = [c for k, cs in KEYWORDS.items() if k in q for c in cs]
    wants_routine = any(w in q for w in ("phase", "switch", "pressure", "cycle"))

    pool = entries
    if vehicles:
        pool = [e for e in entries if any(v in json.dumps(e["details"]).lower() for v in vehicles)]
        if not pool:
            known = sorted({e["details"]["vehicle"] for e in entries
                            if str(e["details"].get("vehicle", "")).startswith(("ambulance", "police", "fire"))})
            hint = (f". Emergency vehicles in this run so far: {', '.join(known)}" if known else
                    ". This run has no emergency vehicles yet (only the emergency and combined scenarios have them)")
            return [], f"no log entry mentions {', '.join(sorted(vehicles))}{hint}"
        if tls and not any(e.get("tls") in tls for e in pool):
            seen = sorted({e.get("tls") for e in pool if e.get("tls")})
            return [], (f"{', '.join(sorted(vehicles))} appears in the log only at "
                        f"{', '.join(seen) or 'no junction'}, not at {', '.join(sorted(tls))}")

    def score(e):
        s = 10 if e["id"] in ids else 0
        if vehicles:
            s += 6
        if e.get("tls") in tls:
            s += 2
        if any(c in e["reason"] for c in codes):
            s += 4
        if times and min(abs(e["t"] - t) for t in times) <= 60:
            s += 2
        if e["reason"] in ROUTINE and not wants_routine:
            s -= 5
        return s

    ranked = sorted(((score(e), e) for e in pool), key=lambda x: (-x[0], x[1]["id"]))
    best = [e for sc, e in ranked if sc >= 4][:limit]
    if not best:
        return [], "no log entry matches this question"
    return sorted(best, key=lambda e: e["id"]), None


def _format(e, narrator):
    return (f"[#{e['id']}] {narrator.describe(e)} (code {e['reason']}: {REASON_CODES[e['reason']]}; "
            f"details={json.dumps(e['details'])})")


def _llm(question, selected, model, narrator):
    return synapse_llm.chat(model or "explainer", SYSTEM_PROMPT,
                            "Log entries:\n" + "\n".join(_format(e, narrator) for e in selected)
                            + f"\n\nQuestion: {question}")[0]


def _template(question, selected, narrator, lang="en"):
    """Plain-language answer without a language model: one sentence per decision."""
    from collections import Counter
    who = Counter(narrator.vehicle(e["details"]["vehicle"]) for e in selected if e["details"].get("vehicle"))
    lines = []
    if len(selected) > 1:
        about = phrase(EXPLAIN, "about", lang, who=who.most_common(1)[0][0]) if len(who) == 1 else ""
        lines.append(phrase(EXPLAIN, "found", lang, n=len(selected), about=about))
    if lang != "en":
        lines.append(EXPLAIN["note"][lang])
    for e in selected[:10]:
        lines.append(f"- {narrator.describe(e)} [#{e['id']}]")
    if len(selected) > 10:
        lines.append(f"... +{len(selected) - 10}")
    return "\n".join(lines)


AGENT_SYSTEM = """You are Synapse, the explainer of a SIMULATED traffic control system for central Tunis.
Answer the question in {language}, in at most 6 sentences, using ONLY what the tools return.
Cite every factual claim with its log entry id like [#412]. Use search_log to find decisions
(try vehicle names like ambulance0, junction ids like B3, or topics like bus, crossing, incident, rain);
get_live_state for the current situation; get_results for experiment results.
Never guess a cause the log does not state. If the tools do not answer the question, reply exactly:
ABSTAIN: <one sentence saying what is missing, in {language}>."""

TOOLS = [
    {"name": "search_log", "description": "Search the decision log. Returns matching entries as plain sentences with their ids.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_live_state", "description": "Current simulation state: clock, junction modes and queues, incidents, congestion, weather.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_results", "description": "Experiment results (mean over seeds) for a persona measure, by scenario and controller.",
     "input_schema": {"type": "object", "properties": {"measure": {"type": "string",
                      "description": "e.g. car wait, pedestrian wait, clearance truncations, ambulance trip"}}}},
]


def explain(entries, question, engine="auto", model=None, narrator=None, lang="en", tools=None):
    """tools: optional {"get_live_state": fn, "get_results": fn(measure)} for the tool-using agent."""
    """Returns {"answer", "citations", "abstained", "engine"}."""
    narrator = narrator or Narrator()
    if lang not in LANG_NAMES:
        lang = "en"
    if (engine == "auto" and synapse_llm.available()) or engine == "agent":
        return _agent(entries, question, narrator, lang, tools or {}, model)
    selected, why_empty = select_entries(entries, question)
    if not selected:
        return {"answer": f"ABSTAIN: {why_empty}, so I cannot explain it without guessing.",
                "citations": [], "abstained": True, "engine": "none"}
    if engine == "auto":
        engine = "llm" if synapse_llm.available() else "template"
    if engine == "llm":
        answer = _llm(question, selected, model or os.environ.get("SYNAPSE_MODEL") or "explainer", narrator)
    else:
        answer = _template(question, selected, narrator, lang)

    if answer.startswith("ABSTAIN"):
        return {"answer": answer, "citations": [], "abstained": True, "engine": engine}
    cited = [int(x) for x in re.findall(r"\[#(\d+)\]", answer)]
    valid = {e["id"] for e in entries}
    if not cited or any(c not in valid for c in cited):
        return {"answer": "ABSTAIN: the draft explanation cited entries that are not in the "
                          "log (or none at all), so it was rejected.",
                "citations": [], "abstained": True, "engine": engine}
    return {"answer": answer, "citations": sorted(set(cited)), "abstained": False,
            "engine": engine}


class ExplainerAgent:
    """Wraps explain() for the analyst page. Not part of the control loop."""
    name = "explainer"

    def __init__(self, entries, narrator=None):
        self.entries, self.narrator = entries, narrator

    def ask(self, question, engine="auto", lang="en", tools=None):
        return explain(self.entries, question, engine, narrator=self.narrator, lang=lang, tools=tools)


def _agent(entries, question, narrator, lang, tools, model=None):
    """Tool-using Claude agent: it decides what to look up, then answers with checked citations."""
    import os
    from ...core import config
    model = model or os.environ.get("SYNAPSE_MODEL") or "explainer"

    def search_log(query):
        found, why = select_entries(entries, query, limit=15)
        return {"entries": [{"id": e["id"], "text": narrator.describe(e)} for e in found]} if found else {"none": why}

    handlers = {"search_log": search_log,
                "get_live_state": tools.get("get_live_state", lambda: {"error": "no live run"}),
                "get_results": tools.get("get_results", lambda measure="": {"error": "no results"})}
    try:
        answer, calls = synapse_llm.chat(model, AGENT_SYSTEM.format(language=LANG_NAMES[lang]), question,
                                         tools=TOOLS, handlers=handlers, max_tokens=900)
    except Exception as e:                       # API problem: fall back to templates
        out = explain(entries, question, engine="template", narrator=narrator, lang=lang)
        out["note"] = f"language model unavailable ({e.__class__.__name__}); template answer"
        return out
    if not answer or answer.startswith("ABSTAIN"):
        return {"answer": answer or "ABSTAIN", "citations": [], "abstained": True, "engine": "llm-agent",
                "tool_calls": calls}
    cited = [int(x) for x in re.findall(r"\[#(\d+)\]", answer)]
    valid = {e["id"] for e in entries}
    if any(c not in valid for c in cited):
        return {"answer": "ABSTAIN: the draft cited log entries that do not exist, so it was rejected.",
                "citations": [], "abstained": True, "engine": "llm-agent", "tool_calls": calls}
    return {"answer": answer, "citations": sorted(set(cited)), "abstained": False, "engine": "llm-agent",
            "tool_calls": calls}
