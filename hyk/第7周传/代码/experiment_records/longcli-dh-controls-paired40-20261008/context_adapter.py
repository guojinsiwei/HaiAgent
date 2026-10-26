"""Common final-prompt projection for both sides of the tool ablation."""
from bestfgs.context_budget import fit_payload

class SharedContextProjection:
    def _prepare_context(self,role,system,payload):
        self.conversation.byte_budget=True
        self._emit('context_source',role=role,payload=payload)
        projected,view=fit_payload(system,payload,self.config.context_chars-1024)
        fixed=projected.get('fixed_context',{})
        if 'evidence' in fixed:self.visible_evidence={e['id'] for e in fixed['evidence']}
        self.visible_evidence.update(projected.get('handover_report',{}).get('advertised_evidence_ids',[]))
        if 'memories' in fixed:
            self.visible_memories={m['id'] for m in fixed['memories']}
            self.visible_memory_records={m['id']:m for m in fixed['memories']}
        self._emit('context_projection',role=role,**view)
        return projected
