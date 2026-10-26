"""HAI-inspired execution-time provenance and observed lessons, without LLM claims."""
from collections import OrderedDict
import json
from pathlib import PurePosixPath
import shlex
import re

from .lean_audit import digest
from .lean_memory import action_key
from .lean_progress import normalize_workspace_path
from .command_paths import command_dependency_paths


def dependency_paths(action, known=(), limit=16):
    return command_dependency_paths(action, known, limit)


class MemoryEvents:
    def _init_memory_events(self):
        self.memory_pending = OrderedDict()
        self.memory_seen = OrderedDict()
        self.memory_notices = []

    def _memory_query(self, question, recent):
        pieces=[self.task.goal[:500],question]
        for row in recent[-3:]:
            pieces.extend([row['argv'],row['purpose'],row['stderr'][:600],row['stdout'][:300]])
        if self.monitor_review:
            pieces.extend([self.monitor_review['reason'],self.monitor_review['next_check']])
        return ' '.join(pieces)[:4000]

    def _memory_audit_admission(self, item, added, origin):
        self.counts['memories_admitted'] += int(added)
        self._emit('memory_admitted', memory=item, new=added, origin=origin,
                   retained=item['id'] in self.memory.items)
        if item.get('repairs'):
            notice=dict(memory_id=item['id'], repairs=item['repairs'])
            self.memory_notices=(self.memory_notices+[notice])[-3:]
            self._emit('memory_field_repaired', **notice)
        for eviction in self.memory.evicted:
            self._emit('memory_evicted', **eviction)
        self.memory.evicted.clear()

    def _observe_memory_event(self, action, row):
        if not (self.config.memory_reliability and self.config.auto_memory):
            return
        failed = row['return_code'] != 0 or row['timed_out'] or row['blocked']
        assessment=row.get('execution_assessment',{})
        if assessment.get('suspected_failure') and not failed:
            self.monitor_event='suspected_execution_failure'
            self._emit('suspected_failure_observed',evidence_id=row['id'],signals=assessment['signals'])
            # A suspicious zero exit is not a verified success or a causal blocker.
            return
        # rg/grep exit 1 without diagnostics is a no-match observation, not a failure lesson.
        no_match=row['category']=='search' and row['return_code']==1 and not row['stderr'] and not row['timed_out'] and not row['blocked']
        checked = row['category']=='test' and not failed
        if self.config.outcome_reliability:
            checked=assessment.get('check_status')=='public_check_passed'
        if no_match or not (failed or checked) or row['capture_incomplete'] or row.get('terminal_projection_incomplete'):
            return
        self.memory_pending[row['id']]=dict(row)
        while len(self.memory_pending)>32:
            lost,_=self.memory_pending.popitem(last=False)
            self._emit('memory_candidate_expired', evidence_id=lost, reason='bounded_event_queue')
        self._emit('memory_event_candidate', evidence_id=row['id'], kind='failure' if failed else 'public_check')
        key=digest([row['command_key'],row['outcome_key'],row['after']])
        previous=self.memory_seen.get(key)
        self.memory_seen[key]=dict(row)
        self.memory_seen.move_to_end(key)
        while len(self.memory_seen)>64: self.memory_seen.popitem(last=False)
        if failed and previous is None:
            return
        evidence={row['id']:row}
        if failed: evidence[previous['id']]=previous
        ids=list(evidence)[-3:]
        quote=(row['stderr'] or row['stdout'])[:240]
        value=dict(kind='blocker' if failed else 'finding',
            conclusion=(('This exact command produced the same captured failure twice; cause remains unknown.'
                if failed else 'This public test command exited zero; test completeness and task success remain unverified.')
                +' Captured outcome: '+row['outcome_key'][:16]),
            condition='For this command and observed dependencies; external state must be rechecked. '+row['argv'][:180],
            targets=list(row.get('stable_dependencies',{}))[:4],operation='',
            next_step='Check changed inputs or a specific retry reason before repeating.' if failed else 'Re-run relevant checks after related changes.',
            evidence_ids=ids)
        item,added=self.memory.admit(value,evidence,set(evidence),self.environment.dependency_state,
                                     current_scope=row['after'])
        item.update(origin='execution_observer',status='observed_tool_outcome_not_causal_rule',
                    command_key=row['command_key'],outcome_key=row['outcome_key'],observation_excerpt=quote)
        self.counts['observed_memories_admitted']+=int(added)
        self._memory_audit_admission(item,added,'execution_observer')
