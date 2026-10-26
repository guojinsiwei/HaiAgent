"""Capacity adapter only: DSH text-token estimate and task-global wire ceiling."""
import json
from math import ceil
from common import ROOT,save

def estimated_tokens(messages):
    # Character-equivalent units represent serialized UTF-8 bytes for this small arm.
    return ceil(len(json.dumps({'messages':messages},ensure_ascii=False).encode('utf-8'))/4)

def install_context_meter():
    import bestfgs.lean_conversation as conversation
    # Native history selection is unchanged; its arithmetic now uses token-priced
    # character-equivalent units, consistently with the configured budget * 4.
    conversation.message_chars=lambda messages:estimated_tokens(messages)*4
    if not getattr(conversation.Conversation,'_dsh_budget_meter',False):
        original=conversation.Conversation.build
        def build(self,system,payload,budget):
            history,view=original(self,system,payload,budget)
            messages=[{'role':'system','content':system},*history,
                      {'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
            view['budget_character_equivalents']=view['message_chars']
            view['message_chars']=len(json.dumps(messages,ensure_ascii=False))
            view['estimated_input_tokens']=estimated_tokens(messages)
            view['meter']='DSH fixed density heuristic, not exact tokenizer'
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
    def __call__(self,endpoint,payload,key,seconds,recorder=None):
        from bestfgs.models import ModelCallError
        messages=payload['messages'];removed=0
        size=lambda:len(json.dumps({'messages':messages},ensure_ascii=False).encode('utf-8'))
        while size()>48000 and len(messages)>2:
            del messages[1:min(3,len(messages)-1)];removed+=1
        if size()>48000:
            raise ModelCallError('protected input exceeds 48000-byte small budget')
        if removed:self.audit.emit('transport_history_projection',removed_old_pairs=removed,
            reason='48000_utf8_bytes',full_history_retained_in_audit=True)
        assert payload['max_tokens']==4096,'Wrong output budget'
        self.audit.emit('context_measurement',input_utf8_bytes=size(),max_input_bytes=48000,
            output_token_allowance=4096,exact_tokenizer=False)
        return self.transport(endpoint,payload,key,seconds,recorder=recorder)
