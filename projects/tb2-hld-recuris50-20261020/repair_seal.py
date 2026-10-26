"""Seal deployed controller only after the two real payments checks pass."""
import hashlib,json
from pathlib import Path
import seal
R=Path(__file__).resolve().parent

def main():
    a=json.loads((R/'repair-v1/acceptance.json').read_text())
    if not a.get('passed') or a.get('paid_calls')!=0 or len(a.get('checks',[]))!=2:
        raise RuntimeError('Both ordinary and stopped-main acceptance checks required')
    seal.main()
    ready=json.loads((R/'ready.json').read_text())
    ready.update(repair_acceptance='repair-v1/acceptance.json',repair='payments-stopped-container-and-budget-classification',
        original_ready_sha256=hashlib.sha256((R/'repair-v1/original/ready.json').read_bytes()).hexdigest())
    (R/'ready.json').write_text(json.dumps(ready,indent=2))
    (R/'repair-v1/deployed-manifest.json').write_text(json.dumps(ready,indent=2))
if __name__=='__main__':main()
