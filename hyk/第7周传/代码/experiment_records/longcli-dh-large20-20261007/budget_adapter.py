"""Capacity adapter only: DSH text-token estimate and task-global wire ceiling."""
import json
from math import ceil
from common import ROOT,save

def estimated_tokens(messages):
    return sum(ceil(len(m['content'].encode('utf-16-le'))/8)+(4 if m['role']=='system' else 8)
               for m in messages)

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
        estimate=estimated_tokens(payload['messages'])
        assert estimate+payload['max_tokens']<=1000000,'Context allowance exceeded before provider call'
        self.audit.emit('context_measurement',estimated_input_tokens=estimate,
            output_token_allowance=payload['max_tokens'],context_tokens=1000000,exact_tokenizer=False)
        return self.transport(endpoint,payload,key,seconds,recorder=recorder)
