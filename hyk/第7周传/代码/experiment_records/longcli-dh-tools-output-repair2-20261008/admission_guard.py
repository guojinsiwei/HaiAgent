"""A failed engineering pilot cannot authorize a paid batch expansion."""
class AdmissionGuard:
    def __init__(self):self.streaks={}
    def observe(self,method,summary,*,pilot=False):
        if pilot and summary.get('stop_reason')=='model_or_protocol_error_limit':
            return 'pilot_protocol_failure:'+method
        shared=summary.get('engineering_fault') or summary.get('cleanup_error')
        if shared:return 'shared_'+str(shared)
        reason=summary.get('task_local_error') or summary.get('artifact_error')
        if not reason and summary.get('state') not in ('awaiting_grade','keyless_pass'):
            reason=summary.get('error_type') or 'missing_delivery'
        if not reason:
            self.streaks[method]=(None,0);return None
        previous,count=self.streaks.get(method,(None,0))
        count=count+1 if previous==reason else 1
        self.streaks[method]=(reason,count)
        if pilot:return 'engineering_pilot_failed:'+method+':'+reason
        if count>=2:return 'repeated_engineering_failure:'+method+':'+reason
        return None
