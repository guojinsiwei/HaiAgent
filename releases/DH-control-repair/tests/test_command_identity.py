import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'sources/bestfgs-project/src'))
from bestfgs.lean_memory import action_key


def shell(command, **extra):
    return dict(action='run', argv=['bash','-lc',command], cwd='.', **extra)


def old_key(action):
    value = [action.get('argv'),action.get('cwd','.'),action.get('stdin') or '']
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


class CommandIdentityTests(unittest.TestCase):
    def test_outer_spaces_and_tabs_are_equivalent(self):
        self.assertEqual(action_key(shell('python guard.py')),
                         action_key(shell('  python\t  guard.py  ')))

    def test_literal_argument_quoting_is_equivalent(self):
        for variant in ('python "guard.py"', "python 'guard.py'", "python gu'ard'.py"):
            with self.subTest(variant=variant):
                self.assertEqual(action_key(shell('python guard.py')),action_key(shell(variant)))

    def test_escaped_literal_space_is_equivalent_to_quoted_space(self):
        self.assertEqual(action_key(shell(r'python check.py path\ name')),
                         action_key(shell('python check.py "path name"')))

    def test_quoted_whitespace_is_not_collapsed(self):
        self.assertNotEqual(action_key(shell('python check.py "a  b"')),
                            action_key(shell('python check.py "a b"')))
        self.assertNotEqual(action_key(shell('python check.py "a\tb"')),
                            action_key(shell('python check.py "a b"')))

    def test_quoted_argument_is_not_split(self):
        self.assertNotEqual(action_key(shell('python check.py "a b"')),
                            action_key(shell('python check.py a b')))

    def test_quoted_operator_remains_literal_data(self):
        self.assertEqual(action_key(shell('python check.py ";"')),
                         action_key(shell("  python check.py ';'  ")))
        self.assertNotEqual(action_key(shell('python check.py ";"')),
                            action_key(shell('python check.py ;')))

    def test_real_argument_changes_order_and_options_remain_distinct(self):
        original = action_key(shell('python train.py --lr 0.01 --verbose'))
        for command in ('python train.py --lr 0.001 --verbose', 'python train.py --lr 0.01',
                        'python train.py --verbose --lr 0.01', 'pip install A', 'pip uninstall A'):
            with self.subTest(command=command):
                self.assertNotEqual(original,action_key(shell(command)))
        self.assertNotEqual(action_key(shell('pip install A')),action_key(shell('pip uninstall A')))

    def test_direct_argv_preserves_spaces_and_legacy_hash(self):
        one = dict(action='run',argv=['python','check.py','a  b'])
        two = dict(action='run',argv=['python','check.py','a b'])
        self.assertNotEqual(action_key(one),action_key(two))
        self.assertEqual(action_key(one),old_key(one))

    def test_cwd_stdin_shell_and_shell_flags_remain_distinct(self):
        original = shell('python guard.py')
        for variant in (dict(original,cwd='subdir'),dict(original,stdin='new input'),
                        dict(original,argv=['sh','-lc','python guard.py']),
                        dict(original,argv=['bash','-c','python guard.py'])):
            with self.subTest(variant=variant):
                self.assertNotEqual(action_key(original),action_key(variant))

    def test_purpose_and_decision_text_are_not_identity(self):
        original = shell('python guard.py')
        self.assertEqual(action_key(original),action_key(dict(original,purpose='claim new route',
            strategy_adjustment='claim changed approach',uses_memory=['M1'])))

    def test_extra_shell_parameters_use_raw_identity(self):
        action = dict(action='run',argv=['bash','-c','python "$1"','arg0','guard.py'])
        self.assertEqual(action_key(action),old_key(action))

    def test_alias_sensitive_command_word_spelling_is_preserved(self):
        self.assertNotEqual(action_key(shell('python guard.py')),action_key(shell('"python" guard.py')))
        self.assertEqual(action_key(shell('"python" guard.py')),action_key(shell('  "python"  guard.py  ')))

    def test_control_expansion_and_malformed_shell_keep_raw_identity(self):
        commands = ('python *.py', 'echo ~', 'echo "$HOME"', "echo '$HOME'", 'echo `date`',
            'echo $(date)', 'cat a | cat', 'cat a > out', 'cat a && cat b', 'cat a; cat b',
            'cat a # comment', 'cat a\ncat b', 'cat <<EOF\nx\nEOF', '(cat a)',
            'if true; then cat a; fi', 'time python guard.py', 'VAR=1 python guard.py',
            'python "unterminated', 'python trailing\\', '  ', 'echo {a,b}',
            'python\r guard.py', 'cat\x00a')
        for command in commands:
            with self.subTest(command=command):
                action = shell(command)
                self.assertEqual(action_key(action),old_key(action))

    def test_identity_never_mutates_executed_command(self):
        action = shell('  python  "a  b.py"  ')
        before = copy.deepcopy(action)
        action_key(action)
        self.assertEqual(action,before)


if __name__ == '__main__': unittest.main()
