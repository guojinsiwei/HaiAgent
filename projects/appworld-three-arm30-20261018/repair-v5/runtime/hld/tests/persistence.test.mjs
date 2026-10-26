import test from 'node:test';
import assert from 'node:assert/strict';
import { replaceCheckpoint } from '../src/persistence.mjs';

test('transient atomic-replace locks retry without dropping the old checkpoint',()=>{
  const pauses=[];let attempts=0;
  replaceCheckpoint('new.tmp','old.json',(from,to)=>{
    assert.equal(from,'new.tmp');assert.equal(to,'old.json');
    if(++attempts<4)throw Object.assign(new Error('locked'),{code:'EPERM'});
  },ms=>pauses.push(ms));
  assert.equal(attempts,4);assert.deepEqual(pauses,[5,10,20]);
});
test('persistent audit failure stays explicit and retries are bounded',()=>{
  let attempts=0;const pauses=[];
  assert.throws(()=>replaceCheckpoint('new.tmp','old.json',()=>{attempts++;throw Object.assign(new Error('locked'),{code:'EBUSY'});},ms=>pauses.push(ms)),/locked/);
  assert.equal(attempts,6);assert.equal(pauses.reduce((a,b)=>a+b,0),155);
  attempts=0;assert.throws(()=>replaceCheckpoint('new.tmp','old.json',()=>{attempts++;throw Object.assign(new Error('disk full'),{code:'ENOSPC'});},()=>assert.fail()),/disk full/);
  assert.equal(attempts,1);
});
