"""Bound rejected-delivery loops using observed files and fresh tool evidence.

No similarity claim or hidden-grader inference: a changed file is not a changed
algorithm, and a clean command is not proof of correctness. A fixed rejection
cap bounds cosmetic/same-direction changes that file hashes cannot diagnose.
"""
from .lean_audit import digest
from .lean_progress import normalize_workspace_path
from .lean_protocol import text
from .prompt_views import diagnostic_category


class SubmissionGuard:
    def __init__(self, environment, config):
        self.environment, self.config = environment, config
        self.rejected_scopes = set()
        self.rejected_artifacts = set()
        self.last = None
        self.blocked = 0
        self.rejections = 0

    def state(self):
        scope = self.environment.scope()
        paths = self.config.submission_artifact_paths
        states = self.environment.dependency_state(paths) if paths else {}
        complete = bool(paths) and all(states.get(p, 'unknown') != 'unknown' for p in paths)
        return dict(scope=scope, artifact_states=states,
                    artifact_key=digest(states) if complete else None,
                    coverage='explicit_public_contract' if paths else 'workspace_only')

    def view(self):
        return dict(enabled=True, last_rejection=self.last,
            rejected_submissions=self.rejections, blocked_proposals=self.blocked,
            max_rejected_submissions=self.config.max_rejected_submissions,
            rule=('After rejection, change the delivered files and run a fresh, complete '
                  'non-listing check against the current state. Supply submission_revision '
                  'with rejection_id, hypothesis, change and validation_evidence_ids. '
                  'Neither a new summary nor repeated checks unlock an unchanged artifact. '
                  'Clean execution is evidence only, not proof of task success.'))

    def validate(self, action, evidence):
        current = self.state()
        if not self.last:
            return current, None
        if current['scope'] in self.rejected_scopes:
            return current, 'unchanged_or_previously_rejected_workspace'
        if self.config.submission_artifact_paths:
            if current['artifact_key'] is None:
                return current, 'artifact_state_unknown'
            if current['artifact_key'] in self.rejected_artifacts:
                return current, 'unchanged_or_previously_rejected_public_artifacts'
        revision = action.get('submission_revision')
        if not isinstance(revision, dict):
            return current, 'missing_submission_revision'
        if revision.get('rejection_id') != self.last['id']:
            return current, 'revision_must_address_latest_rejection'
        try:
            text(revision.get('hypothesis'), 'submission_revision.hypothesis', 400)
            text(revision.get('change'), 'submission_revision.change', 400)
        except ValueError as error:
            return current, str(error)
        ids = revision.get('validation_evidence_ids')
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 3 or
                any(not isinstance(i, str) or i not in evidence for i in ids)):
            return current, 'validation_evidence_ids_require_1_to_3_available_tool_records'
        for key in ids:
            row = evidence[key]
            if (row.get('tool_index', 0) <= self.last['tool_index'] or
                    row.get('before') != current['scope'] or row.get('after') != current['scope']):
                return current, 'validation_is_stale_or_changed_files_while_checking'
            if (not row.get('execution_assessment', {}).get('execution_clean') or
                    row.get('capture_incomplete') or row.get('terminal_projection_incomplete')):
                return current, 'validation_failed_or_incomplete'
            # Listings, grep/cat, echo and no-output true do not verify a repair.
            argv = row.get('validation_argv', [])
            if (diagnostic_category(argv) in {'read', 'listing', 'search', 'diff'} or
                    not argv or argv[0].rsplit('/', 1)[-1] in {'echo', 'printf', 'true', 'pwd'} or
                    not (row.get('stdout', '').strip() or row.get('stderr', '').strip())):
                return current, 'validation_requires_observed_non_listing_check'
        return current, None

    def reject(self, state, feedback, tool_index):
        self.rejections += 1
        self.blocked = 0
        self.rejected_scopes.add(state['scope'])
        if state['artifact_key'] is not None:
            self.rejected_artifacts.add(state['artifact_key'])
        self.last = dict(id='S'+str(self.rejections), tool_index=tool_index,
            workspace=state['scope'], artifact_key=state['artifact_key'],
            coverage=state['coverage'], feedback=feedback,
            status='evaluator_rejection_not_causal_exclusion')

    def refuse(self, reason):
        self.blocked += 1
        return dict(submission_blocked=True, error_code=reason,
            rejection_id=self.last['id'] if self.last else None,
            instruction=self.view()['rule'],
            remaining_blocked_proposals=max(0, self.config.max_submission_blocks-self.blocked),
            environment_submission_executed=False, task_success=None)

    def exhausted(self):
        return (self.rejections >= self.config.max_rejected_submissions or
                self.blocked >= self.config.max_submission_blocks)


def validate_artifact_paths(paths):
    if not isinstance(paths, tuple) or len(paths) > 64 or len(set(paths)) != len(paths):
        raise ValueError('submission_artifact_paths must be a unique tuple of public contract paths')
    for path in paths:
        if normalize_workspace_path(path) != path:
            raise ValueError('submission_artifact_paths must be normalized workspace paths')
