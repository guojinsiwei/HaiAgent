import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, mkdtemp, writeFile, symlink } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { readTaskInstruction, TaskInstructionError } from '../src/task-instruction.mjs';

async function fixture() {
  const base=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(base,{recursive:true});
  const parent=await mkdtemp(path.join(base,'task-instruction-')),root=path.join(parent,'task');await mkdir(root);
  return {parent,root};
}
const code = value => error => error instanceof TaskInstructionError&&error.code===`TASK_INSTRUCTION_${value}`;

test('R4 task instruction: absent config performs no filesystem discovery',async()=>{
  for(const value of [undefined,null,''])assert.equal(await readTaskInstruction('nonexistent root',value),null);
});

test('R4 task instruction: only explicit public file is read completely and hashed without rewriting',async()=>{
  const {root}=await fixture();await mkdir(path.join(root,'public'));
  const text='\uFEFF公开任务：完成 HW3 和 HW5。\r\n'+('保留每条要求。\n'.repeat(12000));
  await writeFile(path.join(root,'public','task.md'),text);await writeFile(path.join(root,'README.md'),'Contradictory HW4 wrapper');
  const value=await readTaskInstruction(root,'public/task.md');assert.equal(value.text,text);assert.equal(value.path,'public/task.md');
  assert.equal(value.sha256,createHash('sha256').update(Buffer.from(text)).digest('hex'));
});

test('R4 task instruction: dangerous and hidden path forms fail before touching the filesystem',async()=>{
  for(const name of ['/tmp/task.md','C:/task.md','C:task.md','../task.md','a/../task.md','a\\task.md','//server/share/task.md','a//task.md','./task.md',' .txt','task.md ','a/./task.md','.env','a/.git/config','.hidden/task.md','grader/task.md','hidden_tests/task.md','solutions/task.md','id_rsa','credentials.json','a\0b','task.md:stream']) {
    await assert.rejects(readTaskInstruction('nonexistent root',name),code('INVALID_PATH'),name);
  }
});

test('R4 task instruction: missing configured file does not fall back to a present README',async()=>{
  const {root}=await fixture();await writeFile(path.join(root,'README.md'),'wrapper');
  await assert.rejects(readTaskInstruction(root,'task.md'),code('MISSING'));
});

test('R4 task instruction: requires a regular nonempty UTF-8 text file',async()=>{
  const {root}=await fixture();await mkdir(path.join(root,'directory'));
  await assert.rejects(readTaskInstruction(root,'directory'),code('NOT_FILE'));
  for(const [name,data,expected] of [['binary.txt',Buffer.from([0xC3,0x28]),'INVALID_TEXT'],['nul.txt','a\0b','INVALID_TEXT'],['empty.txt',' \r\n\t','EMPTY']]) {
    await writeFile(path.join(root,name),data);await assert.rejects(readTaskInstruction(root,name),code(expected));
  }
});

test('R4 task instruction: root must be an absolute task directory',async()=>{
  await assert.rejects(readTaskInstruction('.', 'task.md'),code('INVALID_ROOT'));
  await assert.rejects(readTaskInstruction(path.parse(process.cwd()).root,'task.md'),code('INVALID_ROOT'));
});

test('R4 task instruction: refuses a linked directory even when it points inside the workspace',async t=>{
  const {root}=await fixture();const target=path.join(root,'real');await mkdir(target);await writeFile(path.join(target,'task.md'),'Public text');
  try { await symlink(target,path.join(root,'linked'),process.platform==='win32'?'junction':'dir'); }
  catch(error) { if(['EPERM','EACCES','ENOTSUP'].includes(error.code)){t.skip(`Filesystem cannot create a test link: ${error.code}`);return;}throw error; }
  await assert.rejects(readTaskInstruction(root,'linked/task.md'),code('UNSAFE_LINK'));
});

test('R4 task instruction: refuses a linked workspace root',async t=>{
  const {parent,root}=await fixture();await writeFile(path.join(root,'task.md'),'Public text');const link=path.join(parent,'alias');
  try { await symlink(root,link,process.platform==='win32'?'junction':'dir'); }
  catch(error) { if(['EPERM','EACCES','ENOTSUP'].includes(error.code)){t.skip(`Filesystem cannot create a test link: ${error.code}`);return;}throw error; }
  await assert.rejects(readTaskInstruction(link,'task.md'),code('UNSAFE_LINK'));
});

test('R4 task instruction: refuses a linked file pointing outside the task',async t=>{
  const {parent,root}=await fixture();const outside=path.join(parent,'outside.md');await writeFile(outside,'Not public task input');
  try { await symlink(outside,path.join(root,'task.md'),'file'); }
  catch(error) { if(['EPERM','EACCES','ENOTSUP'].includes(error.code)){t.skip(`Filesystem cannot create a test link: ${error.code}`);return;}throw error; }
  await assert.rejects(readTaskInstruction(root,'task.md'),code('UNSAFE_LINK'));
});
