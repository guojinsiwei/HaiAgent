"""Prepare a source snapshot; does not change sources or launch experiments."""
from pathlib import Path
import os, re, json, hashlib, tarfile, io
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
EXCLUDED = {'.git','node_modules','.venv','venv','__pycache__','.pytest_cache',
    'test-deps','handoff-test-local','jobs','grades','runs','outputs','logs','audit',
    'evidence','validation','acceptance-jobs','preflight','incoming','host-tmp',
    'backups','dist','build','.cache','data','datasets','public-data','assets',
    'screenshots','downloads','cache','tmp','server-migration-20261023'}
EXT = {'.py','.mjs','.cjs','.js','.ts','.tsx','.jsx','.json','.yaml','.yml',
    '.toml','.ini','.cfg','.sh','.ps1','.txt','.md','.sql','.html','.css','.patch'}
SECRET = re.compile(rb'(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{25,}|-----BEGIN (?:OPENSSH|RSA|EC|DSA)? ?PRIVATE KEY-----)')
NAME_SECRET = re.compile(r'(?:credential|secret|\.private\.|\.env(?:\.|$)|id_rsa|id_ed25519)', re.I)
roots = [ROOT/'projects', ROOT/'components/recuris-handoff-20261007',
    ROOT/'experiment_records/longcli-recuris-frozen-small20-20261007',
    ROOT/'experiment_records/longcli-recuris-large20-20261009']
files=[]; skips=Counter(); groups=Counter()
archive=OUT/'project-code-20261023.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=3) as tf:
    for base in roots:
        for current, dirs, names in os.walk(base,followlinks=False):
            dirs[:]=sorted(d for d in dirs if d not in EXCLUDED and not d.startswith('.test') and not Path(current,d).is_symlink())
            for name in sorted(names):
                p=Path(current,name)
                if p.is_symlink() or NAME_SECRET.search(name): skips['credential_name_or_symlink']+=1;continue
                if p.suffix.lower() not in EXT and not name.startswith(('Dockerfile','LICENSE','Makefile')):continue
                try:
                    if p.stat().st_size>2_000_000:skips['large_file']+=1;continue
                    raw=p.read_bytes()
                except OSError:skips['unreadable']+=1;continue
                if SECRET.search(raw):skips['credential_pattern']+=1;continue
                rel=p.relative_to(ROOT).as_posix()
                info=tarfile.TarInfo('mcts-code/'+rel);info.size=len(raw);info.mtime=int(p.stat().st_mtime)
                info.mode=0o700 if p.suffix in {'.sh','.py'} else 0o600
                tf.addfile(info,io.BytesIO(raw))
                files.append({'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
                groups['/'.join(p.relative_to(ROOT).parts[:2])]+=1
    manifest={'kind':'source_snapshot_not_runtime_installation','files':files,'groups':dict(groups),
        'excluded_counts':dict(skips),'excluded_directories':sorted(EXCLUDED),
        'source_root':str(ROOT),'experiments_started':False}
    raw=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
    info=tarfile.TarInfo('mcts-code/MIGRATION-MANIFEST.json');info.size=len(raw);info.mode=0o600
    tf.addfile(info,io.BytesIO(raw))
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
summary={'files':len(files),'groups':len(groups),'source_bytes':sum(f['bytes'] for f in files),
    'archive_bytes':archive.stat().st_size,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
    'skipped':dict(skips),'uploaded':False}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary))
