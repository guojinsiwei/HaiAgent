"""No-tools deadline fallback: deliver only a content-bound owned checkpoint."""
import hashlib
import json
from pathlib import Path
from bestfgs.environment import _tree_manifest, _manifest_fingerprint


def budget_candidate(state, checkpoint):
    if not checkpoint.exists():
        return state.initial
    data = json.loads(checkpoint.read_text(encoding='utf-8'))
    location = data.get('best_workspace')
    expected = data.get('best_snapshot_fingerprint')
    for record in state.snapshots.values():
        snapshot = record['snapshot']
        if snapshot.location != location:
            continue
        if not expected or expected != snapshot.fingerprint:
            raise RuntimeError('Checkpoint lacks matching candidate fingerprint')
        manifest = _tree_manifest(Path(location))
        actual = hashlib.sha256(json.dumps([_manifest_fingerprint(manifest), record['external']],
                                          sort_keys=True).encode()).hexdigest()
        if actual != expected or manifest != record['manifest']:
            raise RuntimeError('Checkpoint candidate changed after validation')
        status = data.get('delivery') or {}
        if status.get('validation_status') == 'failed' and status.get('local_validation_passed'):
            raise RuntimeError('Contradictory checkpoint validation state')
        return snapshot
    raise RuntimeError('Checkpoint candidate is not an owned snapshot')
