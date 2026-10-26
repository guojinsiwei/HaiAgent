"""Byte-bounded state serialization, preserving facets and whole evidence records.

This does not infer new facts. The original model output remains in the API audit.
Omitted records are explicitly marked; malformed/truncated states remain errors.
"""
import re
from retrac.engine import STATE_HEADINGS, ProtocolError, validate_state


def bounded_state(text, variant, limit):
    validate_state(text, variant, max(len(text), limit))
    if len(text.encode('utf-8')) <= limit:
        return validate_state(text, variant, limit), {'changed': False}
    headings=STATE_HEADINGS[:5] if variant=='base' else STATE_HEADINGS
    plain=text
    matches=[]
    for i,title in enumerate(headings):
        hits=[line for line in re.finditer(r'(?m)^.*$',plain)
              if re.fullmatch(rf'\s*(?:#+\s*)?{i}\)\s*{re.escape(title)}\s*:?\s*',
                              line.group().replace('**','').replace('__',''),flags=re.IGNORECASE)]
        if len(hits)!=1:raise ProtocolError('Ambiguous duplicate state facet')
        matches.append(hits[0])
    blocks=[]
    for i,match in enumerate(matches):
        body=plain[match.end():matches[i+1].start() if i+1<len(matches) else len(plain)].strip()
        # Keep complete paragraphs/bullets including their continuation lines.
        units=[];current=[];fenced=False
        for line in body.splitlines():
            boundary=not fenced and (not line.strip() or re.match(r'^\s*[-*+]\s+',line))
            if boundary and current:
                units.append('\n'.join(current).strip());current=[]
            if line.strip():current.append(line)
            if line.lstrip().startswith(('```','~~~')):fenced=not fenced
        if current:units.append('\n'.join(current).strip())
        blocks.append(list(dict.fromkeys(u for u in units if u)))
    marker='[Records omitted by size limit; this facet is incomplete. Recheck files/logs before relying on absence.]'
    bodies=[[] for _ in headings]
    def render():
        sections=[]
        for i,title in enumerate(headings):
            content=list(bodies[i])
            if len(content)<len(blocks[i]):content.append(marker)
            sections.append(f'{i}) {title}\n'+'\n'.join(content))
        return '\n'.join(sections)
    if len(render().encode('utf-8'))>limit:raise ProtocolError('State envelope too small for facet omission markers')
    # Round-robin allocates room across all facets, not just the beginning.
    # A record that cannot fit is omitted whole; no clipped paths/code/facts.
    for depth in range(max(map(len,blocks),default=0)):
        for i,units in enumerate(blocks):
            if depth>=len(units):continue
            bodies[i].append(units[depth])
            if len(render().encode('utf-8'))>limit:bodies[i].pop()
    result=render()
    validate_state(result,variant,limit)
    assert len(result.encode('utf-8'))<=limit
    return result, {'changed':True,'original_chars':len(text),'original_bytes':len(text.encode('utf-8')),
                    'retained_bytes':len(result.encode('utf-8')),
                    'retained_records':[len(x) for x in bodies],
                    'omitted_records':[len(a)-len(b) for a,b in zip(blocks,bodies)]}
