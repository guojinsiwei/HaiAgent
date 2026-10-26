import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {commitCheckpoint,recoverCommit,writeEvidence} from '../src/persistence.mjs';

function fixture(t) {
  const root=new URL('../.runtime/',import.meta.url);
  fs.mkdirSync(root,{recursive:true});
  const dir=fs.mkdtempSync(new URL('persistence-',root));
  t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  return {file:path.join(dir,'state.json'),log:path.join(dir,'state.jsonl'),dir};
}

for(const boundary of ['intent','events','checkpoint'])test(`recover commit interrupted after ${boundary} exactly once`,t=>{
  const {file,log}=fixture(t);
  commitCheckpoint(file,log,{state:'old'},[{event:'old'}]);
  assert.throws(()=>commitCheckpoint(file,log,{state:'new'},[{event:'new'},{event:'memory'}],stage=>{
    if(stage===boundary)throw Object.assign(Error('disk fault'),{code:'ENOSPC'});
  }),/disk fault/);
  assert.throws(()=>commitCheckpoint(file,log,{state:'unsafe'},[]),/restore/);
  recoverCommit(file,log);recoverCommit(file,log);
  const checkpoint=JSON.parse(fs.readFileSync(file));
  const rows=fs.readFileSync(log,'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(checkpoint.state,'new');assert.equal(checkpoint.commitSeq,2);
  assert.deepEqual(rows.map(r=>r.event),['old','new','memory']);
  assert.deepEqual(rows.map(r=>r.commitSeq),[1,2,2]);
});

test('recover a partial final JSONL record without losing committed prefix',t=>{
  const {file,log}=fixture(t);
  commitCheckpoint(file,log,{state:'old'},[{event:'old'}]);
  assert.throws(()=>commitCheckpoint(file,log,{state:'new'},[{event:'new'}],()=>{throw Error('stop');}));
  const tx=JSON.parse(fs.readFileSync(file+'.txn'));
  fs.appendFileSync(log,tx.events.slice(0,13));
  recoverCommit(file,log);
  assert.equal(fs.readFileSync(log,'utf8').trim().split('\n').length,2);
});

test('independent audit modifications block recovery instead of being overwritten',t=>{
  const {file,log}=fixture(t);
  commitCheckpoint(file,log,{state:'old'},[{event:'old'}]);
  assert.throws(()=>commitCheckpoint(file,log,{state:'new'},[{event:'new'}],()=>{throw Error('stop');}));
  fs.appendFileSync(log,'unexpected\n');
  assert.throws(()=>recoverCommit(file,log),/Unexpected audit suffix/);
  assert.equal(JSON.parse(fs.readFileSync(file)).state,'old');
});

test('archived evidence is immutable and repeated identical writes are idempotent',t=>{
  const {dir}=fixture(t),file=path.join(dir,'E1.json');
  writeEvidence(file,{evidence:{id:'E1'},native:{exit:0}});
  writeEvidence(file,{evidence:{id:'E1'},native:{exit:0}});
  assert.throws(()=>writeEvidence(file,{evidence:{id:'E1'},native:{exit:1}}),/another receipt/);
  assert.equal(JSON.parse(fs.readFileSync(file)).native.exit,0);
});
