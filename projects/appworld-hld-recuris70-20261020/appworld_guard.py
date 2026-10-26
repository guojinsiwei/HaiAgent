"""Agent-side safeguards using public API contracts only; no grader access."""
import re


def answer_contract(instruction):
    text = instruction.strip().lower()
    asks = re.search(r'\b(how many|how much|what is|what are|which |tell me|report |return |answer |give me|let me know)\b', text)
    if asks or re.match(r'^(count|calculate|list|find out|identify|show me)\b', text):
        return 'answer'
    if re.match(r'^(send|add|import|delete|remove|create|make|update|change|move|save|export|cancel|mark|set|i made)\b', text):
        return 'state_only'
    return 'unspecified'


class AppWorldGuard:
    def __init__(self, instruction, docs):
        self.contract = answer_contract(instruction)
        self.docs = docs
        self.read_only = False
        self.submitted = False
        self.revision = 0
        self.events = []
        self.submission_response = None

    def invoke(self, original, app, api, **kwargs):
        doc = self.docs.get(app, {}).get(api, {})
        method = doc.get('method', '').upper()
        auth = api == 'login' and method == 'POST'
        # Some public GET exports persist files/attachments. HTTP method alone
        # cannot establish absence of application side effects.
        readonly = (method == 'GET' and not api.startswith(('export', 'download'))) or auth
        submission = app == 'supervisor' and api == 'complete_task'
        if (self.read_only or self.submitted) and not readonly:
            # A public submission is the agent's commit point. Repeated submits
            # are idempotent; extra probes cannot mutate an already submitted world.
            if submission and self.submitted:
                return self.submission_response
            self.events.append({'kind': 'write_blocked', 'api': app+'.'+api})
            raise RuntimeError('APPWORLD_READ_ONLY: verification/submitted tasks permit reads and login only. Do not send probes, top up, export, or delete records as verification.')
        if submission and self.contract == 'state_only' and kwargs.get('answer') is not None:
            kwargs['answer'] = None
            self.events.append({'kind': 'state_only_answer_normalized', 'basis': 'public instruction asks for an operation without a returned answer'})
        parameters = {p.get('name') for p in doc.get('parameters', [])}
        if 'page_index' in parameters and 'page_index' not in kwargs:
            self.events.append({'kind': 'partial_page_warning', 'api': app+'.'+api,
                                'instruction': 'Default page is a sample. For ALL records, use collect_pages or explicitly paginate to an empty page before selecting/mutating.'})
        response = original(_app_name=app, _api_name=api, **kwargs)
        success = getattr(response, 'status_code', 500) < 300
        if success and not readonly:
            self.revision += 1
            self.events.append({'kind': 'mutation', 'api': app+'.'+api})
        if success and submission:
            self.submitted = True
            self.submission_response = response
        return response

    def status(self):
        return {'revision': self.revision, 'submitted': self.submitted,
                'read_only': self.read_only or self.submitted, 'answer_contract': self.contract}


def collect_pages(api, *, page_limit=5, max_pages=200, **kwargs):
    """Explicit helper. Preserves each API row and refuses incomplete scans."""
    if 'page_index' in kwargs:
        raise ValueError('collect_pages starts at page zero; omit page_index')
    rows = []
    seen = set()
    for index in range(max_pages):
        page = api(page_index=index, page_limit=page_limit, **kwargs)
        if not isinstance(page, list):
            raise TypeError('This API does not return a list; inspect its public pagination contract')
        if not page:
            return rows
        signature = repr(page)
        if signature in seen:
            raise RuntimeError('Pagination repeated a page; completeness is unverified')
        seen.add(signature)
        rows.extend(page)
    raise RuntimeError('Pagination limit reached; completeness is unverified')
