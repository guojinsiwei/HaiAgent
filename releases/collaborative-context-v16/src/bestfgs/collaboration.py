"""Role-separated model policy; graph scheduling and tool execution stay deterministic."""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

from .retrac_adapter import (
    RetracPolicyAdapter, OpenAICompatibleJSONClient, PROVIDER_DEFAULTS,
    _system_prompt_for_mode,
)

ROLES = ('action', 'assessment', 'memory')
RESPONSIBILITIES = {
    'action': 'You only propose the initial semantic map and executable candidate actions. Do not assess results that have not happened or generate next_context. The deterministic graph scheduler, not you, chooses the next frontier entry. Existing explicit submission rules remain in force.',
    'assessment': 'You only assess an already executed CLI transition against real evidence. Never generate commands, memory, or next_context. You cannot execute, submit, or declare official success.',
    'memory': 'You only maintain task-local structured context and optional evidence-linked experience. You cannot execute, submit, generate an assessment, or change the search policy. Claims are not facts without actual evidence.',
}

def role_system(role, mode):
    original = _system_prompt_for_mode(mode)
    return '\n'.join(RESPONSIBILITIES[role] + ' Never pretend that you executed a command.'
                     if line.startswith('Your responsibilities are ') else line
                     for line in original.splitlines())

class CollaborativePolicyAdapter(RetracPolicyAdapter):
    """Action -> real environment -> assessment + memory -> original graph.

    Calls are deliberately serial. No simultaneous workspace writers, unbounded
    debate, extra CLI tools, extra judge, or change to the memory admission rules.
    A role failure is propagated; there is no fallback to a silently different model.
    """
    def __init__(self, config, *, role_configs=None, clients=None, experience_mode='conditioned', diagnostics_dir=None,
                 terminal_views=True):
        configs = dict(role_configs or {})
        supplied = dict(clients or {})
        if set(configs) - set(ROLES) or set(supplied) - set(ROLES):
            raise ValueError('Unknown collaboration role')
        self.role_configs = {role: configs.get(role, config) for role in ROLES}
        self.role_clients = {}
        for role in ROLES:
            path = Path(diagnostics_dir) / f'model-failures-{role}.jsonl' if diagnostics_dir else None
            self.role_clients[role] = supplied.get(role) or OpenAICompatibleJSONClient(
                self.role_configs[role], diagnostics_path=path)
        if len({id(c) for c in self.role_clients.values()}) != len(ROLES):
            raise ValueError('Roles require distinct client instances for independent accounting')
        super().__init__(self.role_configs['action'], client=self.role_clients['action'],
                         experience_mode=experience_mode,
                         system_prompt_override=role_system('action', experience_mode), terminal_views=terminal_views)
        self.incremental_context = True
        if terminal_views and self.config.max_context_chars < 4000:
            raise ValueError('Terminal memory panel requires max_context_chars >= 4000')
        self.role_policies = {role: RetracPolicyAdapter(self.role_configs[role],
            client=self.role_clients[role], experience_mode=experience_mode,
            system_prompt_override=role_system(role, experience_mode))
            for role in ('assessment', 'memory')}
        self._last_role = 'action'

    def _ask_and_parse(self, *args, **kwargs):
        self._last_role = 'action'
        return super()._ask_and_parse(*args, **kwargs)

    def _ask_transition(self, prompt, parser, *, assessment_prompt, memory_prompt):
        def parse_assessment(payload):
            if set(payload) != {'assessment'} or not isinstance(payload['assessment'], dict):
                raise ValueError('Assessment role must return assessment only')
            allowed = {'direction_status', 'task_success', 'satisfied_success_criteria', 'feedback'}
            if set(payload['assessment']) - allowed:
                raise ValueError('Assessment role exceeded its field ownership')
            # Validate with original eligibility/criteria gates before asking memory.
            parser({'assessment': payload['assessment'], 'next_context': {}})
            return dict(payload['assessment'])

        self._last_role = 'assessment'
        assessment = self.role_policies['assessment']._ask_and_parse(
            assessment_prompt, parse_assessment, stage='Assess observed evidence only',
            prompt_cache_key='bestfgs-v15-assessment')

        def parse_memory(payload):
            allowed = {'next_context', 'micro_experiences'} if self.experience_mode == 'conditioned' else {'next_context'}
            allowed.add('context_changes')
            if set(payload) - allowed or not isinstance(payload.get('next_context'), dict):
                raise ValueError('Memory role must return next_context and optional task-local experience only')
            combined = dict(assessment)
            if self.experience_mode == 'conditioned':
                combined['micro_experiences'] = payload.get('micro_experiences', [])
            return parser({'assessment': combined, 'next_context': payload['next_context'],
                           'context_changes': payload.get('context_changes', [])})

        # A memory parse retry repeats only memory, not the already-valid assessor.
        self._last_role = 'memory'
        return self.role_policies['memory']._ask_and_parse(
            memory_prompt, parse_memory, stage='Maintain context and task-local experience only',
            prompt_cache_key='bestfgs-v15-memory')

    def model_usage_summary(self):
        roles = {}
        for role, client in self.role_clients.items():
            fn = getattr(client, 'usage_summary', None)
            roles[role] = dict(fn() if callable(fn) else {})
            roles[role].update(provider=self.role_configs[role].provider,
                               configured_model=self.role_configs[role].model_name)
        counters = ('model_calls', 'api_requests', 'api_responses', 'prompt_tokens',
            'cached_prompt_tokens', 'cache_miss_prompt_tokens', 'cache_write_prompt_tokens',
            'completion_tokens', 'usage_missing_responses', 'usage_unreported_requests')
        totals = {key: sum(row.get(key, 0) for row in roles.values()) for key in counters}
        denominator = totals['cached_prompt_tokens'] + totals['cache_miss_prompt_tokens']
        totals['cache_hit_rate'] = round(totals['cached_prompt_tokens'] / denominator, 6) if denominator else 0.0
        for key in ('response_models', 'system_fingerprints'):
            totals[key] = sorted({v for row in roles.values() for v in row.get(key, [])})
        failures = {}
        for row in roles.values():
            for name, count in row.get('failure_counts', {}).items():
                failures[name] = failures.get(name, 0) + count
        last = roles[self._last_role]
        totals.update(failure_counts=failures, roles=roles, policy='collaborative-context-v16',
                      prompt_view_policy='terminal-views-v2' if self.terminal_views else 'v15-original',
                      context_update_policy='explicit-retirement-v1',
                      prompt_views={'built_count': self.prompt_view_count,
                                    'retained_last': list(self.prompt_view_audit)},
                      last_role=self._last_role, last_failure_kind=last.get('last_failure_kind'),
                      last_failure_detail=last.get('last_failure_detail'))
        return totals

