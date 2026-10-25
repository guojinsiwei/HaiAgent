// Telemetry inside the *existing DSH Bash call*, never a second executor/run.
// Deliberately not a shell parser: unfamiliar syntax executes unchanged and its
// stage coverage remains unknown. A receipt covers top-level pipeline processes,
// not the internals of scripts, tests, child shells, or a semantic task outcome.
import { randomBytes } from 'node:crypto';

const VERSION = 1;
const PREFIX = '\x1eKZ_PIPESTATUS_V1:';
const SUFFIX = '\x1f';
const SHELL_CONTROL = new Set(['!', '{', '}', 'if', 'then', 'else', 'elif', 'fi', 'for', 'while', 'until',
  'do', 'done', 'case', 'esac', 'in', 'select', 'function', 'coproc', 'time', 'eval', 'exec', 'source', '.',
  'trap', 'set', 'shopt', 'export', 'readonly', 'declare', 'typeset', 'local', 'unset', 'return', 'exit',
  'break', 'continue', 'wait', 'jobs', 'fg', 'bg', 'disown', 'enable', 'builtin', 'command', 'hash']);

// Words retain the original source for execution. Decoded text is used only to
// recognize a narrow grammar, never to reconstruct/normalize a command.
function lex(command) {
  if (typeof command !== 'string' || !command.trim()) return { reason: 'empty_command' };
  if (/[\r\n\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/u.test(command)) return { reason: 'multiline_or_control_syntax' };
  const tokens = []; let i = 0;
  while (i < command.length) {
    if (/[ \t]/u.test(command[i])) { i++; continue; }
    const start = i;
    if (command.startsWith('&&', i)) { tokens.push({ kind: 'and', start, end: i += 2 }); continue; }
    if (command[i] === '|') {
      if ('|&'.includes(command[i + 1] ?? '\0')) return { reason: 'unsupported_control_operator' };
      tokens.push({ kind: 'pipe', start, end: ++i }); continue;
    }
    // This common fd merge is the only supported redirection. It does not open
    // files or redirect the shell's later machine receipt away from stderr.
    if (command.startsWith('2>&1', i) && (i + 4 === command.length || /[ \t|&]/u.test(command[i + 4]))) {
      tokens.push({ kind: 'redirect', start, end: i += 4 }); continue;
    }
    let value = '', literal = true, consumed = false;
    while (i < command.length && !/[ \t|&]/u.test(command[i])) {
      const ch = command[i];
      if (ch === "'") {
        const end = command.indexOf("'", i + 1);
        if (end < 0) return { reason: 'unclosed_quote' };
        value += command.slice(i + 1, end); i = end + 1; consumed = true; continue;
      }
      if (ch === '"') {
        i++; let closed = false;
        while (i < command.length) {
          if (command[i] === '"') { i++; closed = true; break; }
          if (/[\$`\\]/u.test(command[i])) return { reason: 'expansion_or_escape_syntax' };
          value += command[i++];
        }
        if (!closed) return { reason: 'unclosed_quote' };
        consumed = true; continue;
      }
      if (/[;<>`$\\(){}]/u.test(ch)) return { reason: 'unsupported_shell_syntax' };
      if (ch === '#' && !consumed) return { reason: 'comment_syntax' };
      if (/[*?\[\]~]/u.test(ch)) literal = false;
      value += ch; i++; consumed = true;
    }
    if (!consumed) return { reason: 'unsupported_control_operator' };
    tokens.push({ kind: 'word', value, literal, start, end: i });
  }
  return { tokens };
}

function simpleStage(command, tokens) {
  if (!tokens.length || tokens[0].kind !== 'word') return null;
  const exe = tokens[0].value;
  if (!/^[A-Za-z0-9_./+\-]+$/u.test(exe) || SHELL_CONTROL.has(exe) || tokens.some(t => !['word', 'redirect'].includes(t.kind))) return null;
  return { command: command.slice(tokens[0].start, tokens.at(-1).end), executable: exe };
}

function analyze(command) {
  const parsed = lex(command);
  if (parsed.reason) return parsed;
  let tokens = parsed.tokens, prefix = null;
  const ands = tokens.filter(t => t.kind === 'and');
  if (ands.length) {
    if (ands.length !== 1) return { reason: 'unsupported_conditional_list' };
    const index = tokens.findIndex(t => t.kind === 'and'), left = tokens.slice(0, index);
    const cd = simpleStage(command, left);
    // No `cd -`, HOME/CDPATH expansion, glob, variable, or extra shell action.
    // `cd` itself runs with its original spelling/options and cwd semantics.
    const words = left.map(t => t.value);
    const operand = words.length === 2 ? words[1] : words.length === 3 && words[1] === '--' ? words[2] : null;
    if (!cd || cd.executable !== 'cd' || left.some(t => t.kind !== 'word' || !t.literal) || !operand || operand.startsWith('-')) return { reason: 'unsupported_conditional_prefix' };
    prefix = cd.command; tokens = tokens.slice(index + 1);
  }
  if (!tokens.some(t => t.kind === 'pipe')) return { reason: 'not_a_pipeline' };
  const stages = []; let part = [];
  for (const token of [...tokens, { kind: 'pipe' }]) {
    if (token.kind !== 'pipe') { part.push(token); continue; }
    const stage = simpleStage(command, part);
    if (!stage) return { reason: 'unsupported_pipeline_stage' };
    stages.push(stage.command); part = [];
  }
  return { kind: prefix ? 'cd_then_pipeline' : 'single_pipeline', prefix, stages,
    pipeline: command.slice(tokens[0].start, tokens.at(-1).end) };
}

function wrap(plan) {
  const variable = `__kz_receipt_${plan.nonce}`, rc = `${variable}_rc`, ps = `${variable}_ps`, csv = `${variable}_csv`, prefix = `${variable}_prefix`;
  // One assignment-only simple command expands BOTH values before it changes
  // `$?`/PIPESTATUS. Separate assignment statements would destroy PIPESTATUS.
  const capture = `${rc}=$? ${ps}=( "\${PIPESTATUS[@]}" )`;
  // Keep even the `cd &&` conditional *exactly* as submitted. Expanding that
  // prefix into an if/else changes Bash's errexit/ERR-trap eligibility. After a
  // supported list, PIPESTATUS has >=2 entries if its pipeline ran, or one
  // nonzero cd status if short-circuiting skipped the pipeline.
  const body = `${plan.originalCommand}\n${capture}\n` + (plan.kind === 'single_pipeline'
    ? `${prefix}='-'`
    : `if [ "\${#${ps}[@]}" -eq 1 ]; then\n${prefix}=\${${ps}[0]}\n${ps}=()\nelse\n${prefix}=0\nfi`);
  return `${body}\nif [ "\${#${ps}[@]}" -gt 0 ]; then\n` +
    `builtin printf -v ${csv} '%s,' "\${${ps}[@]}"\n${csv}=\${${csv}%,}\nelse\n${csv}='-'\nfi\n` +
    `builtin printf '\\036KZ_PIPESTATUS_V1:${plan.nonce}:%s:%s:%s\\037' "$${rc}" "$${prefix}" "$${csv}" >&2\nbuiltin exit "$${rc}"`;
}

/** Call only after the original host permission/budget/policy checks. DSH still
 * performs execution, sandbox escalation, deadlines and background promotion.
 * The deployment must explicitly attest that its executor is POSIX Bash.
 * `args` is original/unmodified; only `executionArgs.command` is instrumented.
 */
export function prepareShellReceipt(args, { enabled = false } = {}) {
  const base = { instrumented: false, args, executionArgs: args };
  const parsed = enabled === true ? analyze(args?.command) : { reason: 'capability_disabled' };
  if (parsed.reason) return { ...base, plan: { version: VERSION, instrumented: false, originalCommand: args?.command ?? '', reason: parsed.reason } };
  const plan = { version: VERSION, instrumented: true, originalCommand: args.command, nonce: randomBytes(16).toString('hex'), ...parsed,
    scope: 'top_level_pipeline_stages_only', nestedProgramsVerified: false };
  return { instrumented: true, args, executionArgs: { ...args, command: wrap(plan) }, plan };
}

function unknown(observation, plan, reason) {
  return { ...observation, shellStageReceipt: { status: 'unknown', scope: 'top_level_pipeline_stages_only',
    kind: plan?.kind ?? null, reason, stages: [], allSucceeded: null, nestedProgramsVerified: false } };
}

/** Consume only raw, channel-separated native observations BEFORE ANSI cleanup.
 * A random correlation token is not cryptographic attestation against adversarial
 * programs that inspect their parent's command line. This is shell telemetry,
 * never a model's self-reported `passed`, nor proof the task/tests are correct.
 * Save the original native result as usual; receiptRaw retains exact removed bytes.
 */
export function consumeShellReceipt(plan, observation) {
  if (!plan?.instrumented) return unknown(observation, plan, plan?.reason ?? 'not_instrumented');
  if (plan.version !== VERSION || !/^[a-f0-9]{32}$/u.test(plan.nonce ?? '')) return unknown(observation, plan, 'invalid_plan');
  const expected = analyze(plan.originalCommand);
  if (expected.reason || expected.kind !== plan.kind || expected.prefix !== plan.prefix || expected.pipeline !== plan.pipeline ||
    JSON.stringify(expected.stages) !== JSON.stringify(plan.stages)) return unknown(observation, plan, 'invalid_plan');
  if (observation?.executed !== true || observation.complete !== true || observation.nativeToolError ||
    observation.timedOut || observation.aborted || observation.stopped || observation.signal || observation.truncated ||
    observation.sandbox?.denied || observation.sandbox?.runnerFailed || observation.runnerFailed || observation.denied ||
    observation.lossy || observation.channelUnknown || observation.outputCoverage === 'partial_or_rendered' ||
    observation.jobStage && observation.jobStage !== 'final' || observation.jobStatus && observation.jobStatus !== 'completed' ||
    !Number.isInteger(observation.exitCode) || observation.exitCode < 0 || observation.exitCode > 255 ||
    typeof observation.stdout !== 'string' || typeof observation.stderr !== 'string')
    return unknown(observation, plan, 'native_execution_or_stream_incomplete');
  const start = `${PREFIX}${plan.nonce}:`, stderr = observation.stderr;
  const at = stderr.indexOf(start);
  if (at < 0) return unknown(observation, plan, 'receipt_missing');
  if (stderr.indexOf(start, at + start.length) >= 0) return unknown(observation, plan, 'receipt_duplicate');
  const end = stderr.indexOf(SUFFIX, at + start.length);
  if (end < 0) return unknown(observation, plan, 'receipt_incomplete');
  const fields = stderr.slice(at + start.length, end).split(':');
  const code = value => /^(?:0|[1-9]\d{0,2})$/u.test(value) && Number(value) <= 255 ? Number(value) : null;
  if (fields.length !== 3) return unknown(observation, plan, 'receipt_malformed');
  const shellExitCode = code(fields[0]), prefixExitCode = fields[1] === '-' ? null : code(fields[1]);
  const codes = fields[2] === '-' ? [] : fields[2].split(',').map(code);
  const hasPrefix = plan.kind === 'cd_then_pipeline';
  if (shellExitCode === null || shellExitCode !== observation.exitCode || codes.some(x => x === null) ||
    hasPrefix && prefixExitCode === null || !hasPrefix && fields[1] !== '-') return unknown(observation, plan, 'receipt_native_status_mismatch');
  const executed = !hasPrefix || prefixExitCode === 0;
  if (executed ? codes.length !== plan.stages.length : codes.length !== 0 || shellExitCode !== prefixExitCode)
    return unknown(observation, plan, 'receipt_stage_count_mismatch');
  // PIPESTATUS can differ from $? under pipefail; both normal modes are valid.
  // Any other status is inconsistent with a captured, ordinary top-level pipe.
  if (executed && shellExitCode !== codes.at(-1) && shellExitCode !== ([...codes].reverse().find(x => x !== 0) ?? 0))
    return unknown(observation, plan, 'receipt_pipeline_status_inconsistent');
  const stages = plan.stages.map((command, index) => ({ index, command, executed, exitCode: executed ? codes[index] : null }));
  const receiptRaw = stderr.slice(at, end + SUFFIX.length);
  return { ...observation, stderr: stderr.slice(0, at) + stderr.slice(end + SUFFIX.length), receiptRaw,
    shellStageReceipt: { status: 'verified', scope: 'top_level_pipeline_stages_only', kind: plan.kind,
      stages, prefix: hasPrefix ? { command: plan.prefix, executed: true, exitCode: prefixExitCode } : null,
      shellExitCode, allSucceeded: executed && codes.every(x => x === 0), nestedProgramsVerified: false } };
}
