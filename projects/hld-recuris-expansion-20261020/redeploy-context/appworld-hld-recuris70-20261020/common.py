"""Compatibility helpers for the reused, audited proxy and progress readers."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
def save(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(value));t.replace(p)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def import_tree(*args,**kwargs):raise RuntimeError('Legacy workspace restoration is disabled for AppWorld')
def export_tree(*args,**kwargs):raise RuntimeError('Legacy source export is disabled for AppWorld')
