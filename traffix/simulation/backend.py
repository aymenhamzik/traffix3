"""
How Python talks to SUMO. Only simulation/sensors.py (read), simulation/executor.py (write lights),
simulation/world.py (scenario events) and evaluation/monitor.py may import this.
check_architecture.py enforces that rule.

libsumo runs SUMO inside Python (fast); traci uses a socket and is needed
for the GUI. Both expose the same functions.
"""
import sys

if "--gui" in sys.argv:
    import traci
else:
    try:
        import libsumo as traci
    except ImportError:
        import traci
