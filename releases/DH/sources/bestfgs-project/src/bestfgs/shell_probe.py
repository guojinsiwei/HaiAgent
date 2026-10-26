"""Bounded Bash status observations. Not a sandbox or proof of check success.

Only top-level Bash -c/-lc is instrumented. Nested shells, exec, overwritten
traps and deliberate status masking are reported as partial/unknown coverage.
The command's exit status and pipefail setting are never changed.
"""
import json
import re
from pathlib import Path
import shlex
import tempfile
import uuid


def prepare_trace(action):
    args = list(action.get('argv', []))
    if len(args) < 3 or Path(args[0]).name != 'bash' or args[1] not in ('-c', '-lc'):
        return dict(action), None
    directory = tempfile.TemporaryDirectory(prefix='bestfgs-status-')
    path = Path(directory.name) / 'trace'
    token = uuid.uuid4().hex
    # A separate file descriptor keeps observations out of task stdout/pipelines.
    # Expansion at trap entry captures PIPESTATUS before any helper runs.
    preamble = r'''
exec {__fgs_status_fd}>TRACE_PATH
__fgs_status_pid=$BASHPID
__fgs_status_count=0
__fgs_status_record() {
  if [[ $BASHPID == "$__fgs_status_pid" ]]; then
    if [[ $__fgs_status_count -lt 128 ]]; then
      printf 'TOKEN|step|%s|%s\n' "$1" "$2" >&$__fgs_status_fd
    fi
    __fgs_status_count=$((__fgs_status_count+1))
  fi
  return 0
}
__fgs_status_exit() {
  __fgs_status_record "$1" "$2"
  printf 'TOKEN|end|%s|%s\n' "$1" "$__fgs_status_count" >&$__fgs_status_fd
}
trap '__fgs_status_record "$?" "${PIPESTATUS[*]}"' DEBUG
trap '__fgs_status_exit "$?" "${PIPESTATUS[*]}"' EXIT
'''.replace('TRACE_PATH', shlex.quote(str(path))).replace('TOKEN', token)
    args[2] = preamble + '\n' + args[2]
    # Commands installing their own traps may replace this observer. Treat
    # coverage conservatively even when an EXIT footer survives.
    modifies_traps = bool(re.search(r'\btrap\b', action['argv'][2]))
    return dict(action, argv=args), (directory, path, token, modifies_traps)


def finish_trace(handle):
    if handle is None:
        return dict(coverage='not_instrumented', pipelines=[], nonzero_statuses=[], complete=False)
    directory, path, token, modifies_traps = handle
    try:
        if path.exists():
            with path.open('rb') as stream:
                captured=stream.read(65536)
            rows=captured.decode(errors='replace').splitlines()
        else:
            rows=[]
        pipelines, failures, ended, count = [], [], False, 0
        for line in rows:
            parts = line.split('|')
            if len(parts) != 4 or parts[0] != token:
                continue
            try:
                if parts[1] == 'end':
                    ended, count = True, int(parts[3])
                elif parts[1] == 'step':
                    codes = [int(x) for x in parts[3].split()]
                    if len(codes) > 1:
                        pipelines.append(codes)
                    if int(parts[2]) != 0 or any(codes):
                        failures.append(dict(shell_status=int(parts[2]), stages=codes))
            except ValueError:
                continue
        return dict(coverage='top_level_bash_only', complete=ended and count <= 128 and not modifies_traps,
                    command_may_modify_traps=modifies_traps,
                    trace_truncated=count > 128, pipelines=pipelines,
                    nonzero_statuses=failures,
                    notice='Nonzero stages may be handled intentionally (grep no-match, head SIGPIPE, || recovery). Not task failure proof.')
    finally:
        directory.cleanup()
