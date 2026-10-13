"""The fixed priority order every master applies. A policy choice, never learned."""
from . import config

ORDER = config.agents()["priority_order"]


def rank(level):
    return ORDER.index(level)
