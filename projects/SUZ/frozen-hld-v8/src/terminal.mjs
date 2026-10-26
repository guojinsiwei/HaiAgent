// Port of terminal_text.py / prompt_views.py / tool_outcomes.py.
// Model projections never overwrite the native tool result.
import { createHash } from 'node:crypto';
import { maskedStages } from './commands.mjs';

export const hashText = text => createHash('sha256').update(text).digest('hex');
export function projectTerminal(value) {
  let out = '', removed = 0, incomplete = false;
  for (let i = 0; i < value.length;) {
    let ch = value[i], kind = null;
    if (ch === '\x1b') {
      ch = value[++i];
      if (ch === undefined) { incomplete = true; break; }
      kind = ch === '[' ? 'csi' : ch === ']' ? 'osc' : 'P^_X'.includes(ch) ? 'string' : 'escape'; i++;
    } else if ('\x9b\x9d\x90\x9e\x9f\x98'.includes(ch)) {
      kind = ch === '\x9b' ? 'csi' : ch === '\x9d' ? 'osc' : 'string'; i++;
    }
    if (kind) {
      removed++;
      if (kind === 'csi') {
        while (i < value.length && /[0-?]/u.test(value[i])) i++;
        while (i < value.length && /[ -/]/u.test(value[i])) i++;
        if (i < value.length && /[@-~]/u.test(value[i])) i++; else incomplete = true;
      } else if (kind === 'osc' || kind === 'string') {
        let ended = false;
        while (i < value.length) {
          if (value.startsWith('\x1b\\', i)) { i += 2; ended = true; break; }
          if (value[i] === '\x9c' || kind === 'osc' && value[i] === '\x07') { i++; ended = true; break; }
          i++;
        }
        if (!ended) incomplete = true;
      } else if (/[ -/]/u.test(ch)) {
        while (i < value.length && /[ -/]/u.test(value[i])) i++;
        if (i < value.length && /[0-~]/u.test(value[i])) i++; else incomplete = true;
      } else if (!/[0-~]/u.test(ch)) incomplete = true;
      continue;
    }
    if (ch === '\r') { out += '\n'; i += value[i + 1] === '\n' ? 2 : 1; continue; }
    if (/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/u.test(ch)) { removed++; i++; continue; }
    out += ch; i++;
  }
  return { text: out, controlsRemoved: removed, incomplete, cursorRewritesApplied: false };
}

