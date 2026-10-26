import fs from 'node:fs';
export function descendants(root, proc='/proc') {
  const rows=[];
  for(const name of fs.readdirSync(proc)) {
    if(!/^\d+$/.test(name))continue;
    try {
      const raw=fs.readFileSync(`${proc}/${name}/stat`,'utf8');
      const cols=raw.slice(raw.lastIndexOf(')')+2).trim().split(/\s+/);
      rows.push({pid:Number(name),ppid:Number(cols[1]),start:cols[19]});
    } catch {}
  }
  const selected=new Set([root]);
  for(let n=0;n<rows.length;n++)for(const r of rows)if(selected.has(r.ppid))selected.add(r.pid);
  return rows.filter(r=>selected.has(r.pid));
}
export function signalOwned(rows, signal, proc='/proc', kill=process.kill) {
  for(const row of [...rows].reverse()) {
    try {
      const raw=fs.readFileSync(`${proc}/${row.pid}/stat`,'utf8');
      const cols=raw.slice(raw.lastIndexOf(')')+2).trim().split(/\s+/);
      if(cols[19]===row.start)kill(row.pid,signal);
    } catch {}
  }
}
export function deadline(child, seconds, receipt, graceMs=15000) {
  let owned=[], expired=false, grace;
  const terminate=(reason='solver_wall_limit_3h')=>{
    if(expired)return;expired=true;owned=descendants(child.pid);
    try{receipt({state:'terminating',reason,limit_seconds:seconds});}catch{}
    signalOwned(owned,'SIGTERM');
    grace=setTimeout(()=>{signalOwned(owned,'SIGKILL');try{receipt({state:'enforced',reason,limit_seconds:seconds});}catch{}},graceMs);
  };
  const timer=setTimeout(terminate,seconds*1000);
  return {terminate,finish(){clearTimeout(timer);if(!expired)clearTimeout(grace);},get expired(){return expired;}};
}
