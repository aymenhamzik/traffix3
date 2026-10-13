"""Quick tests:  python -m pytest tests   (or python tests/test_core.py)"""
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from traffix.core.decision_log import DecisionLog  # noqa: E402
from traffix.demand import hijri  # noqa: E402
from traffix.demand.calendar_model import CalendarModel  # noqa: E402


def test_ramadan_2026_dates():
    assert hijri.info(datetime(2026, 2, 18).date())["ramadan"]
    assert hijri.info(datetime(2026, 3, 20).date())["eid_al_fitr"]
    assert not hijri.info(datetime(2026, 4, 15).date())["ramadan"]


def test_calendar_layers():
    c = CalendarModel()
    sept, _, _ = c.level(datetime(2026, 9, 14, 8, 0))
    aug_sat, _, _ = c.level(datetime(2026, 8, 15, 8, 0))
    assert abs(sept - 1.15) < 1e-6
    assert aug_sat < 0.6 * sept
    _, morning_share, _ = c.level(datetime(2026, 10, 13, 8, 0))
    _, evening_share, _ = c.level(datetime(2026, 10, 13, 17, 0))
    assert morning_share > 0.6 > 0.4 > evening_share


def test_decisions_need_reason_codes():
    log = DecisionLog()
    log.log(1, "master@B1", "switch", "MAX_PRESSURE_SWITCH", tls="B1")
    try:
        log.log(2, "master@B1", "switch", "MADE_UP_REASON")
        assert False, "unknown reason code accepted"
    except ValueError:
        pass


def test_architecture():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, os.path.join(root, "scripts", "check_architecture.py")])
    assert r.returncode == 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
