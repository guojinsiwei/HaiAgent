"""Evidence-backed cross-action trigger; never an action-equivalence proof."""
import json
import posixpath
import re


def check_identity(command, cwd='.'):
    text = str(command)
    directory = cwd
    cd = re.match(r'''^\s*cd\s+(['"]?)([^\s;'"&|]+)\1\s*&&\s*''', text)
    if cd:
        directory = posixpath.normpath(posixpath.join(cwd, cd[2]))
        text = text[cd.end():]
    if '<<' not in text:
        build = re.search(r'(?:^|[;&|]\s*)(gcc|g\+\+|cc|c\+\+)\s+([^;\n|&]+)', text)
        if build and not re.search(r'[$`\\]', build[2]):
            sources = sorted(re.findall(r'''(?:^|\s)([^\s'"<>]+\.(?:c|cc|cpp|cxx))(?=\s|$)''', build[2]))
            if sources:
                return json.dumps(['build', directory, sources], separators=(',', ':'))
        telnet = re.search(r'(?:^|[;|&]\s*|\btimeout\s+\d+\s+)telnet\s+([\w.-]+)\s+(\d+)\b', text)
        if telnet:
            return json.dumps(['telnet', directory, telnet[1], telnet[2]], separators=(',', ':'))
    if not re.search(r'[\n\r$`<>]', text):
        test = re.search(r'(?:^|[;&|]\s*)(python(?:3)?\s+-m\s+pytest|pytest)\s+([^;&|]*)', text)
        if test:
            args = [x for x in test[2].strip().split() if not re.fullmatch(r'-q+|-v+|--tb=(?:short|long|no)|--disable-warnings|--no-header|--no-summary', x)]
            if args:
                return json.dumps(['pytest', directory, args], separators=(',', ':'))
    return json.dumps(['exact', directory, text.strip()], separators=(',', ':'))


def issue_identity(focus, observation, cwd='.'):
    targets=sorted(set(focus.get('targets', [])))
    if not focus.get('goal') or not targets:return None
    families=sorted(set(re.findall(r'\b(?:[A-Z][A-Za-z]*(?:Error|Exception)|undefined reference|segmentation fault|connection refused|address already in use)\b',
        observation.get('stderr','')+'\n'+observation.get('stdout',''))))
    return json.dumps(['issue',cwd,focus['goal'],targets,families],separators=(',',':')) if families else None


class ExplorationTrigger:
    def __init__(self, state=None, capacity=24):
        self.state = state if state is not None else {}
        self.capacity = capacity
        for key in ('checks', 'seen', 'blockedEvidence'):
            self.state.setdefault(key, [])
        self.state.setdefault('lastDecision', None)

    def observe(self, key, evidence, status):
        if status not in ('failed', 'passed') or (evidence in self.state['seen'] or [key,evidence] in self.state['seen']):
            return
        self.state['seen'] = (self.state['seen'] + [[key,evidence]])[-1024:]
        row = next((x for x in self.state['checks'] if x['key'] == key), None)
        if status == 'passed':
            self.state['checks'] = [x for x in self.state['checks'] if x['key'] != key]
            return
        if row is None:
            row = dict(key=key, failures=0, evidence=[], blocked=False)
        row['failures'] += 1
        row['evidence'] = (row['evidence'] + [evidence])[-4:]
        self.state['checks'] = ([x for x in self.state['checks'] if x is not row] + [row])[-self.capacity:]

    def blocked(self, key, evidence):
        row = next((x for x in self.state['checks'] if x['key'] == key), None)
        if row is None or evidence in self.state['blockedEvidence']:
            return
        self.state['blockedEvidence'] = (self.state['blockedEvidence'] + [evidence])[-1024:]
        row['blocked'] = True

    def pending(self, threshold, key=None):
        return next((x for x in self.state['checks'] if (key is None or x['key'] == key)
                     and (x['failures'] >= threshold or x['blocked'] or x.get('requested'))), None)

    def consume(self, row):
        decision = dict(key=row['key'], failures=row['failures'], evidence=list(row['evidence']),
                        reason=row['reason'] if row.get('requested') else 'repeated_failure_request' if row['blocked'] else 'same_check_failed_again')
        row['failures'] = 0
        row['blocked'] = False
        row['requested'] = False
        self.state['lastDecision'] = decision
        return decision

    def retire_pending(self):
        for row in self.state['checks']:
            row['failures'] = 0
            row['blocked'] = False
            row['requested'] = False

    def request(self,key,evidence,reason):
        ids=list(dict.fromkeys(evidence))
        if len(ids)<2:return
        row=dict(key=key,failures=0,evidence=ids[-4:],blocked=False,requested=True,reason=reason)
        self.state['checks']=([x for x in self.state['checks'] if x['key']!=key]+[row])[-self.capacity:]
