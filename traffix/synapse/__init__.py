"""
The Synapse layer: language agents that READ the system and WRITE text, never lights.

  explainer     answers "why?" questions from the decision log (agents/network/explainer.py)
  alert_writer  every notification in Arabic, French and English, adapted to its persona
  copilot       situation summaries, suggested actions and incident reports for the operator

Without an Anthropic API key every agent falls back to built-in templates, so the
project runs offline. With a key, Claude writes the text, but only from data the
system provides, and outputs are checked (citations exist, numbers unchanged).
scripts/check_architecture.py proves this package has no path to the simulation.
"""
