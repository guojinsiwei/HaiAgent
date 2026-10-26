"""Freeze selection before any solver outcomes: deterministic CPU-only sample."""
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parent
def main():
    inventory=json.loads((ROOT/'inventory.json').read_text(encoding='utf-8'))
    eligible=sorted([r for r in inventory['tasks'] if not r['environment'].get('gpus',0)],key=lambda r:r['name'])
    selected=random.Random(20261013).sample(eligible,30)
    result=dict(commit=inventory['commit'],seed=20261013,selection='Python Random.sample from sorted CPU-only names, frozen before outcomes',
        population=len(inventory['tasks']),eligible=len(eligible),excluded_gpu=[r['name'] for r in inventory['tasks'] if r['environment'].get('gpus',0)],
        tasks=[dict(name=r['name'],category=r['metadata']['category'],environment=r['environment'],agent=r['agent'],verifier=r['verifier']) for r in selected])
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    target=ROOT/'tasks.json'
    if target.exists() and target.read_text(encoding='utf-8')!=text:raise RuntimeError('Refuse to alter sealed task selection')
    target.write_text(text,encoding='utf-8')
    print(json.dumps(dict(tasks=[r['name'] for r in selected],sha256=hashlib.sha256(text.encode()).hexdigest())))
if __name__=='__main__':main()
