"""Record task.yaml entry points and native algorithm settings before sealing."""
import json
from common import ROOT,save

assert not any(ROOT.glob('health-*.json'))
protocol=json.loads((ROOT/'protocol.json').read_text())
for row in protocol['tasks']:
    lines=(ROOT/'upstream/tasks_long_cli'/row['task']/'task.yaml').read_text(encoding='utf-8').splitlines()
    start=lines.index('instruction: |-')+1
    instruction=[]
    for line in lines[start:]:
        if line and not line.startswith('  '): break
        instruction.append(line[2:] if line.startswith('  ') else line)
    row['instruction']='\n'.join(instruction).rstrip()
    assert row['instruction'] and len(row['instruction'])<10000
protocol.update(endpoint='https://api.deepseek.com',response_protocol='json_object_both_arms',
    context_windows={'bestfgs-v6.1':'48000 characters, native budgeted dialogue and memory',
                     'raw':'48000 UTF-8 bytes, native sequential dialogue; no memory'},
    role_output_tokens={'action':4096,'advisor':1536,'monitor':1536},
    role_wire_attempts={'action':2,'advisor':2,'monitor':1},
    output_bytes=24000,task_entry='Unmodified task.yaml instruction; full INSTRUCTION.md available on disk',
    assignment='Same ten tasks, cross-over: each worker five v6.1 and five RAW',
    grading_resources={'concurrency':2,'cpu_each':8,'memory_gib_each':8,'disk_reserve_gib':100,
                       'note':'Independent grading needs enough compile capacity to honor unchanged official test timeouts; both arms use identical settings.'},
    generation_resources={'cpu_affinity_each':2,'address_space_gib_per_process':3,'host_container_memory_bytes':16000000000},
    known_upstream_defects=[{'task':'cs61_fa24_cats','kind':'starter_p2p_missing_file',
        'detail':'Unmodified official P2P requests READMD.md, absent from the pinned starter; 18/19 pass before solving. Keep raw official scores; do not attribute this pre-existing failure to a solver.'}])
save(ROOT/'protocol.json',protocol)
print(json.dumps(dict(tasks=len(protocol['tasks']),sealed=False,model_calls=0)))
