"""Checkpoint candidate selection without benchmark-runtime imports."""
import json


def budget_candidate(state, checkpoint):
    """Use the recorded choice only when it names an intact owned snapshot."""
    if checkpoint.exists():
        data = json.loads(checkpoint.read_text())
        location = data.get('best_workspace')
        for record in state.snapshots.values():
            if record['snapshot'].location == location:
                return record['snapshot']
        raise RuntimeError('Checkpoint candidate is not an owned snapshot')
    return state.initial
