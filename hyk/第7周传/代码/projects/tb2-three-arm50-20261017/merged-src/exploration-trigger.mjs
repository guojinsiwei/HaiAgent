import path from 'node:path';

// Grouping is only a recovery trigger. It never proves action equivalence or
// authorizes cached results. Unknown shell programs retain exact identity.
export function checkIdentity(command, cwd = '.') {
  let text = String(command), directory = cwd;
  const cd = text.match(/^\s*cd\s+(['"]?)([^\s;'"&|]+)\1\s*&&\s*/u);
  if (cd) { directory = path.posix.normalize(path.posix.join(cwd, cd[2])); if(cd[2].startsWith('/'))directory=path.posix.normalize(cd[2]); text=text.slice(cd[0].length); }
  if (!text.includes('<<')) {
    const build = text.match(/(?:^|[;&|]\s*)(gcc|g\+\+|cc|c\+\+)\s+([^;\n|&]+)/u);
    if (build && !/[$`\\]/u.test(build[2])) {
      const sources = [...build[2].matchAll(/(?:^|\s)([^\s'"<>]+\.(?:c|cc|cpp|cxx))(?=\s|$)/gu)].map(m=>m[1]).sort();
      if (sources.length) return JSON.stringify(['build',directory,sources]);
    }
    const telnet = text.match(/(?:^|[;|&]\s*|\btimeout\s+\d+\s+)telnet\s+([\w.-]+)\s+(\d+)\b/u);
    if (telnet) return JSON.stringify(['telnet',directory,telnet[1],telnet[2]]);
  }
  return JSON.stringify(['exact',directory,text.trim()]);
}

export class ExplorationTrigger {
  constructor(state = {}, capacity = 24) {
    this.state=state; this.capacity=capacity;
    state.checks??=[];state.seen??=[];state.blockedEvidence??=[];state.lastDecision??=null;
  }
  observe(key, evidence, status) {
    if(!['failed','passed'].includes(status)||this.state.seen.includes(evidence))return;
    this.state.seen.push(evidence);this.state.seen=this.state.seen.slice(-1024);
    let row=this.state.checks.find(x=>x.key===key);
    if(status==='passed') {this.state.checks=this.state.checks.filter(x=>x.key!==key);return;}
    if(!row){row={key,failures:0,evidence:[],blocked:false};this.state.checks.push(row);}
    row.failures++;row.evidence.push(evidence);row.evidence=row.evidence.slice(-4);
    // Reads, edits, uncertain observations and changed error text do not erase
    // this ledger. A clean completion of this same check closes it.
    this.state.checks=this.state.checks.filter(x=>x!==row).concat(row).slice(-this.capacity);
  }
  blocked(key,evidence) {
    const row=this.state.checks.find(x=>x.key===key);
    if(!row||this.state.blockedEvidence.includes(evidence))return;
    this.state.blockedEvidence.push(evidence);this.state.blockedEvidence=this.state.blockedEvidence.slice(-1024);
    row.blocked=true;
  }
  pending(threshold,key=null) {return this.state.checks.find(x=>(key===null||x.key===key)&&(x.failures>=threshold||x.blocked));}
  consume(row) {
    const decision={key:row.key,failures:row.failures,evidence:[...row.evidence],reason:row.blocked?'repeated_failure_request':'same_check_failed_again'};
    row.failures=0;row.blocked=false;this.state.lastDecision=decision;return decision;
  }
  retirePending() {for(const row of this.state.checks){row.failures=0;row.blocked=false;}}
}
