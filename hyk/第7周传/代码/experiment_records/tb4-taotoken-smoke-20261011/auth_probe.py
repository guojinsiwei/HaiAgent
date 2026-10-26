"""Two authorized, bounded requests. No retries, redirects, or saved credentials."""
import datetime
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = 'https://api.taotoken.net/token/v1'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def redact(value, key):
    text = str(value).replace(key, '[REDACTED]') if key else str(value)
    text = re.sub(r'(?i)\b(?:sk|tk|api)[-_][a-z0-9_\-]{8,}', '[REDACTED]', text)
    return text[:400]

def make_request(protocol, key):
    body = dict(model='deepseek-flash', max_tokens=64, temperature=0, stream=False,
                thinking={'type': 'disabled'}, messages=[{'role':'user','content':'Reply only OK.'}])
    headers = {'Content-Type':'application/json', 'Accept':'application/json'}
    if protocol == 'openai':
        path = '/chat/completions'
        headers['Authorization'] = 'Bearer ' + key
    else:
        path = '/messages'
        headers.update({'x-api-key':key, 'anthropic-version':'2023-06-01'})
    return urllib.request.Request(ROOT + path, data=json.dumps(body).encode(), headers=headers, method='POST')

def probe(protocol, key, opener):
    req = make_request(protocol, key)
    record = dict(protocol=protocol, endpoint=req.full_url, max_output_tokens=64)
    started = time.monotonic()
    try:
        try:
            response = opener.open(req, timeout=45)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            record['http_status'] = response.code
            raw = response.read(65537)
        if len(raw) > 65536:
            record['error'] = 'Response too large; body omitted'
            return record
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            record['error'] = 'Non-JSON response; body omitted'
            return record
        if not isinstance(data, dict):
            record['error'] = 'Unexpected JSON structure'
            return record
        if response.code == 200:
            if protocol == 'openai':
                choices = data.get('choices') or [{}]
                answer = choices[0].get('message', {}).get('content') or ''
            else:
                answer = ''.join(x.get('text','') for x in data.get('content',[]) if x.get('type') == 'text')
            record['reply'] = redact(answer, key)
            record['model_returned'] = redact(data.get('model',''), key)
            record['success'] = bool(answer.strip())
            usage = data.get('usage')
            if isinstance(usage, dict):
                record['usage'] = {k:v for k,v in usage.items() if isinstance(v,(int,float)) and not isinstance(v,bool)}
        else:
            error = data.get('error', data)
            if isinstance(error, dict):
                record['error_type'] = redact(error.get('type',error.get('code','')), key)
                record['error'] = redact(error.get('message','Unspecified API error'), key)
            else:
                record['error'] = redact(error, key)
    except Exception as error:
        record['error'] = 'Transport/response failure: ' + type(error).__name__
    finally:
        record['elapsed_seconds'] = round(time.monotonic()-started, 2)
    return record

def main():
    key = sys.stdin.readline(8192).strip()
    if not key or len(key)>8000 or not key.isascii() or any(c.isspace() for c in key):
        raise SystemExit('Invalid input format; no requests sent. Paste only the API key.')
    opener = urllib.request.build_opener(NoRedirect())
    results = [probe(protocol, key, opener) for protocol in ('openai','anthropic')]
    key = ''
    now = datetime.datetime.now(datetime.timezone.utc)
    report = dict(timestamp=now.isoformat(), requests_attempted=2, retries=0, benchmark_started=False, results=results)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    folder = Path(__file__).resolve().parent
    (folder / ('auth-probe-' + now.strftime('%Y%m%dT%H%M%S%fZ') + '.json')).write_text(text, encoding='utf-8')
    (folder / 'auth-probe-latest.json').write_text(text, encoding='utf-8')
    print(text)

if __name__ == '__main__':
    main()
