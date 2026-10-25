"""Install a pinned, keyless DSH runtime in this campaign's private directory."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent
BASE = Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')


def package(name, version, destination):
    metadata = json.load(urllib.request.urlopen(
        f'https://registry.npmjs.org/{name}/{version}', timeout=60))
    dist = metadata['dist']
    archive = ROOT / (name.replace('/', '-') + '-' + version + '.tgz')
    payload = urllib.request.urlopen(dist['tarball'], timeout=180).read()
    algorithm, expected = dist['integrity'].split('-', 1)
    assert algorithm == 'sha512'
    assert base64.b64encode(hashlib.sha512(payload).digest()).decode() == expected
    archive.write_bytes(payload)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as stream:
        stream.extractall(destination, filter='data')
    return dist


def main():
    assert ROOT.name == 'lizh639-longcli-dsh20-20261005'
    runtime = ROOT / 'runtime'
    runtime.mkdir(exist_ok=True)
    node_metadata = package('node-linux-x64', '22.19.0', runtime / 'node')
    npm_metadata = package('npm', '11.6.0', runtime / 'npm')
    node = runtime / 'node/package/bin/node'
    npm = runtime / 'npm/package/bin/npm-cli.js'
    os.chmod(node, 0o755)
    env = {**os.environ, 'PATH': str(node.parent) + ':' + os.environ['PATH']}
    subprocess.run([str(node), str(npm), 'install', '--prefix', str(runtime / 'dsh'),
                    '--no-audit', '--no-fund', '@deepseek-ai/dsh@0.2.0-rc.2'],
                   env=env, check=True, timeout=1200)
    actual = json.loads((runtime / 'dsh/node_modules/@deepseek-ai/dsh/package.json').read_text())
    assert actual['version'] == '0.2.0-rc.2'
    for name in ('common.py', 'college_grader.py'):
        shutil.copyfile(BASE / name, ROOT / name)
    for name in ('upstream',):
        link = ROOT / name
        if not link.exists():
            link.symlink_to(BASE / name, target_is_directory=True)
    shutil.copyfile(BASE / 'input-manifest.json', ROOT / 'input-manifest.json')
    for name in ('empty-tests', 'jobs'):
        (ROOT / name).mkdir(exist_ok=True)
    info = {'state': 'installed_not_started', 'version': actual['version'],
            'node': node_metadata, 'npm': npm_metadata,
            'lock_sha256': hashlib.sha256((runtime / 'dsh/package-lock.json').read_bytes()).hexdigest(),
            'paid_model_requests': 0}
    (ROOT / 'installation.json').write_text(json.dumps(info, indent=2))
    print(json.dumps(info))


if __name__ == '__main__':
    main()
