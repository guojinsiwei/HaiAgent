"""Mechanically extract the active v6.1 import closure into an independent reader.

Only three legacy-heavy dependency modules are sliced by top-level symbol reachability.
Retained definitions are copied verbatim, not regenerated from AST. Record every source.
"""
import ast
import hashlib
import json
from pathlib import Path
import shutil

WORKSPACE = Path(__file__).resolve().parents[1]
SOURCE = WORKSPACE/'experiment_records/longcli-v6-raw-paired10-20261001'
OUTPUT = WORKSPACE/'experiment_records/bestfgs-minimal-reader-20261001'
PACKAGES = {'bestfgs': SOURCE/'sources/bestfgs-project/src/bestfgs',
            'haiagent': SOURCE/'sources/hai-project/src/haiagent',
            'terminal_context': SOURCE/'sources/hai-project/src/terminal_context'}
SLICED = {'bestfgs.retrac_adapter', 'bestfgs.environment', 'bestfgs.models',
          'bestfgs.prompt_views', 'bestfgs.semantic', 'bestfgs.lean_docker', 'haiagent.demo'}
INITIAL = ['bestfgs.lean_runtime', 'bestfgs.lean_protocol', 'bestfgs.lean_environment',
           'bestfgs.monitor_config', 'bestfgs.shell_probe',
           'bestfgs.tool_outcomes', 'haiagent.runtime', 'haiagent.protocol',
           'haiagent.model', 'haiagent.executor']
DEMANDS = {name: None for name in INITIAL}
DEMANDS['bestfgs.retrac_adapter'] = {'OpenAICompatibleJSONClient', 'RetracModelConfig', 'ModelCallError'}
DEMANDS['bestfgs.models'] = {'TaskSpec', 'CommandSpec', 'CommandResult', 'ModelCallError'}
DEMANDS['bestfgs.lean_docker'] = {'FINGERPRINT_SCRIPT', 'DEPENDENCY_SCRIPT'}
DEMANDS['haiagent.demo'] = {'ScriptedClient'}
FILES = {}
PROVENANCE = []


def locate(module):
    parts = module.split('.')
    if parts[0] not in PACKAGES: return None
    p = PACKAGES[parts[0]].joinpath(*parts[1:])
    p = p/'__init__.py' if p.is_dir() else p.with_suffix('.py')
    return p if p.exists() else None


def bound(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): return {node.name}
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {a.asname or (a.name.split('.')[0] if isinstance(node, ast.Import) else a.name) for a in node.names}
    return set()


def extract(module, requested):
    path = locate(module)
    source = path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    if module not in SLICED:
        return source, tree, None
    if requested is None: raise RuntimeError('Sliced modules require explicit symbols: '+module)
    definitions = {name: node for node in tree.body for name in bound(node)}
    missing = requested-set(definitions)
    if missing: raise RuntimeError('Missing symbols: '+repr((module, missing)))
    selected = set(requested)
    while True:
        expanded = set(selected)
        for name in selected:
            expanded.update(n.id for n in ast.walk(definitions[name]) if isinstance(n, ast.Name) and n.id in definitions)
        if expanded == selected: break
        selected = expanded
    lines = source.splitlines(keepends=True)
    segments = []
    ranges = []
    for node in tree.body:
        names = bound(node)
        if isinstance(node, ast.ImportFrom) and node.module == '__future__':
            keep = node.names
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            keep = [a for a in node.names if (a.asname or (a.name.split('.')[0] if isinstance(node, ast.Import) else a.name)) in selected]
        else:
            if not names & selected: continue
            start = min([node.lineno]+[d.lineno for d in getattr(node, 'decorator_list', [])])
            segments.append(''.join(lines[start-1:node.end_lineno]).rstrip()+'\n')
            ranges.append([start, node.end_lineno])
            continue
        if not keep: continue
        if isinstance(node, ast.Import):
            retained = ast.Import(names=keep)
        else:
            retained = ast.ImportFrom(module=node.module, names=keep, level=node.level)
        segments.append(ast.unparse(retained)+'\n')
        ranges.append([node.lineno, node.end_lineno])
    extracted = '\n'.join(segments)
    return extracted, ast.parse(extracted), dict(symbols=sorted(selected), original_line_ranges=ranges)