def role_config_from_environment(base, role):
    """Overrides change model routing only, not the existing limits or budgets.

    Cross-provider/endpoint routing requires an explicit key environment variable
    so a base credential can never be silently forwarded to another service.
    """
    prefix = 'BESTFGS_' + role.upper() + '_'
    model = os.getenv(prefix + 'MODEL', base.model_name)
    provider = os.getenv(prefix + 'PROVIDER', base.provider)
    url = os.getenv(prefix + 'BASE_URL', base.base_url)
    key_env = os.getenv(prefix + 'API_KEY_ENV')
    if provider not in PROVIDER_DEFAULTS:
        raise ValueError(f'Unsupported provider for {role}')
    if (provider != base.provider or url.rstrip('/') != base.base_url.rstrip('/')) and not key_env:
        raise ValueError(f'{prefix}API_KEY_ENV is required when changing provider or endpoint')
    if provider != base.provider and (not os.getenv(prefix + 'BASE_URL') or not os.getenv(prefix + 'MODEL')):
        raise ValueError(f'Explicit {prefix}BASE_URL and MODEL required for a different provider')
    key = os.getenv(key_env, '') if key_env else base.api_key
    if not key.strip():
        raise ValueError(f'Missing credential for role {role}')
    return replace(base, model_name=model, provider=provider, base_url=url, api_key=key)

def build_collaborative_policy(config, *, experience_mode, diagnostics_dir):
    enabled = os.getenv('BESTFGS_TERMINAL_VIEWS', 'on')
    if enabled not in ('on', 'off'):
        raise ValueError('BESTFGS_TERMINAL_VIEWS must be on or off')
    return CollaborativePolicyAdapter(config,
        role_configs={r: role_config_from_environment(config, r) for r in ROLES},
        experience_mode=experience_mode, diagnostics_dir=diagnostics_dir, terminal_views=enabled == 'on')
