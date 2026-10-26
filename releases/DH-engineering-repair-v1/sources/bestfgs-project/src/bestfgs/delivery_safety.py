"""Audit known xv6 boot-test substitutions without reverting unknown edits."""
import re
from pathlib import Path


def boot_programs(text):
    return re.findall(r'\bexec\s*\(\s*"([A-Za-z0-9_-]+)"\s*,', text)


class BootDeliveryGuard:
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve(strict=True)
        self.baselines = {}
        for folder in sorted(self.workspace.iterdir()):
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
            programs = boot_programs(init.read_text(encoding='utf-8', errors='replace'))
            folder = init.parent.parent
            replacements = [p for p in programs if p not in original
                            and (folder/'user'/f'{p}.c').is_file()]
            if 'sh' not in programs and replacements:
                issues.append(dict(path=name, reason='test_program_replaced_boot_shell',
                                   programs=replacements, original_programs=original))
        return dict(passed=not issues, issues=issues, source='public_starter_boot_dispatch',
                    task_success=None, automatic_revert=False,
                    instruction='Restore temporary test-only boot substitutions before delivery. '
                                'Do not revert unrelated implementation changes. '
                                'This audit does not establish overall correctness.')
