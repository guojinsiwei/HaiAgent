"""Deterministic paired selection and atomic metadata; no outcome filtering."""
import json
import os
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
COMMIT='d78f5eb52ad754c5ee9154741af73130a85a65b8'

def write(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
    temporary.replace(path)

def reserve():
    if os.environ.get('LHTB_DISABLE_DISK_GUARD') == '1':
        return
    if min(shutil.disk_usage(p).free for p in ('/var/lib/docker',str(HERE))) < 60*2**30:
        raise RuntimeError('Disk reserve under 60 GiB; no data deleted')

def select(original):
    if len(original['tasks']) != 12:
        raise ValueError('Expected the pre-existing twelve-task manifest')
    return dict(original,tasks=original['tasks'][:8],methods=['v6','v7'],total_trials=16,
        status='authorized_paired8_pending_preflight_and_credential',
        selection_rule='First eight in the prior fixed seeded order; same eight in both arms; no outcome filtering.',
        source_release={'v6':'monitor-control-v6','v7':'route-selection-v7'},prior_results_carried=0,
        arm_order='Within each task, v6/v7 order alternates by original task index; two global slots.')