def dependencies(module, tree):
    package = module if locate(module).name == '__init__.py' else module.rsplit('.', 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split('.')
                base = '.'.join(parts[:len(parts)-node.level+1])
                target = base + ('.'+node.module if node.module else '')
            else: target = node.module or ''
            if locate(target):
                yield target, {a.name for a in node.names}
            else:
                for a in node.names:
                    if locate(target+'.'+a.name): yield target+'.'+a.name, None
        elif isinstance(node, ast.Import):
            for a in node.names:
                if locate(a.name): yield a.name, None


def demand(module, names):
    if module == 'bestfgs': return False  # replace legacy eager initializer explicitly
    if module not in DEMANDS:
        DEMANDS[module] = names if module in SLICED else None
        return True
    if module in SLICED and names:
        before = len(DEMANDS[module]); DEMANDS[module].update(names)
        return len(DEMANDS[module]) != before
    return False


def main():
    while True:
        changed = False
        for module, names in list(DEMANDS.items()):
            source, tree, detail = extract(module, names)
            FILES[module] = source, detail
            for target, symbols in dependencies(module, tree): changed |= demand(target, symbols)
            parent = module.rsplit('.', 1)[0] if '.' in module else None
            if parent and parent != 'bestfgs' and locate(parent): changed |= demand(parent, None)
        if not changed: break
    OUTPUT.mkdir(exist_ok=True)
    for module, (source, detail) in sorted(FILES.items()):
        original = locate(module)
        relative = Path('src').joinpath(*module.split('.'))
        relative = relative/'__init__.py' if original.name == '__init__.py' else relative.with_suffix('.py')
        destination = OUTPUT/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if detail is None: shutil.copy2(original, destination)
        else: destination.write_text(source, encoding='utf-8')
        PROVENANCE.append(dict(path=relative.as_posix(), source=str(original.relative_to(WORKSPACE)),
            source_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
            extracted_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
            extraction='verbatim' if detail is None else 'top_level_symbol_closure', detail=detail))
    for name in ('test_lean.py', 'test_model_wire.py'):
        original = SOURCE/'sources/bestfgs-project/tests'/name
        destination = OUTPUT/'tests'/name
        destination.parent.mkdir(exist_ok=True); shutil.copy2(original, destination)
        PROVENANCE.append(dict(path='tests/'+name,source=str(original.relative_to(WORKSPACE)),
            source_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
            extracted_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(), extraction='verbatim'))
    for name in ('runner.py','environment.py','audit.py','net_transport.py','common.py','chroot_entry.py'):
        original = SOURCE/name
        destination = OUTPUT/'experiment_adapter'/name
        destination.parent.mkdir(exist_ok=True); shutil.copy2(original, destination)
        PROVENANCE.append(dict(path='experiment_adapter/'+name,source=str(original.relative_to(WORKSPACE)),
            source_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
            extracted_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(), extraction='verbatim_reference'))
    (OUTPUT/'SOURCE_MANIFEST.json').write_text(json.dumps(dict(
        source_experiment=SOURCE.name, algorithm='monitor-control-v6.1',
        benchmark_commit='2015f37b5c458f2562354de6b415e9182c91af64',
        original_project_untouched=True, files=PROVENANCE), ensure_ascii=False, indent=2),encoding='utf-8')
    print(json.dumps(dict(output=str(OUTPUT), modules=len(FILES), files=len(PROVENANCE),
        sliced=sorted(SLICED), bytes=sum((OUTPUT/r['path']).stat().st_size for r in PROVENANCE))))


if __name__ == '__main__': main()
