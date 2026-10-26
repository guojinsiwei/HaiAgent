"""Strict single-choice SSE assembly; reasoning is never executable content."""
import json
import time


def read_completion(response, deadline):
    content=[]; reasoning=[]; finish=None; usage=None; size=0; done=False
    data=[]
    for raw in response:
        size+=len(raw)
        if size>16_000_000 or time.monotonic()>deadline:
            raise ValueError('stream resource limit reached')
        line=raw.decode('utf-8').rstrip('\r\n')
        if line.startswith('data:'):
            data.append(line[5:].lstrip());continue
        if line or not data:continue
        value='\n'.join(data);data=[]
        if value=='[DONE]':done=True;break
        chunk=json.loads(value)
        if chunk.get('error'):raise ValueError('stream provider error')
        if chunk.get('usage') is not None:usage=chunk['usage']
        for choice in chunk.get('choices',[]):
            if choice.get('index',0)!=0:raise ValueError('multiple choices unsupported')
            delta=choice.get('delta',{})
            if delta.get('tool_calls'):raise ValueError('unexpected native tool calls')
            for key,target in [('content',content),('reasoning_content',reasoning)]:
                if delta.get(key) is not None:
                    if not isinstance(delta[key],str):raise ValueError('invalid text delta')
                    target.append(delta[key])
            if choice.get('finish_reason') is not None:finish=choice['finish_reason']
    if not done or finish is None or usage is None:
        raise ValueError('incomplete stream; reservation retained')
    return {'choices':[{'finish_reason':finish,'message':{'content':''.join(content),
             'reasoning_content':''.join(reasoning)}}],'usage':usage}
