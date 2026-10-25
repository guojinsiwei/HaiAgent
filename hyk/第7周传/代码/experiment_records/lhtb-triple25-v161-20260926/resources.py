"""Conservative slot reservation; task limits are never reduced for concurrency."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Demand:
    cpu: float
    memory_mb: int

def demand(task):
    e = task['environment']
    # Original scorer container + one active candidate. Verification runs only
    # after the candidate stops. Mirrors/images additionally need disk reserves.
    return Demand(2 * e['cpus'], 2 * e['memory_mb'])

def fits(tasks, cpu_cap=12, memory_cap_mb=28 * 1024, max_slots=3):
    costs = [demand(t) for t in tasks]
    return (len(tasks) <= max_slots and sum(c.cpu for c in costs) <= cpu_cap
            and sum(c.memory_mb for c in costs) <= memory_cap_mb)
