"""Generate source hashes and record completed zero-API acceptance."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = ROOT/'sources/bestfgs-project/src/bestfgs'
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.glob('*.py'))}
manifest = dict(release='DH-v9-recovery-repair', date='2026-10-07',
    base='experiment_records/longcli-dh-large20-20261007',
    route_search=False, contrastive_predictions=False, rejection_recovery_limit=7,
    hashes=hashes, paid_experiment_started=False)
(ROOT/'dh-source-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n',encoding='utf-8')
acceptance = dict(candidate='DH-v9-recovery-repair', source_hashes=hashes,
    model_api_calls=0, live_experiments_modified=False,
    local_suite=dict(tests=144, passed=143, skipped=1, failed=0),
    linux_suite=dict(tests=144, passed=144, skipped=0, failed=0,
        directory='/var/tmp/lizh639-dh-recovery-acceptance-20261007-fpfhdq4u'),
    supplementary_legacy_suite=dict(tests=33, passed=28, failed=5,
        baseline_failed=5, same_failure_names_and_assertions=True,
        note='All five also fail on frozen v9; not changed within this scoped repair.'),
    accepted_behaviors=['seven_rejections_advisor_seven_rejections_preserve_and_exit',
        'mixed_gates_share_counter', 'no_reset_for_listing_or_unrelated_edit',
        'related_edits_and_new_evidence_reset', 'role_and_total_budgets_preserved',
        'real_linux_import_failure_source_edit_same_test',
        'line_and_qualified_symbol_diagnostics', 'cached_diagnostic_no_recursive_episode'])
(ROOT/'evidence/recovery-repair-acceptance.json').write_text(json.dumps(acceptance,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(release=manifest['release'],modules=len(hashes),acceptance_recorded=True)))
