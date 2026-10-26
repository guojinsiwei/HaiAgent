"""Build fresh arms from public pinned runtime only; never copy trials or caches."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
SOURCES = {
    'recuris_frozen': Path('/mnt/sdb/home/lizh639/longcli-recuris-frozen-small20-20261007'),
    'taco': Path('/mnt/sdb/home/lizh639/longcli-taco-clean20-20261007'),
}
REFERENCE = Path('/var/tmp/longcli-dh-routing3x7-20261008')
BASE = Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def replace(path, old, new):
    code = path.read_text()
    assert old in code, f'Missing patch anchor in {path.name}'
    path.write_text(code.replace(old, new))


def main():
    reference = json.loads((REFERENCE / 'protocol.json').read_text())
    assert reference['max_tokens'] == 32768 and reference['context_tokens'] == 1000000
    assert len(reference['tasks']) == 7
    canonical = {k: reference[k] for k in ('model', 'temperature', 'max_tokens', 'context_tokens',
                 'context_headroom_tokens', 'actual_api_attempts_per_task', 'max_tools',
                 'wall_seconds', 'command_seconds', 'tasks')}
    canonical.update(experiment=ROOT.name, methods=list(SOURCES), total_trials=14,
                     max_turns=800, concurrency=6, concurrency_per_arm=3,
                     cross_task_memory=False, thinking=False, source_reference=str(REFERENCE),
                     context_meter='DH-large initial 1.5 heuristic, calibrated from provider prompt_tokens',
                     cpu_per_task=2, memory_gib_per_task=8, pids_limit=256,
                     baseline_modes={'recuris_frozen': 'fixed seed; no Meta/TTA; W mutable within task',
                                     'taco': 'author compression modules on CLI actor; task-local rules'},
                     official_feedback_to_solver=False, notifications={'enabled': False})
    (ROOT / 'protocol.json').write_text(json.dumps(canonical, indent=2))
    provenance = {}
    for method, src in SOURCES.items():
        dest = ROOT / method
        dest.mkdir(exist_ok=False)
        names = ['runner.py', 'sandbox.py', 'command_driver.py', 'common.py', 'safe_process.py',
                 'grade_one.py', 'grading_adapter.py', 'college_grader.py']
        names += ['adapter.py', 'terminal_seed.json', 'test_offline.py'] if method == 'recuris_frozen' else ['agents.py', 'test_offline.py']
        hashes = {}
        for name in names:
            shutil.copyfile(src / name, dest / name); hashes[name] = sha(src / name)
        folder = 'recuris' if method == 'recuris_frozen' else 'taco_native'
        shutil.copytree(src / folder, dest / folder,
                        ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', '.test-tmp*'))
        for name in ('client.py', 'capacity.py', 'worker.py', 'accept_arm.py', 'test_capacity.py'):
            shutil.copyfile(ROOT / name, dest / name)
        for name in ('upstream', 'input-manifest.json'):
            (dest / name).symlink_to(BASE / name, target_is_directory=(BASE / name).is_dir())
        for name in ('jobs', 'grades', 'incoming', 'host-tmp', 'empty-tests', 'acceptance-jobs'):
            (dest / name).mkdir()
        p = dict(canonical, experiment=dest.name, methods=[method], total_trials=7, concurrency=3)
        (dest / 'protocol.json').write_text(json.dumps(p, indent=2))
        # The historical large DH had no extra 3GiB address-space cap or read-only
        # root. Match 2CPU/8GiB/256PIDs; task container is still disposable/networkless.
        replace(dest / 'sandbox.py',
                "self.driver=('import resource; resource.setrlimit(resource.RLIMIT_AS, '\n                     '(3221225472,3221225472))\\n'+(ROOT/'command_driver.py').read_text())",
                "self.driver=(ROOT/'command_driver.py').read_text()")
        replace(dest / 'sandbox.py', "'--pids-limit','128'", "'--pids-limit','256'")
        replace(dest / 'sandbox.py', "            '--read-only','--cap-drop','ALL',", "            '--cap-drop','ALL',")
        replace(dest / 'sandbox.py', "assert x['HostConfig']['ReadonlyRootfs'] and x['HostConfig']['NetworkMode']=='none'",
                "assert not x['HostConfig']['ReadonlyRootfs'] and x['HostConfig']['NetworkMode']=='none'")
        replace(dest / 'sandbox.py', "'read_only_root':True", "'read_only_root':False")
        replace(dest / 'sandbox.py', "'process_address_space_gib':3", "'process_address_space_gib':None")
        replace(dest / 'sandbox.py', '>24000', '>524288')
        replace(dest / 'runner.py', 'client.wire<=1600', 'client.wire<=800')
        # Budget/model errors freeze the current work, not discard its artifact.
        replace(dest / 'runner.py', 'from client import Client', 'from client import Client,BudgetStop,ModelFault')
        anchor = '    except Exception as exc:\n        import traceback'
        replacement = ("    except (BudgetStop,ModelFault) as exc:\n"
            "        if env is not None:\n"
            "            env.close();artifact=env.export()\n"
            "            h.update(state='awaiting_grade',artifact=artifact,task_processes_stopped=True,\n"
            "                     stop_reason=str(exc),submitted=False,model_fault=isinstance(exc,ModelFault))\n"
            "        else: h.update(state='engineering_failure',engineering_fault=type(exc).__name__)\n"
            + anchor)
        replace(dest / 'runner.py', anchor, replacement)
        if method == 'recuris_frozen':
            replace(dest / 'adapter.py', 'max_context_chars=48000', 'max_context_chars=3737856')
            replace(dest / 'adapter.py', 'self._size(result)>45000', 'self._size(result)>3734856')
            replace(dest / 'adapter.py', '[Explicit UTF8 budget projection:', '[Explicit calibrated token-budget projection:')
        else:
            replace(dest / 'runner.py', "cache_path=ROOT/'taco-pool.json'", "cache_path=d/'taco-rules.json'")
            replace(dest / 'agents.py', 'Output limit4096 tokens.',
                    'Output limit32768 tokens. For large code, use stdin with a short command, not a huge argv item.')
            replace(dest / 'agents.py', '>46000', '>3735856')
            replace(dest / 'agents.py', '>48000', '>3737856')
        provenance[method] = {'source': str(src), 'original_hashes': hashes,
                              'author_modules_verbatim': True,
                              'capacity_and_isolation_adapter_only': True}
    (ROOT / 'source-provenance.json').write_text(json.dumps(provenance, indent=2))
    print(json.dumps({'prepared': True, 'trials': 14, 'paid_model_calls': 0}))


if __name__ == '__main__': main()
