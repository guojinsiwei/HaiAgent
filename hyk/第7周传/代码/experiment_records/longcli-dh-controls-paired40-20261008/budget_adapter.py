"""Exact UTF8 message-byte admission and task-global wire ceiling."""
import json
from math import ceil
from common import ROOT,save

def estimated_tokens(messages):
    # Character-equivalent units represent serialized UTF-8 bytes for this small arm.
    return ceil(len(json.dumps({'messages':messages},ensure_ascii=False).encode('utf-8'))/4)

def install_context_meter():
    import bestfgs.lean_conversation as conversation
    # Install byte accounting on each campaign conversation, not unrelated profiles.
    if not getattr(conversation.Conversation,'_dsh_budget_meter',False):
        original=conversation.Conversation.build
        def build(self,system,payload,budget):
            self.byte_budget=True
            history,view=original(self,system,payload,budget)
            messages=[{'role':'system','content':system},*history,
                      {'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
            view['input_utf8_bytes']=len(json.dumps({'messages':messages},ensure_ascii=False).encode('utf-8'))
            view['estimated_input_tokens']=estimated_tokens(messages)
            view['meter']='exact serialized UTF8 message bytes; token estimate is informational only'
            return history,view
        conversation.Conversation.build=build
        conversation.Conversation._dsh_budget_meter=True

class WireBudget:
    def __init__(self,limit=800):self.limit=limit;self.used=0
    def claim(self):
        if self.used>=self.limit:raise TimeoutError('actual API request budget exhausted')
        self.used+=1

class CheckedTransport:
    def __init__(self,audit,transport=None):
        from net_transport import request
        self.audit=audit;self.transport=transport or request
    def prepare(self,payload):
        from bestfgs.context_budget import ContextBudgetError
        messages=payload['messages'];removed=0
        size=lambda:len(json.dumps({'messages':messages},ensure_ascii=False).encode('utf-8'))
        while size()>48000 and len(messages)>2:
            del messages[1:min(3,len(messages)-1)];removed+=1
        if size()>48000:
            raise ContextBudgetError('protected input exceeds 48000-byte small budget')
        if removed:self.audit.emit('transport_history_projection',removed_old_pairs=removed,
            reason='48000_utf8_bytes',full_history_retained_in_audit=True)
        assert payload['max_tokens']==4096,'Wrong output budget'
        return payload
    def __call__(self,endpoint,payload,key,seconds,recorder=None):
        self.prepare(payload)
        messages=payload['messages']
        size=lambda:len(json.dumps({'messages':messages},ensure_ascii=False).encode('utf-8'))
        self.audit.emit('context_measurement',input_utf8_bytes=size(),max_input_bytes=48000,
            output_token_allowance=4096,exact_tokenizer=False)
        return self.transport(endpoint,payload,key,seconds,recorder=recorder)
