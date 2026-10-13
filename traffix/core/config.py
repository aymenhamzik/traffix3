"""Loads the YAML files in config/. Every assumption lives there, not in code."""
import os
from functools import lru_cache

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def path(*parts):
    return os.path.join(ROOT, *parts)


@lru_cache(maxsize=None)
def load(name):
    with open(path("config", f"{name}.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def simulation():
    return load("simulation")


def agents():
    return load("agents")


def scenarios():
    return load("scenarios")


def calendar():
    return load("calendar")


def network_files():
    name = os.environ.get("TRAFFIX_NETWORK", simulation()["network"])
    return (path("data", "networks", f"{name}.net.xml"),
            path("data", "networks", f"{name}_actuated.net.xml"))
