"""Audit known xv6 boot-test substitutions without reverting unknown edits."""
import re
import ast
from pathlib import Path


_C_TOKENS = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_]\w*|[^\s]', re.S)


def _literal(tokens):
    if not tokens or not all(t.startswith('"') for t in tokens):
        return None
    try:
        value = ''.join(ast.literal_eval(t) for t in tokens)
    except (ValueError, SyntaxError):
        return None
    return value if re.fullmatch(r'[A-Za-z0-9_./-]+', value) else None


def boot_dispatch(text):
    """Bounded C lexical inspection, not a compiler/reachability proof.

    Strip comments without reading strings as code. Variable/computed dispatch
    stays unverified: an assignment alone does not prove its runtime value.
    """
    text = re.sub(r'\\\r?\n', '', text)  # C line splicing precedes comment removal.
    tokens = [m.group() for m in _C_TOKENS.finditer(text)
              if not m.group().startswith(('//', '/*'))]
    programs, unknown = [], 0
    for i in range(len(tokens)-2):
        if tokens[i:i+2] != ['exec', '(']:
            continue
        argument, j, depth = [], i+2, 0
        while j < len(tokens):
            token = tokens[j]
            if depth == 0 and token in (',', ')'):
                break
            depth += int(token == '(') - int(token == ')')
            argument.append(token); j += 1
        value = _literal(argument)
        if value is None:
            unknown += 1
        else:
            programs.append(value)
    return dict(programs=programs, unresolved_calls=unknown)


def boot_programs(text):
    return boot_dispatch(text)['programs']


class BootDeliveryGuard:
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve(strict=True)
        self.baselines = {}
        for folder in [self.workspace, *sorted(self.workspace.iterdir())]:
            init = folder / 'user/init.c'
            if (folder.is_symlink() or not (folder/'kernel/proc.c').is_file()
                    or not (folder/'Makefile').is_file() or not init.is_file()):
                continue
            if not init.resolve().is_relative_to(self.workspace) or init.stat().st_size > 65536:
                continue
            text = init.read_text(encoding='utf-8', errors='replace')
            if 'sh' in boot_programs(text):
                self.baselines[init.relative_to(self.workspace).as_posix()] = boot_programs(text)

    def check(self):
        issues = []
        for name, original in self.baselines.items():
            init = self.workspace / name
            if (init.is_symlink() or not init.is_file()
                    or not init.resolve().is_relative_to(self.workspace)
                    or init.stat().st_size > 65536):
                issues.append(dict(path=name, reason='boot_source_missing_or_unsafe'))
                continue
            try:
                dispatch = boot_dispatch(init.read_text(encoding='utf-8', errors='replace'))
            except OSError:
                issues.append(dict(path=name, reason='boot_source_unreadable'))
                continue
            programs = dispatch['programs']
            replacements = [p for p in programs if p not in original]
            if replacements:
                issues.append(dict(path=name, reason='test_program_replaced_boot_shell',
                                   programs=replacements, original_programs=original))
            if 'sh' not in programs:
                issues.append(dict(path=name, reason='boot_shell_dispatch_missing_or_unverified'))
            if dispatch['unresolved_calls']:
                issues.append(dict(path=name, reason='boot_dispatch_unverified',
                                   unresolved_calls=dispatch['unresolved_calls']))
        return dict(passed=not issues, issues=issues, source='public_starter_boot_dispatch',
                    task_success=None, automatic_revert=False,
                    instruction='Restore temporary test-only boot substitutions before delivery. '
                                'Do not revert unrelated implementation changes. '
                                'This audit does not establish overall correctness.')
