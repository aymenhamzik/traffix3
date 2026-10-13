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
import urllib.request

from ...core.decision_log import REASON_CODES
from ...core.narrate import Narrator

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
    body = json.dumps({
        "model": model, "max_tokens": 600, "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content":
                      "Log entries:\n" + "\n".join(_format(e, narrator) for e in selected)
                      + f"\n\nQuestion: {question}"}]}).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                 "x-api-key": os.environ["ANTHROPIC_API_KEY"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return "".join(b.get("text", "") for b in data["content"]).strip()


def _template(question, selected, narrator):
    """Plain-language answer without a language model: one sentence per decision."""
    from collections import Counter
    who = Counter(narrator.vehicle(e["details"]["vehicle"]) for e in selected if e["details"].get("vehicle"))
    lines = []
    if len(selected) > 1:
        about = f" about {who.most_common(1)[0][0]}" if len(who) == 1 else ""
        lines.append(f"I found {len(selected)} decisions{about}:")
    for e in selected[:10]:
        lines.append(f"- {narrator.describe(e)} [#{e['id']}]")
    if len(selected) > 10:
        lines.append(f"... and {len(selected) - 10} more.")
    return "\n".join(lines)


def explain(entries, question, engine="auto", model=None, narrator=None):
    """Returns {"answer", "citations", "abstained", "engine"}."""
    narrator = narrator or Narrator()
    selected, why_empty = select_entries(entries, question)
    if not selected:
        return {"answer": f"ABSTAIN: {why_empty}, so I cannot explain it without guessing.",
                "citations": [], "abstained": True, "engine": "none"}
    if engine == "auto":
        engine = "llm" if os.environ.get("ANTHROPIC_API_KEY") else "template"
    if engine == "llm":
        model = model or os.environ.get("SYNAPSE_MODEL", "claude-sonnet-5-5")
        answer = _llm(question, selected, model, narrator)
    else:
        answer = _template(question, selected, narrator)

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

    def ask(self, question, engine="auto"):
        return explain(self.entries, question, engine, narrator=self.narrator)
