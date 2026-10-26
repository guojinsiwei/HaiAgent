import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { lstat, open, realpath } from 'node:fs/promises';
import path from 'node:path';

export class TaskInstructionError extends Error {
  constructor(code,message,cause) { super(message,cause?{cause}:undefined);this.name='TaskInstructionError';this.code=`TASK_INSTRUCTION_${code}`; }
}
const fail = (code,message) => { throw new TaskInstructionError(code,message); };
const privateComponent = /^(?:hidden[-_]?tests?|private[-_]?tests?|verifier|grader|grading|oracle|solutions?|secrets?|credentials?)$/iu;
const privateFile = /^(?:id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|(?:api[-_]?key|access[-_]?token|credentials?)(?:\.[^/]*)?)$/iu;
function checkedName(value) {
  if (typeof value!=='string' || value!==value.trim() || !value || /[\\\x00-\x1f\x7f:]/u.test(value) || path.posix.isAbsolute(value) || path.win32.isAbsolute(value)) fail('INVALID_PATH','Task instruction must be an explicit workspace-relative public file path.');
  const parts=value.split('/');
  if (parts.some(part=>!part || part==='.' || part==='..' || part.startsWith('.') || privateComponent.test(part) || privateFile.test(part))) fail('INVALID_PATH','Task instruction cannot use traversal, hidden, credential, or evaluator/solution paths.');
  return {name:value,parts};
}
async function inspect(root,parts) {
  let cursor=root,stat;
  for (let index=0;index<parts.length;index++) {
    cursor=path.join(cursor,parts[index]);stat=await lstat(cursor);
    if (stat.isSymbolicLink()) fail('UNSAFE_LINK','Task instruction must not traverse symbolic links.');
    if (index<parts.length-1&&!stat.isDirectory()) fail('NOT_FILE','Task instruction parent must be a directory.');
  }
  if (!stat.isFile()) fail('NOT_FILE','Task instruction must be a regular text file.');
  const resolved=await realpath(cursor),relative=path.relative(root,resolved);
  if (!relative || relative==='..' || relative.startsWith('..'+path.sep) || path.isAbsolute(relative)) fail('OUTSIDE_ROOT','Task instruction resolved outside its task workspace.');
  return {file:cursor,stat};
}
const sameFile = (a,b) => a.dev===b.dev&&a.ino===b.ino&&a.size===b.size&&a.mtimeMs===b.mtimeMs;

// Explicit public input only: never infer a README, search the workspace, truncate
// task requirements, or fall back to a potentially contradictory wrapper prompt.
export async function readTaskInstruction(root,relativePath) {
  if (relativePath===undefined || relativePath===null || relativePath==='') return null;
  const {name,parts}=checkedName(relativePath);
  let handle;
  try {
    if (typeof root!=='string'||!path.isAbsolute(root)||path.resolve(root)===path.parse(path.resolve(root)).root) fail('INVALID_ROOT','Task instruction requires an absolute task directory, not a filesystem root.');
    const rootStat=await lstat(root);
    if (rootStat.isSymbolicLink()) fail('UNSAFE_LINK','Task instruction workspace root must not be a symbolic link.');
    if (!rootStat.isDirectory()) fail('INVALID_ROOT','Task instruction workspace root must be a directory.');
    const canonicalRoot=await realpath(root),before=await inspect(canonicalRoot,parts);
    handle=await open(before.file,constants.O_RDONLY|(constants.O_NOFOLLOW??0));
    const opened=await handle.stat();
    if (!opened.isFile()||!sameFile(before.stat,opened)) fail('CHANGED','Task instruction changed while being opened.');
    const bytes=await handle.readFile(),after=await handle.stat(),pathAfter=await inspect(canonicalRoot,parts);
    if (!sameFile(opened,after)||!sameFile(after,pathAfter.stat)||bytes.length!==after.size) fail('CHANGED','Task instruction changed while being read; retry with a stable public file.');
    let text;
    try { text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes); }
    catch (error) { throw new TaskInstructionError('INVALID_TEXT','Task instruction is not valid UTF-8 text.',error); }
    if (/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/u.test(text)) fail('INVALID_TEXT','Task instruction contains binary/control bytes, not plain public task text.');
    if (!text.trim()) fail('EMPTY','Configured task instruction is empty.');
    return {text,path:name,sha256:createHash('sha256').update(bytes).digest('hex')};
  } catch (error) {
    if (error instanceof TaskInstructionError) throw error;
    throw new TaskInstructionError(error.code==='ENOENT'?'MISSING':'READ_FAILED',`Cannot read configured public task instruction (${error.code??'unknown filesystem error'}).`,error);
  } finally { await handle?.close(); }
}