export function classify(command) {
  if (/[;&|<>`$\n\r]/u.test(command)) return 'generic';
  if (/^(?:\S*\/)?(?:pytest|py\.test)\b|^python[\d.]*\s+-m\s+(pytest|unittest|doctest)\b|^(npm|cargo|go)\s+test\b/u.test(command)) return 'test';
  if (/^(ls|find|tree)\b/u.test(command)) return 'listing';
  if (/^(rg|grep)\b/u.test(command)) return 'search';
  if (/^(cat|head|tail|sed)\b/u.test(command)) return 'read';
  if (/^git\s+diff\b/u.test(command)) return 'diff';
  if (/^(make|cmake|ninja|gcc|g\+\+|cargo)\b/u.test(command)) return 'build';
  if (/^(pip3?|npm|uv)\b|^python[\d.]*\s+-m\s+pip\b/u.test(command)) return 'install';
  return 'generic';
}
export function clip(text, chars) {
  // Role data can contain structured next_step objects. Render those as data;
  // never execute or interpret them while constructing another role's context.
  if(typeof text!=='string')text=text==null?'':JSON.stringify(text)??String(text);
  if (text.length <= chars) return text;
  const marker = '\n[... display omitted; full evidence retained ...]\n';
  if (chars <= marker.length) return '[display omitted]'.slice(0, chars);
  const n = Math.floor((chars - marker.length) / 2);
  return text.slice(0, n) + marker + text.slice(-(chars - marker.length - n));
}
export function stageReceiptView(receipt) {
  if(!receipt)return null;
  return {status:receipt.status,scope:receipt.scope,reason:receipt.reason,allSucceeded:receipt.allSucceeded,
    stages:(receipt.stages??[]).slice(0,12).map(({index,command,executed,exitCode})=>({index,command:clip(command??'',100),executed,exitCode})),
    stage_count:receipt.stages?.length??0,details_partial:(receipt.stages?.length??0)>12,
    prefix:receipt.prefix?{command:clip(receipt.prefix.command,100),exitCode:receipt.prefix.exitCode}:null,
    nestedProgramsVerified:false,taskSuccess:null};
}
export function extractStream(text, category, chars = 4000) {
  if(typeof text!=='string')text=text==null?'':JSON.stringify(text)??String(text);
  if (text.length <= chars) return text;
  if (category==='read') return clip(text, chars);
  const lines = text.split('\n'), chosen = new Set(); let used = 120;
  const add = i => { if (i >= 0 && i < lines.length && !chosen.has(i) && used + lines[i].length + 32 < chars) {
    chosen.add(i); used += lines[i].length + 32;
  } };
  const matches = [];
  for (let i = 0; i < lines.length; i++) if (/error|fail|exception|traceback|assert|denied|not found|warning|\bpassed\b|skipped/iu.test(lines[i]) || category === 'diff' && /^(diff --git|---|\+\+\+|@@)/u.test(lines[i])) matches.push(i);
  for (const i of [...matches.slice(0, 4), ...matches.slice(-4)]) add(i);
  for (let i = lines.length - 6; i < lines.length; i++) add(i);
  for (const i of matches) { add(i - 1); add(i); add(i + 1); }
  for (let i = 0; i < lines.length; i++) add(i);
  return clip('[excerpt only; missing lines do not prove absence]\n' + [...chosen].sort((a,b) => a-b).map(i => `[L${i+1}] ${lines[i]}`).join('\n'), chars);
}
export function extractOutcome(args, observation) {
  const stdout = projectTerminal(observation.stdout), stderr = projectTerminal(observation.stderr);
  const category = classify(args.command ?? ''), combined = stdout.text + '\n' + stderr.text;
  const traceback = /Traceback \(most recent call last\):/u.test(combined) && /\b(?:\w*Error|\w*Exception):/u.test(combined);
  const failedSummary = /\b[1-9]\d* (failed|errors?)\b/iu.test(combined) && category === 'test' || /^(FAILED|FAIL:|ERROR:)/mu.test(combined);
  const receipt=observation.shellStageReceipt;
  const verifiedStages=receipt?.status==='verified';
  const shellStagesUnknown = maskedStages(args.command ?? '')&&!verifiedStages;
  const pipelineNonzero=verifiedStages&&!receipt.allSucceeded;
  const suspect = traceback || failedSummary;
  const complete = observation.complete && !stdout.incomplete && !stderr.incomplete;
  const noMatch = category === 'search' && observation.exitCode === 1 && !stderr.text.trim() && complete;
  const clean = complete && observation.executed===true && !observation.nativeToolError && observation.exitCode === 0 && !suspect && !shellStagesUnknown && !pipelineNonzero;
  const pytest = /^(?:pytest|py\.test)\b|^python[\d.]*\s+-m\s+pytest\b/u.test(args.command ?? '');
  const checkStatus = pytest && clean && /=+ .*\b[1-9]\d* passed\b.* =+/u.test(combined) && !/\b[1-9]\d* (failed|errors?)\b/u.test(combined)
    ? 'public_check_passed' : 'unknown';
  return { ...observation, stdout: stdout.text, stderr: stderr.text, complete, clean, suspect, noMatch, category,
    checkStatus, pipelineNonzero, shellStageCoverage:verifiedStages?'verified_top_level_pipeline':shellStagesUnknown?'unknown_composite_statuses':'top_level_exit_only', failureObserved: complete && observation.executed===true && !observation.nativeToolError && Number.isInteger(observation.exitCode) && observation.exitCode !== 0 && !noMatch,
    rawHashes: { stdout: hashText(observation.stdout), stderr: hashText(observation.stderr) },
    projection: { stdout, stderr }, taskSuccess: null };
}
