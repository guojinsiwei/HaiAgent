"""Validate a cloud export, run official Docker harness locally, and join all task results."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile

from benchmark_runtime import atomic_write_json, atomic_write_text, canonical_sha256
from benchmark_splits import reject_frozen_overlap
from run_notebook import run_lock


def predictions_from_text(text):
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    ids = []
    for row in rows:
        if set(row) != {'instance_id', 'model_name_or_path', 'model_patch'} or not all(isinstance(v, str) for v in row.values()):
            raise ValueError('Invalid prediction fields')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+', row['instance_id']):
            raise ValueError('Unsafe instance id')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', row['model_name_or_path']):
            raise ValueError('Use a filesystem-safe model name')
        ids.append(row['instance_id'])
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Empty predictions or duplicate instance ids')
    reject_frozen_overlap(ids, benchmark='swebench', allow_frozen_test_set=False)
    return rows


def read_bundle(path, allow_partial=False):
    # Never extract a remote archive. Read only expected data files after integrity checks.
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or sum(x.file_size for x in archive.infolist()) > 128 * 1024 ** 2:
            raise ValueError('Duplicate archive entries or bundle too large')
        manifest = json.loads(archive.read('bundle.json'))
        if manifest.get('schema_version') != 1 or manifest.get('dataset') != 'SWE-bench/SWE-bench_Verified' or manifest.get('split') != 'test':
            raise ValueError('Invalid bundle identity')
        expected = manifest['expected_ids']
        if len(expected) != manifest['total'] or len(expected) != len(set(expected)):
            raise ValueError('Bundle denominator mismatch')
        if not allow_partial and manifest.get('terminal') != manifest['total']:
            raise ValueError('Batch is not finished; use --allow-partial only for an explicitly provisional report')
        blobs = {}
        for name in ('predictions.jsonl', 'summary.json', 'batch.json'):
            blob = archive.read(name)
            if hashlib.sha256(blob).hexdigest() != manifest['sha256'].get(name):
                raise ValueError(f'Bundle checksum mismatch: {name}')
            blobs[name] = blob
        rows = predictions_from_text(blobs['predictions.jsonl'].decode('utf-8'))
        if [r['instance_id'] for r in rows] != expected:
            raise ValueError('Predictions do not cover exactly the fixed plan')
        summary = json.loads(blobs['summary.json'])
        if [s['id'] for s in summary] != expected:
            raise ValueError('Summary identity mismatch')
        batch = json.loads(blobs['batch.json'])
        if batch['plan_sha256'] != manifest['plan_sha256']:
            raise ValueError('Batch/plan mismatch')
        if 'comparison' in manifest:
            comparison = manifest['comparison']
            if (comparison['protocol'] != batch.get('protocol') or
                    canonical_sha256(comparison['protocol']) != comparison['protocol_sha256']):
                raise ValueError('Comparison protocol mismatch')
            if comparison['protocol']['expected_ids'] != expected or comparison['protocol']['plan_sha256'] != manifest['plan_sha256']:
                raise ValueError('Comparison protocol task list mismatch')
        return blobs['predictions.jsonl'], rows, summary, manifest


def capture(command):
    result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=90)
    return result.stdout.strip()


def linux_path(path, distro):
    if os.name != 'nt':
        return str(Path(path).resolve())
    return capture(['wsl', '-d', distro, '--exec', 'wslpath', '-a', Path(path).resolve().as_posix()])


def command_prefix(args, directory):
    if os.name == 'nt':
        return ['wsl', '-d', args.distro, '--cd', linux_path(directory, args.distro), '--exec']
    return []


def summarize(rows, cloud, reports):
    state_by_id = {s['id']: s for s in cloud}
    results = []
    totals = {'selected': len(rows), 'resolved': 0, 'unresolved': 0, 'evaluation_error': 0, 'empty_patch': 0,
              'prompt_tokens_recorded': 0, 'completion_tokens_recorded': 0}
    for prediction in rows:
        identity = prediction['instance_id']
        state = state_by_id.get(identity, {})
        report = reports.get(identity)
        verdict = ('resolved' if report['resolved'] else 'unresolved') if report is not None else ('empty_patch' if not prediction['model_patch'].strip() else 'evaluation_error')
        totals[verdict] += 1
        attempts = [*state.get('previous_attempts', []), state]
        for attempt in attempts:
            usage = attempt.get('model_usage', {})
            totals['prompt_tokens_recorded'] += usage.get('prompt_tokens', 0)
            totals['completion_tokens_recorded'] += usage.get('completion_tokens', 0)
        results.append({'instance_id': identity, 'search_status': state.get('status', 'unknown'),
                        'agent_succeeded': state.get('agent_succeeded'), 'verdict': verdict,
                        'resolved': report['resolved'] if report else None,
                        'official_report_available': report is not None,
                        'stop_reason': state.get('stop_reason'), 'tool_calls': state.get('tool_calls'),
                        'interaction_rounds': state.get('interaction_rounds'),
                        'comparison_metrics': state.get('comparison_metrics'),
                        'model_usage': state.get('model_usage', {}),
                        'attempt_count': state.get('attempt_count', 1),
                        'previous_attempts': state.get('previous_attempts', []),
                        'last_attempt_seconds': state.get('last_attempt_seconds')})
    totals['resolved_rate_over_selected'] = totals['resolved'] / len(rows)
    totals['usage_note'] = 'Recorded API usage only; interrupted calls and preflight requests may not be included. Not a bill.'
    return {'summary': totals, 'tasks': results}


def main(argv=None):
    # Official harness progress uses Unicode; Windows consoles may default to GBK.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--bundle', type=Path)
    inputs.add_argument('--predictions', type=Path, help='Also supports a single legacy predictions.jsonl')
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--harness-python', default='/home/research/SWE-bench/.venv/bin/python')
    parser.add_argument('--distro', default='Ubuntu')
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--allow-partial', action='store_true')
    parser.add_argument('--offline', action='store_true', help='Use existing HF dataset cache; missing Docker images may still be pulled')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--ssh-host', help='Optional configured OpenSSH alias; download bundle first')
    parser.add_argument('--remote-bundle', default='/mnt/lizh639/bestfgs-runs/swe100-v1/evaluation-bundle.zip')
    args = parser.parse_args(argv)
    if args.workers < 1 or args.timeout < 1:
        raise ValueError('workers/timeout must be positive')
    if args.ssh_host:
        if args.dry_run or not args.bundle:
            raise ValueError('SSH fetch requires --bundle and an actual run')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.ssh_host) or not re.fullmatch(r'/[A-Za-z0-9_./-]+', args.remote_bundle):
            raise ValueError('Unsafe SSH alias/path')
        args.bundle.parent.mkdir(parents=True, exist_ok=True)
        partial = args.bundle.with_suffix('.part')
        subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                        args.ssh_host + ':' + args.remote_bundle, str(partial)], check=True, timeout=300)
        read_bundle(partial, args.allow_partial)
        os.replace(partial, args.bundle)
    if args.bundle:
        blob, rows, cloud, bundle = read_bundle(args.bundle, args.allow_partial)
    else:
        blob = args.predictions.read_bytes()
        rows = predictions_from_text(blob.decode('utf-8'))
        cloud, bundle = [], {}
    fingerprint = hashlib.sha256(blob).hexdigest()
    run_id = 'bestfgs-batch-' + fingerprint[:16]
    output = args.output_root.resolve() / run_id
    config = {'schema_version': 1, 'predictions_sha256': fingerprint, 'run_id': run_id,
              'dataset': 'SWE-bench/SWE-bench_Verified', 'split': 'test',
              'harness_python': args.harness_python, 'timeout': args.timeout,
              'expected_ids': [r['instance_id'] for r in rows]}
    if args.dry_run:
        print(json.dumps({**config, 'output': str(output), 'workers': args.workers}, indent=2))
        return 0
    with run_lock(output):
        manifest_path = output / 'evaluation.json'
        probe = command_prefix(args, output) + [args.harness_python, '-c',
                'import docker,swebench,json,subprocess,pathlib,importlib.metadata; '
                'c=docker.from_env(); assert c.ping(); '
                'root=str(pathlib.Path(swebench.__file__).resolve().parent.parent); '
                'commit=subprocess.run(["git","-C",root,"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip(); '
                'dirty=subprocess.run(["git","-C",root,"status","--porcelain","--","swebench","pyproject.toml"],capture_output=True,text=True,check=True).stdout.strip(); '
                'assert not any(x.name.endswith(' + repr('.' + run_id) + ') for x in c.containers.list()),"An evaluation for this run is still active"; '
                'print(json.dumps({"harness_commit":commit,"harness_dirty":bool(dirty),"swebench_version":importlib.metadata.version("swebench"),"docker_version":c.version()["Version"]}))']
        config['runtime'] = json.loads(capture(probe))
        if config['runtime']['harness_dirty']:
            raise ValueError('Official harness checkout has local changes; verify/restore a clean checkout before grading')
        if manifest_path.exists() and json.loads(manifest_path.read_text()) != config:
            raise ValueError('Evaluation settings/harness changed; use a new output root to avoid stale reports')
        print(json.dumps(config['runtime']), flush=True)
        atomic_write_json(manifest_path, config)
        # Preserve the byte-identical file. No patches are edited during evaluation.
        (output / 'predictions.jsonl').write_bytes(blob)
        atomic_write_json(output / 'cloud-summary.json', cloud)
        if bundle:
            atomic_write_json(output / 'bundle-manifest.json', bundle)
        command = command_prefix(args, output)
        if args.offline:
            command += ['env', 'HF_HUB_OFFLINE=1', 'HF_DATASETS_OFFLINE=1']
        command += [args.harness_python, '-m', 'swebench.harness.run_evaluation',
                    '--dataset_name', config['dataset'], '--split', 'test', '--predictions_path', 'predictions.jsonl',
                    '--instance_ids', *config['expected_ids'], '--max_workers', str(args.workers), '--timeout', str(args.timeout),
                    '--run_id', run_id, '--cache_level', 'env', '--clean', 'False', '--report_dir', '.']
        started = time.monotonic()
        with (output / 'harness.log').open('a', encoding='utf-8') as log:
            # Stream progress while retaining the complete UTF-8 log.
            process = subprocess.Popen(command, cwd=output, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding='utf-8', errors='replace')
            try:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    print(line, end='', flush=True)
                code = process.wait()
            except KeyboardInterrupt:
                print('Interrupted; rerun the same command to collect/reuse official reports.', file=sys.stderr)
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                process.stdout.close()
        reports = {}
        for row in rows:
            path = output / 'logs/run_evaluation' / run_id / row['model_name_or_path'] / row['instance_id'] / 'report.json'
            if path.is_file():
                report = json.loads(path.read_text())[row['instance_id']]
                if not isinstance(report.get('resolved'), bool):
                    raise ValueError('Invalid official report')
                reports[row['instance_id']] = report
        joined = summarize(rows, cloud, reports)
        for task in joined['tasks']:
            prediction = next(r for r in rows if r['instance_id'] == task['instance_id'])
            script = output / 'logs/run_evaluation' / run_id / prediction['model_name_or_path'] / task['instance_id'] / 'eval.sh'
            task['grading_script_sha256'] = hashlib.sha256(script.read_bytes()).hexdigest() if script.is_file() else None
        joined.update(harness_exit_code=code, elapsed_seconds=round(time.monotonic() - started, 2),
                      run_id=run_id, predictions_sha256=fingerprint)
        joined['comparison'] = bundle.get('comparison')
        joined['evaluation_parameters'] = {k: config[k] for k in ('dataset', 'split', 'timeout', 'runtime')}
        atomic_write_json(output / 'results.json', joined)
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=list(joined['tasks'][0]))
        writer.writeheader()
        writer.writerows(joined['tasks'])
        atomic_write_text(output / 'results.csv', stream.getvalue())
        print(json.dumps(joined['summary'], indent=2))
        print(f'Results: {output / "results.json"}', flush=True)
        return 2 if code or joined['summary']['evaluation_error'] else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print(f'[evaluation error] {exc}', file=sys.stderr)
        raise SystemExit(2)
