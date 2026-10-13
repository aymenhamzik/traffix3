"""
The message bus: the only way agents, masters and the supermaster talk.

  Request      junction agent -> its master    ("green for link 7, ambulance")
  Proposal     traffic light agent -> master   ("switch to phase 2")
  Directive    supermaster -> master           ("ambulance at B3 in 30 s")
  Publication  network-wide facts              ("lane X stale", "incident on edge Y")
  Status       master -> neighbours, supermaster (queues, exit full, mode)
  Notification supermaster -> persona pages
"""
from dataclasses import dataclass, field
from itertools import count

_ids = count(1)


@dataclass
class Message:
    source: str
    kind: str
    target: str            # junction id, "supermaster" or a persona
    t: float
    expiry: float
    subject: str = ""
    link_index: int = -1
    details: dict = field(default_factory=dict)
    id: int = field(default_factory=lambda: next(_ids))


class MessageBus:
    def __init__(self):
        self._msgs = {}                 # key -> Message (posting again refreshes it)
        self.status = {}                # junction -> latest master status
        self.publications = {}          # (kind, subject) -> Message
        self.notifications = []         # dicts for the persona pages
        self.forecast = {}              # demand forecast from the supermaster

    def post(self, msg):
        key = (msg.source, msg.kind, msg.target, msg.subject)
        old = self._msgs.get(key)
        if old:
            msg.id = old.id
        self._msgs[key] = msg
        return msg

    def inbox(self, target, now, kind=None):
        return [m for m in self._msgs.values()
                if m.target == target and m.expiry >= now and (kind is None or m.kind == kind)]

    def publish(self, msg):
        self.publications[(msg.kind, msg.subject)] = msg

    def unpublish(self, kind, subject):
        self.publications.pop((kind, subject), None)

    def published(self, kind):
        return [m for (k, _), m in self.publications.items() if k == kind]

    def is_published(self, kind, subject):
        return (kind, subject) in self.publications

    def prune(self, now):
        self._msgs = {k: m for k, m in self._msgs.items() if m.expiry >= now}
