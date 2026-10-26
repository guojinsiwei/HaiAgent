from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parent
def main():
 a=json.loads((R/'acceptance.json').read_text());assert a['passed'] and len(a['checks'])==2
 files={}
 for p in R.iterdir():
  if p.is_file() and (p.suffix in ['.py','.mjs'] or p.name in ['tasks.json','protocol.json','experiment.json','budget-profile.json','runtime-final.tar.gz','python-runtime.tar.gz']):
   with p.open('rb') as stream:files[p.name]=hashlib.file_digest(stream,'sha256').hexdigest()
 (R/'ready.json').write_text(json.dumps({'passed':True,'files':files,'paid_calls':0,'acceptance':'Both real production entries stopped at budget gate; both completed original separate TB4 grading'},indent=2))
 print('SEALED',len(files))
if __name__=='__main__':main()
