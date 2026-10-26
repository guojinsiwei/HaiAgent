// Algorithm-owned file checkpoints, NOT a replacement shell or tool runner.
// Restores are dispatched by the plugin through DSH's native bash/permission path.
import { cp, mkdir, readdir, lstat, readFile, writeFile, realpath, rename } from 'node:fs/promises';
import path from 'node:path';
import { fingerprint, resolveWorkspace } from './workspace.mjs';

async function inspectTree(root) {
  let bytes = 0;
  async function visit(dir) {
    for (const name of await readdir(dir)) {
      if (name === '.git') continue;
      const file = path.join(dir,name), stat = await lstat(file);
      if (stat.isSymbolicLink() || !stat.isFile() && !stat.isDirectory()) throw new Error('checkpoint cannot safely represent special files or symlinks');
      if (stat.isDirectory()) await visit(file); else bytes += stat.size;
    }
  }
  await visit(root); return bytes;
}
async function copyEntries(source, destination) {
  await mkdir(destination, { recursive: true });
  for (const name of await readdir(source)) if (name !== '.git') await cp(path.join(source,name),path.join(destination,name),{ recursive: true, errorOnExist: true, force: false, preserveTimestamps: true });
}
export async function saveCheckpoint(root, base, id, maxBytes = 1073741824) {
  root = await resolveWorkspace(root);
  if (!/^C\d+$/u.test(id)) throw new Error('invalid checkpoint ID');
  const rel = path.relative(root,path.resolve(base));
  if (rel === '' || !rel.startsWith('..') && !path.isAbsolute(rel)) throw new Error('checkpoint storage must be outside workspace');
  if (await inspectTree(root) > maxBytes) throw new Error('checkpoint observation capacity exceeded; continue without snapshot');
  const before = await fingerprint(root), destination = path.join(base,id);
  if (!before.startsWith('sha256:')) throw new Error('snapshot state is not fully observable');
  await mkdir(destination, { recursive: false });
  await copyEntries(root,path.join(destination,'files'));
  if (before !== await fingerprint(root) || before !== await fingerprint(path.join(destination,'files'))) throw new Error('workspace changed during snapshot');
  await writeFile(path.join(destination,'manifest.json'),JSON.stringify({ root, id, scope:before }));
  return { id, path:destination, scope:before };
}
export async function restoreCheckpoint(root, snapshot, preserved) {
  root = await resolveWorkspace(root); snapshot = await realpath(snapshot);
  const manifest = JSON.parse(await readFile(path.join(snapshot,'manifest.json'),'utf8'));
  if (manifest.root !== root || !manifest.scope?.startsWith('sha256:')) throw new Error('checkpoint workspace mismatch');
  const relative = path.relative(root,path.resolve(preserved));
  if (relative === '' || !relative.startsWith('..') && !path.isAbsolute(relative)) throw new Error('preserved attempt must be outside workspace');
  await inspectTree(root); await inspectTree(path.join(snapshot,'files'));
  if (manifest.scope !== await fingerprint(path.join(snapshot,'files'))) throw new Error('checkpoint corruption');
  await mkdir(preserved, { recursive:false });
  // Make a complete backup BEFORE moving anything; even a mid-restore I/O failure
  // cannot lose the original attempt. Failed restore files are also recoverable.
  await copyEntries(root,preserved);
  const originalScope=await fingerprint(root);
  if(!originalScope.startsWith('sha256:')||originalScope!==await fingerprint(preserved))throw new Error('cannot safely preserve current attempt');
  const displaced=preserved+'-displaced';await mkdir(displaced);
  try {
    for (const name of await readdir(root)) if (name !== '.git') await rename(path.join(root,name),path.join(displaced,name));
    await copyEntries(path.join(snapshot,'files'),root);
    if (manifest.scope !== await fingerprint(root)) throw new Error('restore verification failed');
  } catch(error) {
    const failed=preserved+'-failed-restore';await mkdir(failed);
    for(const name of await readdir(root))if(name!=='.git')await rename(path.join(root,name),path.join(failed,name));
    await copyEntries(preserved,root);
    throw new Error(`restore failed; original attempt recovered from ${preserved}: ${error.message}`);
  }
  return { restored:manifest.id, preserved, scope:manifest.scope };
}
