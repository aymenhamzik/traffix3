"""
Proves the architecture rules hold in the code:
  1. Only traffix/simulation/executor.py changes a traffic light,
     and only orchestration/ (the masters) calls the executor's request().
  2. Agents never import the simulation backend, the executor or the world.
  3. The Synapse layer (explainer, alert writer, operator copilot) has no path to the simulation.
  4. The calendar assumptions are hidden from agents: no agent imports the calendar model.

  python scripts/check_architecture.py
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIGHT_WRITES = {"setRedYellowGreenState", "setPhase", "setPhaseDuration", "setProgram",
                "setProgramLogic", "setCompleteRedYellowGreenDefinition"}
AGENT_FORBIDDEN = {"backend", "traci", "libsumo", "executor", "world", "calendar_model"}
EXPLAINER_FORBIDDEN = AGENT_FORBIDDEN | {"sensors", "orchestration", "master", "supermaster"}


def names(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[-1] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out |= {(n.module or "").split(".")[-1]} | {a.name for a in n.names}
    return out


fails = []
for path in sorted((ROOT / "traffix").rglob("*.py")):
    rel = path.relative_to(ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    writes = [n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in LIGHT_WRITES]
    if writes and rel != "traffix/simulation/executor.py":
        fails.append(f"{rel} writes a traffic light: {writes}")
    calls_request = any(isinstance(n, ast.Attribute) and n.attr == "request" and
                        isinstance(n.value, ast.Attribute) and n.value.attr in ("ex", "executor")
                        for n in ast.walk(tree))
    if calls_request and not rel.startswith("traffix/orchestration/"):
        fails.append(f"{rel} calls the executor; only masters may")
    if rel.startswith("traffix/agents/") and names(tree) & AGENT_FORBIDDEN:
        fails.append(f"{rel} imports {sorted(names(tree) & AGENT_FORBIDDEN)}")
    if (rel == "traffix/agents/network/explainer.py" or rel.startswith("traffix/synapse/")) \
            and names(tree) & EXPLAINER_FORBIDDEN:
        fails.append(f"{rel} imports {sorted(names(tree) & EXPLAINER_FORBIDDEN)}")

if fails:
    print("ARCHITECTURE CHECK FAILED")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("Architecture check passed:")
print("  - only the executor writes lights, and only masters call it")
print("  - agents have no access to the simulation backend, executor or world")
print("  - agents never see the calendar assumptions")
print("  - the Synapse layer (explainer, alert writer, copilot) has no path to the simulation")
