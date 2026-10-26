import fs, { renameSync } from 'node:fs';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';

// Windows indexers/AV can briefly lock the destination of atomic replace.
// Keep both files intact: never unlink the valid checkpoint to force a rename.
// At most 155 ms of bounded local retry; permanent errors stay explicit.
export function replaceCheckpoint(temporary, destination, rename = renameSync,
  pause = ms => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,ms)) {
  for(let attempt=0;;attempt++) {
    try { rename(temporary,destination);return; }
    catch(error) {
      if(!['EPERM','EACCES','EBUSY'].includes(error.code)||attempt>=5)throw error;
      pause(5*2**attempt);
    }
  }
}

function syncDirectory(directory) {
  if(process.platform==='win32')return; // Windows has no supported directory fsync.
  const fd=fs.openSync(directory,'r');
  try {fs.fsyncSync(fd);} finally {fs.closeSync(fd);}
}

export function durableWrite(file, text) {
  const temporary=file+'.'+randomUUID()+'.tmp';
  try {
    const fd=fs.openSync(temporary,'wx',0o600);
    try {fs.writeFileSync(fd,text);fs.fsyncSync(fd);} finally {fs.closeSync(fd);}
    replaceCheckpoint(temporary,file);
    syncDirectory(path.dirname(file));
  } finally {if(fs.existsSync(temporary))fs.unlinkSync(temporary);}
}

const hash=text=>createHash('sha256').update(text).digest('hex');

// A durable pending transaction is authoritative until both projections are
// materialized. Recovery is idempotent even after a partial JSONL append.
export function recoverCommit(file, log, fault=()=>{}) {
  const pending=file+'.txn';
  if(!fs.existsSync(pending))return;
  const tx=JSON.parse(fs.readFileSync(pending,'utf8'));
  if(tx.version!==1||!Number.isSafeInteger(tx.offset)||tx.offset<0||
     typeof tx.events!=='string'||typeof tx.checkpoint!=='string'||
     hash(tx.checkpoint)!==tx.checkpointHash)throw Error('Invalid pending checkpoint transaction');
  const prefix=fs.existsSync(log)?fs.readFileSync(log):Buffer.alloc(0);
  if(prefix.length<tx.offset||hash(prefix.subarray(0,tx.offset))!==tx.prefixHash)
    throw Error('Audit prefix differs from pending transaction; explicit reconciliation required');
  const suffix=prefix.subarray(tx.offset),expected=Buffer.from(tx.events);
  if(suffix.length>expected.length||!expected.subarray(0,suffix.length).equals(suffix))
    throw Error('Unexpected audit suffix; refusing to overwrite independent records');
  const fd=fs.openSync(log,fs.existsSync(log)?'r+':'w',0o600);
  try {
    fs.ftruncateSync(fd,tx.offset);
    fs.writeFileSync(fd,Buffer.alloc(0));
    // writeSync can return a short write, especially on injected I/O failures.
    let n=0;while(n<expected.length) {
      const count=fs.writeSync(fd,expected,n,expected.length-n,tx.offset+n);
      if(count===0)throw Error('Zero-length audit write');n+=count;
    }
    fs.fsyncSync(fd);
  } finally {fs.closeSync(fd);}
  fault('events');
  durableWrite(file,tx.checkpoint);
  fault('checkpoint');
  fs.unlinkSync(pending);syncDirectory(path.dirname(file));
}

export function commitCheckpoint(file, log, data, events, fault=()=>{}) {
  // A live process must stop after a failed commit. Only restoration may replay
  // the pending transaction; never commit a new tool admission over it.
  if(fs.existsSync(file+'.txn'))throw Error('Pending checkpoint transaction; restore before continuing');
  const prior=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):null;
  const seq=(prior?.commitSeq??0)+1;
  const checkpoint=JSON.stringify({...data,commitSeq:seq});
  const prefix=fs.existsSync(log)?fs.readFileSync(log):Buffer.alloc(0);
  const text=events.map((e,i)=>JSON.stringify({...e,commitSeq:seq,eventIndex:i})+'\n').join('');
  durableWrite(file+'.txn',JSON.stringify({version:1,offset:prefix.length,prefixHash:hash(prefix),
    events:text,checkpoint,checkpointHash:hash(checkpoint)}));
  fault('intent');
  recoverCommit(file,log,fault);
}

export function writeEvidence(file, value) {
  const text=JSON.stringify(value);
  if(fs.existsSync(file)) {
    if(fs.readFileSync(file,'utf8')!==text)throw Error('Evidence ID already belongs to another receipt');
    return;
  }
  durableWrite(file,text);
}
