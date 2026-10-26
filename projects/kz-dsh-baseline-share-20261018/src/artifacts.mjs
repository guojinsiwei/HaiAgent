import path from 'node:path';
import { lstat } from 'node:fs/promises';
const registries=new Map();
const inside=(root,p)=>{const r=path.relative(root,p);return r===''||r!=='..'&&!r.startsWith('..'+path.sep)&&!path.isAbsolute(r);};
function partsSafe(raw) {
  if(typeof raw!=='string'||!raw.trim()||raw.includes('\0')||raw.split(/[\\/]/).some(p=>['..','.git','.ssh','.aws','.codex'].includes(p)))throw new Error('artifact target is outside the declared safe task scope');
}
export function configureArtifactRoots(root,roots=[]) {
  if(!Array.isArray(roots))throw new Error('artifactRoots must be an explicit array');
  const values=roots.map((raw,i)=>{
    partsSafe(raw);const full=path.resolve(raw);
    if(!path.isAbsolute(raw)||full===path.parse(full).root||/^\/(?:proc|sys|dev|run)(?:\/|$)/.test(full))throw new Error('invalid artifact root');
    return {id:`root${i+1}`,path:full};
  });
  const previous=registries.get(root);
  if(previous&&JSON.stringify(previous)!==JSON.stringify(values))throw new Error('artifact roots changed for an active workspace');
  registries.set(root,values);
}
export function artifactTarget(root,raw) {
  partsSafe(raw);
  if(raw.startsWith('@artifacts/')) {resolveArtifact(root,raw);return raw;}
  const full=path.resolve(root,raw),relative=path.relative(root,full).split(path.sep).join('/');
  if(inside(root,full)&&relative)return relative;
  const match=(registries.get(root)??[]).find(r=>inside(r.path,full));
  if(!match)throw new Error('external artifact path needs an explicitly configured task root');
  return `@artifacts/${match.id}/`+(path.relative(match.path,full).split(path.sep).join('/')||'@root');
}
export function resolveArtifact(root,key) {
  partsSafe(key);
  if(key.startsWith('@artifacts/')) {
    const [,id,...parts]=key.split('/'),match=(registries.get(root)??[]).find(r=>r.id===id);
    if(!match||!parts.length)throw new Error('unregistered artifact root');
    const target=parts.join('/')==='@root'?match.path:path.resolve(match.path,...parts);
    if(!inside(match.path,target))throw new Error('artifact escape');
    return {base:match.path,path:target};
  }
  const target=path.resolve(root,key);
  if(!inside(root,target))throw new Error('artifact escape');
  return {base:root,path:target};
}
export async function checkArtifactPath(root,key) {
  const resolved=resolveArtifact(root,key);
  // Also inspect the configured external root's ancestors; declaring a root
  // must not give an existing symlink escape implicit observation authority.
  let cursor=path.parse(resolved.path).root;
  for(const part of resolved.path.slice(cursor.length).split(path.sep)) {
    cursor=path.join(cursor,part);
    try{if((await lstat(cursor)).isSymbolicLink())throw new Error('artifact symbolic link is unverified');}
    catch(error){if(error.code==='ENOENT')break;throw error;}
  }
  return resolved.path;
}
export function recordArtifactStates(state,dependencies,phase='refresh') {
  const records=state.artifacts??={};
  for(const [target,current] of Object.entries(dependencies)) {
    const row=records[target]??={target,baseline:current,baseline_kind:(state.observed??0)===0?'before_first_observation':'first_registered_observation',registered_phase:phase};
    row.current=current;
    const known=x=>typeof x==='string'&&/^(file:|dir:|missing$)/.test(x);
    row.change=known(row.baseline)&&known(current)?row.baseline===current?'unchanged_since_registration':row.baseline==='missing'?'created_since_registration':'changed_since_registration':'unknown';
  }
  return records;
}
