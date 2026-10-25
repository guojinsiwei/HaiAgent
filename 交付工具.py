"""Verify, assemble, and export weekly source deliveries using Python stdlib."""
from pathlib import Path, PurePosixPath
from concurrent.futures import ThreadPoolExecutor
import argparse, hashlib, json, sys, zipfile

ROOT=Path(__file__).resolve().parent

def digest(data):return hashlib.sha256(data).hexdigest()

def safe_relative(s):
    p=PurePosixPath(s)
    if p.is_absolute() or '..' in p.parts or not p.parts or ':' in s or '\\' in s:
        raise ValueError('Unsafe manifest path')
    return p

def load_rows():
    p=ROOT/'文件清单.json'
    if p.exists():rows=json.loads(p.read_text(encoding='utf-8'))['files']
    else:
        rows=[]
        for p in sorted(ROOT.glob('*/第*周传/文件清单.json')):
            rows.extend(json.loads(p.read_text(encoding='utf-8'))['files'])
    if not rows:raise ValueError('No manifest found')
    for r in rows:
        safe_relative(r['source']);safe_relative(r['target'])
        if r['owner'] not in {'lzh','hyk','lty'} or r['week'] not in range(6,10):raise ValueError('Invalid owner/week')
    if len({r['source'] for r in rows})!=len(rows) or len({r['target'] for r in rows})!=len(rows):raise ValueError('Duplicate mappings')
    return rows

def read_checked(r):
    data=(ROOT/r['target']).read_bytes()
    if len(data)!=r['bytes'] or digest(data)!=r['sha256']:raise ValueError('Checksum mismatch: '+r['target'])
    return data

def verify(rows):
    def check(r):read_checked(r);return r['bytes']
    total=0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,size in enumerate(pool.map(check,rows),1):
            total+=size
            if i%10000==0:print(f'Checked {i}/{len(rows)}',flush=True)
    result={'passed':True,'files':len(rows),'bytes':total,'unique_sources':len({r['source'] for r in rows}),'unique_targets':len({r['target'] for r in rows}),'review_flag_files':sum(bool(r['review_flags']) for r in rows)}
    (ROOT/'核对结果.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))

def new_output(value):
    p=Path(value).resolve()
    if p.exists():raise ValueError('Output exists; use a new path')
    p.parent.mkdir(parents=True,exist_ok=True)
    return p

def assemble(rows,args):
    chosen=[r for r in rows if r['week']<=args.through_week]
    out=new_output(args.output)
    if args.zip:
        with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
            for r in chosen:z.writestr(r['source'],read_checked(r))
        with zipfile.ZipFile(out) as z:
            assert len(z.namelist())==len(chosen)
            for r in chosen:
                if digest(z.read(r['source']))!=r['sha256']:raise ValueError('Archive verification failed')
    else:
        out.mkdir()
        for r in chosen:
            p=out/r['source'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(read_checked(r))
    print(json.dumps({'assembled_files':len(chosen),'through_week':args.through_week,'output':str(out),'archive_readback_verified':args.zip},ensure_ascii=True))

def export_week(rows,args):
    chosen=[r for r in rows if r['week']==args.week]
    blocked=[r for r in chosen if r['review_flags']]
    if blocked:raise ValueError(f'{len(blocked)} files need credential review; see 公开上传前待核对.json. This command will not export them automatically.')
    # Export is local only. It never calls GitHub, git, model APIs or experiment scripts.
    out=new_output(args.output)
    with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for r in chosen:z.writestr(r['target'],read_checked(r))
        for owner in ('lzh','hyk','lty'):
            for name in ('本周说明.md','文件清单.json'):
                p=ROOT/owner/f'第{args.week}周传'/name
                z.writestr(p.relative_to(ROOT).as_posix(),p.read_bytes())
        for name in ('README.md','四周安排.md','交付工具.py','.gitignore'):
            p=ROOT/name;z.writestr(name,p.read_bytes())
    print(json.dumps({'week':args.week,'files':len(chosen),'output':str(out),'uploaded':False},ensure_ascii=True))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    s=p.add_subparsers(dest='command',required=True)
    s.add_parser('verify')
    a=s.add_parser('assemble');a.add_argument('--through-week',type=int,choices=range(6,10),default=9);a.add_argument('--output',required=True);a.add_argument('--zip',action='store_true')
    e=s.add_parser('export');e.add_argument('--week',type=int,choices=range(6,10),required=True);e.add_argument('--output',required=True)
    args=p.parse_args();rows=load_rows()
    if args.command=='verify':verify(rows)
    elif args.command=='assemble':assemble(rows,args)
    else:export_week(rows,args)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,AssertionError) as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
