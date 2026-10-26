import getpass
from pathlib import Path
import subprocess
from auth_probe import redact

print('TaoToken Token Plan AUTH TEST ONLY - no benchmark will start.')
print('Two requests: OpenAI + Anthropic; reply OK; max 64 output tokens each; no retries.')
print('Use your TaoToken API key, not a DeepSeek website key. Paste the key only.')
key = getpass.getpass('TaoToken API key (hidden, never saved): ').strip()
if not key:
    raise SystemExit('Empty input: no requests sent.')
try:
    result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',
        '-i','C:/Users/54177/.ssh/cubestudio_notebook','lizh639@172.16.108.236',
        '/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python',
        '/var/tmp/lizh639-tb4-taotoken-smoke-20261011/auth_probe.py'],
        input=(key+'\n').encode(), capture_output=True, timeout=130)
    output = result.stdout.decode(errors='replace')
    error = redact(result.stderr.decode(errors='replace'), key)
    # Preserve full sanitized JSON, not the bounded error-text helper.
    output = output.replace(key, '[REDACTED]')
    print(output)
    if error:
        print(error)
    Path(__file__).with_name('auth-probe-receipt.txt').write_text(output+'\n'+error,encoding='utf-8')
except subprocess.TimeoutExpired:
    print('Timed out waiting for the remote probe. Do not retry automatically; check remote result first.')
finally:
    key = ''
input('Press Enter to close...')
