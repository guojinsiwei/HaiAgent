"""Host-side recovery: exclude a recorded pause without resetting task usage."""
import copy
import math


def exclude_pause(checkpoint, stopped_ms, resumed_ms, receipt_id):
    if not all(isinstance(x, (int, float)) and math.isfinite(x)
               for x in (stopped_ms, resumed_ms)) or resumed_ms < stopped_ms:
        raise ValueError("Invalid host pause interval")
    result = copy.deepcopy(checkpoint)
    full = result["full"]
    history = full.setdefault("hostPauseAdjustments", [])
    previous = next((x for x in history if x["id"] == receipt_id), None)
    receipt = dict(id=receipt_id, stopped_ms=stopped_ms, resumed_ms=resumed_ms)
    if previous:
        if previous != receipt:
            raise ValueError("Conflicting pause receipt")
        return result
    if history and stopped_ms < history[-1]["resumed_ms"]:
        raise ValueError("Overlapping pause intervals")
    started = full["startedAt"]
    if not isinstance(started, (int, float)) or not math.isfinite(started) or started > stopped_ms:
        raise ValueError("Pause precedes task clock")
    full["startedAt"] = started + resumed_ms - stopped_ms
    history.append(receipt)
    return result
