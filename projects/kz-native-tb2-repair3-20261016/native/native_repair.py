"""General protocol repair for standalone KZ. No benchmark-specific knowledge."""
from copy import deepcopy
from pathlib import Path
import shlex
from bestfgs.error_routing import RoutedTaskRunner
from bestfgs.subgoals import SubgoalLedger
from bestfgs.lean_memory import action_key
from bestfgs.models import ModelCallError
from provider_policy import ProviderQuotaUnavailable


class RepairLedger(SubgoalLedger):
    def __init__(self, workspace, emit):
        super().__init__(emit)
        self.workspace = Path(workspace).resolve()
        self.rejected_plan = None
        self.plan_error = None

    def relative(self, value):
        if not isinstance(value, str):
            return value
        path = Path(value)
        if not path.is_absolute():
            return value
        try:
            return path.resolve().relative_to(self.workspace).as_posix()
        except ValueError:
            raise ValueError('subgoal path is outside the task workspace') from None

    def normalize(self, action):
        value = deepcopy(action)
        plan = value.get('subgoal_plan')
        if isinstance(plan, list):
            for row in plan:
                if not isinstance(row, dict):
                    continue
                if isinstance(row.get('targets'), list):
                    row['targets'] = [self.relative(p) for p in row['targets']]
                verification = row.get('verification')
                if isinstance(verification, dict) and 'cwd' in verification:
                    verification['cwd'] = self.relative(verification['cwd'])
        return value

    def check_identity(self, action):
        """Recognize only a literal shell wrapper, never arbitrary shell equivalence."""
        argv = action.get('argv', [])
        cwd = action.get('cwd', '.')
        cwd = str((self.workspace / cwd).resolve())
        if len(argv) == 3 and argv[0] in ('bash', 'sh', '/bin/bash', '/bin/sh') and argv[1] in ('-c', '-lc'):
            source = argv[2]
            # No expansion, redirects, pipelines, comments, or multiple commands.
            if not any(c in source for c in '$`\n\r;|<>#'):
                try:
                    lexer = shlex.shlex(source, posix=False, punctuation_chars='&')
                    lexer.whitespace_split = True
                    tokens = list(lexer)
                    words = [shlex.split(w)[0] if w != '&&' else w for w in tokens]
                    if len(words) >= 4 and tokens[0] == 'cd' and tokens[2] == '&&' and tokens.count('&&') == 1:
                        cwd = str((Path(cwd) / words[1]).resolve())
                        words = words[3:]
                    if words and not any('&' in w for w in words) and '=' not in words[0]:
                        argv = words
                except ValueError:
                    pass
        return action_key(dict(argv=argv, cwd=cwd, stdin=action.get('stdin')))

    def begin(self, action):
        try:
            normalized = self.normalize(action)
            # Preserve the executable verbatim. Only attach its actual receipt
            # to an equivalent declared public check.
            probe = deepcopy(normalized)
            if probe.get('subgoal_phase') == 'verify':
                probe['subgoal_phase'] = 'work'
            attempt = super().begin(probe)
            if attempt:
                verification = self.items[attempt['id']]['definition']['verification']
                if self.check_identity(action) == self.check_identity(verification):
                    attempt['phase'] = 'verify'
                elif action.get('subgoal_phase') == 'verify':
                    self.notices = ['This executed command does not match the declared check; it is work evidence, not completion proof.']
                    self.event('verification_not_matched', goal_id=attempt['id'])
            if normalized.get('subgoal_plan'):
                self.rejected_plan = None
                self.plan_error = None
            return attempt
        except ValueError as error:
            if action.get('subgoal_plan'):
                self.rejected_plan = deepcopy(action['subgoal_plan'])
                self.plan_error = str(error)
            raise

    def view(self):
        panel = super().view()
        if self.rejected_plan is not None:
            panel['unregistered_plan'] = deepcopy(self.rejected_plan)
            panel['plan_error'] = self.plan_error
            panel['repair_instruction'] = (
                'This plan has NOT been registered. Correct it on your next ordinary action; '
                'do not keep referring to its unknown IDs. Include substantive verification '
                'and stdout_contains assertions. Do not replace checks with echo/true. '
                'No extra policy or planning tool call is required.')
        return panel


class RepairRunner(RoutedTaskRunner):
    def _panel(self,*args,**kwargs):
        panel=super()._panel(*args,**kwargs)
        panel.pop('checkpoints',None)
        panel['workspace_restore_enabled']=False
        return panel

    def _fatal_provider_error(self, client):
        return getattr(client,'last_failure_detail','')=='provider_quota' or super()._fatal_provider_error(client)

    def _ask(self, role, *args, **kwargs):
        try:
            result=super()._ask(role,*args,**kwargs)
        except ModelCallError:
            if getattr(self.clients[role],'last_failure_detail','')=='provider_quota':
                raise ProviderQuotaUnavailable('Provider quota unavailable') from None
            raise
        if isinstance(result,dict) and result.get('action') in ('restore','checkpoint'):
            raise ValueError('Workspace checkpoint/restore is frozen in this experiment. Continue with commands and public validation.')
        return result

    def _init_subgoals(self):
        self.subgoals = RepairLedger(self.environment.workspace, self._emit) if self.config.subgoals_enabled else None
        self.subgoal_attempt = None

    def _role_system(self, role):
        text = super()._role_system(role)
        if role == 'action':
            text += ('\nA rejected subgoal plan remains in fixed_context.subgoals.unregistered_plan. '
                     'Repair its named schema error while continuing ordinary work; unknown goal IDs are not registered. '
                     'Submission summary prose has no extra character cap beyond the model output allowance. '
                     'Reviewer rejections remain unresolved evidence; a review count never establishes acceptance.')
            text += '\nWorkspace checkpoint and restore actions are disabled. Do not request them.'
        return text
