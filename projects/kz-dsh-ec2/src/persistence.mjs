import { renameSync } from 'node:fs';

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
