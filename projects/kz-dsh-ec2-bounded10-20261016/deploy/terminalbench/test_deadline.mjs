import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {deadline,signalOwned} from './deadline.mjs';

test('deadline still terminates solver when audit disk write fails',async()=>{
  const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)']);
  const guard=deadline(child,.1,()=>{throw Error('ENOSPC fixture');},50);
  const result=await new Promise(resolve=>child.on('exit',(code,signal)=>resolve({code,signal})));
  guard.finish();assert.equal(guard.expired,true);assert.ok(result.signal);
});
test('PID reuse cannot signal another process',()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'native-guard-'));
  try {
    fs.mkdirSync(path.join(root,'123'));
    const cols=['S','1',...Array(17).fill('0'),'changed-start'];
    fs.writeFileSync(path.join(root,'123/stat'),'123 (fixture) '+cols.join(' '));
    const calls=[];signalOwned([{pid:123,start:'old-start'}],'SIGKILL',root,(...a)=>calls.push(a));
    assert.equal(calls.length,0);
  } finally {fs.rmSync(root,{recursive:true});}
});
