import ast
import collections
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent

def cosine(a, b):
    return float(np.sum(a*b) / np.sqrt(np.sum(a*a)*np.sum(b*b)))

report = {}
elf = ROOT / 'extract-elf'
tree = ast.parse((elf/'official/test_outputs.py').read_text(encoding='utf-8'))
reference = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REF' for t in n.targets))
(elf/'reference-audit.js').write_text(reference.strip(),encoding='utf-8')
binary = elf/'hld/a.out'
ref = json.loads(subprocess.check_output(['node',str(elf/'reference-audit.js'),str(binary)]))
def compare(o):
    common = set(o)&set(ref)
    return {'output_keys':len(o),'reference_keys':len(ref),'overlap':len(common),'coverage':len(common)/len(ref),'wrong_values':sum(o[k]!=ref[k] for k in common)}
report['elf_provided_binary'] = {}
for arm in ['hld','recuris']:
    o=json.loads(subprocess.check_output(['node',str(elf/arm/'extract.js'),str(binary)]))
    report['elf_provided_binary'][arm]=compare(o)
    if arm=='hld':
        report['elf_provided_binary']['hld_only_remove_address_bias']=compare({str(int(k)-0x400000):v for k,v in o.items()})

if (elf/'replay-new.o').exists():
    binary=elf/'replay-new.o'
    ref=json.loads(subprocess.check_output(['node',str(elf/'reference-audit.js'),str(binary)]))
    report['elf_official_source_recompiled']={}
    for arm in ['hld','recuris']:
        o=json.loads(subprocess.check_output(['node',str(elf/arm/'extract.js'),str(binary)]))
        report['elf_official_source_recompiled'][arm]=compare(o)
        if arm=='hld':
            report['elf_official_source_recompiled']['hld_only_remove_address_bias']=compare({str(int(k)-0x400000):v for k,v in o.items()})

target=np.asarray(Image.open(ROOT/'path-tracing/hld/image.ppm'),dtype=np.float64)
report['path']={}
outputs={}
for arm in ['hld','recuris']:
    output=np.asarray(Image.open(ROOT/f'path-tracing/{arm}/reconstructed.ppm'),dtype=np.float64)
    outputs[arm]=output
    err=np.square(target-output)
    report['path'][arm]={'cosine':cosine(target,output),'squared_error_top_share':float(err[:900].sum()/err.sum()),'top_cosine':cosine(target[:900],output[:900]),'bottom_cosine':cosine(target[900:],output[900:])}
for name,top,bottom in [('hld_top_recuris_bottom','hld','recuris'),('recuris_top_hld_bottom','recuris','hld')]:
    report['path'][name]={'cosine':cosine(target,np.concatenate([outputs[top][:900],outputs[bottom][900:]])),'kind':'offline diagnostic array swap, not an experiment score'}

with (ROOT/'path-tracing/hld/image.ppm').open('rb') as f:
    tokens=f.read(300).split()
report['ppm_bug']={'header_tokens':[x.decode() for x in tokens[:4]],'correct_first_pixel':[int(x) for x in tokens[4:7]],'hld_cached_first_pixel':[int(x) for x in tokens[3:6]],'expected_channels':2400*1800*3,'wrong_skip':3,'correct_skip':4}

report['hld_mechanisms']={}
for task in ['extract-elf','path-tracing','log-summary-date-ranges']:
    root=ROOT/task/'hld'
    log=next((root/'agent/live/kz').glob('*.jsonl'))
    events=[json.loads(l) for l in log.read_text(encoding='utf-8').splitlines()]
    state=json.loads(next((root/'agent/live/kz').glob('*.json')).read_text(encoding='utf-8'))
    types=collections.Counter(e['event'] for e in events)
    roles=collections.Counter(e['role'] for e in events if e['event']=='request_completed')
    reviews=[{'line':i,'time':e['time'],'verdict':e['review'].get('verdict'),'reason':e['review'].get('reason')} for i,e in enumerate(events,1) if e['event']=='monitor_review']
    report['hld_mechanisms'][task]={'event_counts':dict(types),'request_roles':dict(roles),'monitor':reviews,'critic_errors':[{'line':i,'error':e.get('error')} for i,e in enumerate(events,1) if e['event']=='critic_unavailable'],'final_state_keys':list(state['state'])}

(ROOT/'replay-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='hld_mechanisms'},ensure_ascii=False,indent=2))
for task,s in report['hld_mechanisms'].items():
    print(task,'roles',s['request_roles'],'monitors',collections.Counter(x['verdict'] for x in s['monitor']),'statekeys',s['final_state_keys'])
