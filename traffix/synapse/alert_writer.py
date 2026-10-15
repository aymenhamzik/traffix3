"""
Alert writer (Synapse layer). Every notification already carries built-in English,
French and Arabic texts. With an API key, this agent asks Claude to rewrite each new
alert for its persona (short and urgent for drivers, plain for pedestrians, precise for
the operator) in the three languages, in batches. A rewrite is accepted only if it keeps
every number of the original; otherwise the built-in text stays. It reads notifications
and writes text only.
"""
import json
import re
import threading
import time

from ..core import config
from . import llm
from .i18n import LANGS

SYSTEM = """You rewrite traffic alerts for the people who receive them in central Tunis.
For each alert you get the persona and the original English text. Return ONLY a JSON object
mapping each alert id to {"en": ..., "fr": ..., "ar": ...}.
Rules: keep every fact and every number exactly (write numbers with digits 0-9, also in Arabic);
add no information; at most 22 words; tone by persona: car_driver and bus_driver = short and
direct, pedestrian = simple and reassuring, bus_passenger = what it means for their wait,
emergency_crew = operational, operator and analyst = precise. Arabic: Modern Standard Arabic."""


def numbers(text):
    return set(re.findall(r"\d+(?:\.\d+)?", text or ""))


class AlertWriter:
    def __init__(self, live):
        self.live = live
        c = config.agents()["synapse"]
        self.model, self.every = "alert", c["alert_batch_every"]
        self.done, self.running, self.stats = set(), False, {"rewritten": 0, "rejected": 0}

    def start(self):
        if llm.available():
            self.running = True
            threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            time.sleep(self.every)
            try:
                self.rewrite_batch()
            except Exception as e:                     # never break the live run
                print(f"[Synapse alert writer] {e.__class__.__name__}: {e}")

    def rewrite_batch(self, limit=12):
        system = getattr(self.live, "system", None)
        if system is None:
            return
        todo = [n for n in list(system.bus.notifications) if n.get("id") not in self.done][-limit:]
        if not todo:
            return
        payload = [{"id": n["id"], "persona": n["persona"], "text": n["text"]} for n in todo]
        reply, _ = llm.chat(self.model, SYSTEM, json.dumps(payload, ensure_ascii=False), max_tokens=2500)
        out = llm.extract_json(reply) or {}
        for n in todo:
            self.done.add(n["id"])
            r = out.get(str(n["id"])) or out.get(n["id"])
            if isinstance(r, dict) and all(isinstance(r.get(l), str) and r[l] for l in LANGS) \
                    and all(numbers(n["text"]) <= numbers(r[l]) for l in LANGS):
                n["texts_llm"] = {l: r[l] for l in LANGS}
                self.stats["rewritten"] += 1
            else:
                self.stats["rejected"] += 1
