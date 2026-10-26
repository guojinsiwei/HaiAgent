"""Bounded, read-only source excerpts around observed lines and symbols."""
import json
import re

SOURCE_SUFFIXES = ('.py', '.c', '.h', '.cc', '.cpp', '.hpp', '.rs', '.go', '.js', '.ts', '.json', '.toml', '.yaml', '.yml', '.cfg', '.ini', '.sh')


def diagnostic_plan(anchors):
    files, symbols, locations = [], [], []
    for anchor in anchors:
        observation = anchor.get('observation', '')
        for name in anchor.get('dependencies', {}):
            if name.endswith(SOURCE_SUFFIXES) or name.rsplit('/', 1)[-1] in ('Makefile', 'CMakeLists.txt'):
                files.append(name)
            elif re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+', name):
                symbols.append(name)
        for path, line in re.findall(r'File ["\']([^"\']+)["\'], line (\d+)', observation):
            files.append(path)
            locations.append(dict(path=path, line=int(line)))
        for path, line in re.findall(r'([\w./-]+\.(?:py|c|h|cc|cpp|rs|go|js|ts)):(\d+)', observation):
            files.append(path)
            locations.append(dict(path=path, line=int(line)))
        for symbol in re.findall(r'\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b', observation):
            if not symbol.endswith(SOURCE_SUFFIXES):
                symbols.append(symbol)
        symbols.extend(re.findall(r'(?:in function|in|undefined reference to)\s+[\'`"]?([A-Za-z_]\w*)', observation))
    return dict(files=list(dict.fromkeys(files))[:8], symbols=list(dict.fromkeys(symbols))[:6],
                locations=locations[:6])


# Executed inside the task sandbox and charged as an ordinary tool call.
# Inputs are data on stdin, never interpolated into Python source.
DIAGNOSTIC_SCRIPT = r'''
import ast,json,os,pathlib,re,sys
plan=json.load(sys.stdin);root=pathlib.Path.cwd().resolve()
files=[];read_bytes=0;excerpts=[];scanned=0;content_cache={}
suffixes={'.py','.c','.h','.cc','.cpp','.hpp','.rs','.go','.js','.ts','.json','.toml','.yaml','.yml','.cfg','.ini','.sh'}
def safe(name):
    if name.startswith('/app/'):name=name[5:]
    p=(root/name).resolve()
    return p if p.is_relative_to(root) and p.is_file() and not p.is_symlink() else None
def lines(p):
    global read_bytes
    if p in content_cache:return content_cache[p]
    if p.stat().st_size>1048576 or read_bytes+p.stat().st_size>4194304:return []
    data=p.read_bytes();read_bytes+=len(data)
    if b'\x00' in data:return []
    value=data.decode('utf-8','replace').splitlines();content_cache[p]=value
    return value
def emit(p,number,why):
    if len(excerpts)>=6:return
    data=lines(p)
    if not data:return
    start=max(0,number-5);end=min(len(data),number+9)
    key=(p.relative_to(root).as_posix(),start)
    if any((v['path'],v['start_line']-1)==key for v in excerpts):return
    excerpts.append(dict(path=key[0],start_line=start+1,reason=why,
        text='\n'.join(str(i+1)+': '+data[i][:200] for i in range(start,end))[:1800]))
def symbols(p,wanted):
    data=lines(p)
    if not data:return
    if p.suffix=='.py':
        try:
            tree=ast.parse('\n'.join(data))
            def visit(node,prefix=''):
                for child in ast.iter_child_nodes(node):
                    named=isinstance(child,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef))
                    qualified=(prefix+'.' if prefix else '')+child.name if named else prefix
                    if named and (qualified in wanted or child.name in wanted):emit(p,child.lineno,'symbol '+qualified)
                    visit(child,qualified)
            visit(tree)
            return
        except (SyntaxError,ValueError,RecursionError):pass
    for i,line in enumerate(data):
        for symbol in wanted:
            if re.search(r'\b'+re.escape(symbol.rsplit('.',1)[-1])+r'\s*\(',line):
                emit(p,i+1,'symbol '+symbol)
for name in plan['files']:
    p=safe(name)
    if p and p not in files:files.append(p)
for item in plan['locations']:
    p=safe(item['path'])
    if p:emit(p,item['line'],'observed error line')
for p in files:
    symbols(p,plan['symbols'])
if plan['symbols'] and not excerpts:
    for base,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in {'.git','node_modules','__pycache__','build','.venv','venv'} and not pathlib.Path(base,d).is_symlink())
        for name in sorted(names):
            scanned+=1
            if scanned>500:break
            p=safe(str(pathlib.Path(base,name).relative_to(root)))
            if p and p.suffix in suffixes:symbols(p,plan['symbols'])
            if excerpts:break
        if excerpts or scanned>500 or read_bytes>=4194304:break
if not plan['symbols'] and not plan['locations']:
    # No invented failure location: provide a bounded index, not file headers.
    for p in files:
        for i,line in enumerate(lines(p)):
            if re.match(r'\s*(?:class|def|async def)\s+\w+',line):
                if len(excerpts)<6:excerpts.append(dict(path=p.relative_to(root).as_posix(),start_line=i+1,reason='symbol index',text=line[:200]))
print(json.dumps(dict(kind='targeted_diagnostic',excerpts=excerpts,
    no_match=not bool(excerpts),bounded=True,scanned_files=scanned),ensure_ascii=False))
'''


def diagnostic_action(anchors):
    plan = diagnostic_plan(anchors)
    return dict(action='run', argv=['python3', '-c', DIAGNOSTIC_SCRIPT],
                stdin=json.dumps(plan, ensure_ascii=False), cwd='.', timeout_seconds=15,
                purpose='Inspect observed error lines or named symbols; report no match explicitly')
