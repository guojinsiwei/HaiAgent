import { createHash } from 'node:crypto';
import { lstat, readdir, readFile, realpath } from 'node:fs/promises';
import path from 'node:path';
import { relativeTarget } from './memory.mjs';
import { commandIdentity } from './policy.mjs';
import { literalFileRead } from './commands.mjs';
import { artifactTarget, checkArtifactPath } from './artifacts.mjs';

// Filesystem equality does not cover services, clocks, queues or live logs.
// This conservative recognition is not a complete dependency analysis.
export function unobservedCommandState(command='') {
  const id=commandIdentity(command),dynamic=/^(curl|wget|ping|nc|netcat|ssh|ps|pgrep|top|htop|systemctl|service|journalctl|docker|podman|kubectl|mysql|psql|redis-cli|date|sleep)$/u;
  if(id[0]==='literal')return dynamic.test(id[1].split('/').at(-1))||id[1].split('/').at(-1)==='tail';
  return /(?:^|[;&|]\s*)(?:curl|wget|ping|ssh|ps|systemctl|journalctl|docker|kubectl|mysql|psql|redis-cli|tail)\s/u.test(command);
}

// Explicit local operands and common runtime/build inputs. Unknown shell programs
// retain workspace fallback; these observations are not a complete dependency graph.
export async function commandTargets(root, args = {}) {
  const identity=commandIdentity(args.command??'');if(identity[0]!=='literal')return [];
  const cwd=path.resolve(root,args.workdir??'.'), relative=path.relative(root,cwd);
  if(relative==='..'||relative.startsWith('..'+path.sep)||path.isAbsolute(relative))return [];
  const found=new Set(),exe=identity[1],tokens=identity[2];
  function add(raw){try{found.add(artifactTarget(root,path.resolve(cwd,raw)));}catch{}}
  for(const token of tokens)if(!token.startsWith('-')&&!/^\d+$/.test(token)&&!token.includes('://')&&(literalFileRead(args.command)||token.includes('/')||/\.[\w-]+$/.test(token)))add(token);
  if(/^(python[\d.]*|pytest|node|npm|make|cmake|cargo|go)$/u.test(exe)) {
    // A build/test runner may depend on an entire project. A few manifests are
    // NOT a complete dependency scope: don't veto re-tests after real source edits.
    if(['npm','make','cmake','cargo','go','pytest'].includes(exe)||tokens.includes('-m')||tokens.includes('-c')||tokens.includes('-e')||!found.size)return [];
    for(const p of ['requirements.txt','pyproject.toml','uv.lock','poetry.lock','package.json','package-lock.json','Makefile','CMakeLists.txt','Cargo.toml','Cargo.lock','go.mod','go.sum'])add(p);
    // Observe directly referenced local imports too, without executing source.
    const queue=[...found].filter(x=>/\.(py|js|mjs|ts)$/.test(x));
    for(let i=0;i<queue.length&&i<64;i++) {
      const name=queue[i];let source;
      try{if((await dependencyState(root,[name]))[name]?.startsWith('file:'))source=await readFile(path.join(root,name),'utf8');}catch{}
      if(!source)continue;
      for(const match of source.matchAll(/^\s*(?:from|import)\s+([\w.]+)/gm)) {
        const module=match[1].replaceAll('.','/');
        for(const candidate of [path.posix.join(path.posix.dirname(name),module+'.py'),module+'.py',module]) {
          try{const p=relativeTarget(candidate);if(!found.has(p)){found.add(p);if(p.endsWith('.py'))queue.push(p);}}catch{}
        }
      }
      for(const match of source.matchAll(/(?:from\s*|require\(\s*)['"](\.\.?\/[^'"]+)['"]/g)) {
        try{const p=relativeTarget(path.posix.normalize(path.posix.join(path.posix.dirname(name),match[1])));found.add(p);for(const ext of ['.js','.mjs','.ts'])found.add(p+ext);}catch{}
      }
    }
  }
  return [...found];
}

export function nativeObservation(result) {
  const returnedText=(result?.content??[]).filter(x=>x.type==='text'&&typeof x.text==='string').map(x=>x.text).join('\n');
  const text=returnedText||JSON.stringify(result?.value??{});
  const partial=result?.value?.truncated===true||result?.value?.partial===true||result?.meta?.truncated===true||result?.meta?.truncatedByBytes===true||/line truncated to \d+ chars/.test(text);
  const nativeToolError=!!result?.isError;
  // A returned, untruncated error page is a complete observation of the tool's
  // rejection, not a successful operation or a failed executed CLI strategy.
  // A bare exception/message without a returned page remains unverified.
  return {executed:true,complete:!partial&&(!nativeToolError||!!returnedText.trim()),exitCode:null,stdout:text,
    stderr:nativeToolError?String(result.error?.message??'native tool error'):'',nativeToolError,
    clean:false,failureObserved:false,checkStatus:'unknown',taskSuccess:null,commandExecuted:null,
    executionStatus:nativeToolError?'native_tool_rejected_or_failed':'native_tool_returned',
    observationScope:nativeToolError?'returned native tool error only; command execution, side effects and route failure unverified':'returned tool page only; not proof of absence outside this page',displayPartial:partial};
}

export function nativeTargets(root,args={}) {
  const targets=[];
  for(const raw of [args.path,args.file_path])if(typeof raw==='string') {
    try{targets.push(artifactTarget(root,raw));}catch{}
  }
  return targets;
}

export async function dependencyState(root, targets) {
  const result = {};
  for (const raw of targets) {
    let name;
    try {
      name = relativeTarget(raw); const cursor = await checkArtifactPath(root,name);
      const stat = await lstat(cursor);
      result[name] = stat.isDirectory() ? (await fingerprint(cursor)).replace(/^sha256:/u,'dir:')
        : stat.isFile() ? 'file:' + createHash('sha256').update(String(stat.mode)).update(await readFile(cursor)).digest('hex') : 'unknown';
    } catch (e) { result[name ?? raw] = e.code === 'ENOENT' ? 'missing' : 'unknown'; }
  }
  return result;
}

// A read-only observation bound, NOT a tool-output or execution restriction.
// A partial/unreadable tree is UNKNOWN, never evidence of an unchanged state.
export async function fingerprint(root, { maxFiles = 20000, maxBytes = 67108864 } = {}) {
  const hash = createHash('sha256'); let files = 0, bytes = 0;
  async function visit(dir) {
    for (const name of (await readdir(dir)).sort()) {
      if (name === '.git') continue;
      const full = path.join(dir, name), stat = await lstat(full);
      if (stat.isSymbolicLink()) throw new Error('symlink state unverified');
      hash.update(path.relative(root, full)); hash.update('\0');
      hash.update(String(stat.mode)); hash.update('\0');
      if (stat.isDirectory()) await visit(full);
      else if (stat.isFile()) {
        if (++files > maxFiles || (bytes += stat.size) > maxBytes) throw new Error('observation bound');
        hash.update(await readFile(full)); hash.update('\0');
      } else throw new Error('non-file state unverified');
    }
  }
  try { await visit(root); return 'sha256:' + hash.digest('hex'); }
  catch { return 'unknown:incomplete_workspace_observation'; }
}

export async function resolveWorkspace(root) {
  if (!path.isAbsolute(root)) throw new Error('workspace must be an absolute task directory');
  const resolved = await realpath(root);
  if (!(await lstat(resolved)).isDirectory() || resolved === path.parse(resolved).root)
    throw new Error('workspace must be a task directory, not a filesystem root');
  return resolved;
}

export function bashObservation(result) {
  const value = result?.value;
  if (result?.isError || value?.kind !== 'foreground')
    return { executed: false, complete: false, exitCode: null, stdout: '', stderr: '' };
  const sandboxFailed=!!(value.sandbox?.denied||value.sandbox?.runnerFailed);
  return { executed: !sandboxFailed,
    complete: !sandboxFailed && !value.timedOut && !value.aborted && !value.stopped && !value.signal &&
      value.stdout?.truncated === false && value.stderr?.truncated === false,
    timedOut:value.timedOut,aborted:value.aborted,stopped:value.stopped,signal:value.signal,sandbox:value.sandbox,
    exitCode: value.exitCode, stdout: value.stdout?.text ?? '', stderr: value.stderr?.text ?? '' };
}
