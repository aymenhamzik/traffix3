"""
Ask the explainer agent (Synapse) about a saved decision log.

  python scripts/ask.py results/logs/decisions_traffix_emergency_1.jsonl "Why did ambulance1 get green at F4?"
"""
import sys

import _path  # noqa: F401
from traffix.agents.network.explainer import ExplainerAgent
from traffix.core.decision_log import load

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    r = ExplainerAgent(load(sys.argv[1])).ask(" ".join(sys.argv[2:]))
    print(f"[{r['engine']}] {r['answer']}")
