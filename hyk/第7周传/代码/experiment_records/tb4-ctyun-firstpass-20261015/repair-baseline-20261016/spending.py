"""Persistent shared reservations. No keys, prompts or provider network requests."""
import hmac
import json
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class BudgetError(RuntimeError):
    def __init__(self, reason, status=402):
        super().__init__(reason)
        self.reason, self.status = reason, status


class Ledger:
    def __init__(self, path, profile):
        self.path, self.profile = str(path), dict(profile)
        self.limit = profile['campaign_limit_fen'] * profile['package_tokens'] // profile['package_price_fen']
        if self.limit <= 0:
            raise ValueError('Positive budget required')
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, job TEXT NOT NULL, arm TEXT NOT NULL, reserved INTEGER NOT NULL, actual INTEGER, state TEXT NOT NULL, created REAL NOT NULL)')
            encoded = json.dumps(profile, sort_keys=True)
            old = db.execute("SELECT value FROM meta WHERE key='profile'").fetchone()
            if old and old[0] != encoded:
                raise ValueError('Existing ledger profile differs; refusing reset or repricing')
            db.execute("INSERT OR IGNORE INTO meta VALUES ('profile',?)", (encoded,))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _status(self, db):
        settled, pending, uncertain = db.execute("SELECT COALESCE(SUM(CASE WHEN state='settled' THEN actual ELSE 0 END),0), COALESCE(SUM(CASE WHEN state='reserved' THEN reserved ELSE 0 END),0), COALESCE(SUM(CASE WHEN state='unknown' THEN reserved ELSE 0 END),0) FROM calls").fetchone()
        halt = db.execute("SELECT value FROM meta WHERE key='halt'").fetchone()
        return dict(limit_tokens=self.limit, settled_tokens=settled, reserved_tokens=pending,
                    uncertain_tokens=uncertain, remaining_tokens=self.limit-settled-pending-uncertain,
                    halt_reason=halt[0] if halt else None, campaign_limit_yuan=self.profile['campaign_limit_fen']/100)

    def status(self):
        with self.db() as db:
            return self._status(db)

    def reserve(self, request):
        p = self.profile
        if request.get('endpoint') != p['endpoint'] or request.get('model') != p['model']:
            raise BudgetError('pricing_provider_or_model_mismatch', 400)
        maximum = request.get('max_tokens')
        if type(maximum) is not int or not 0 < maximum <= p['max_output_tokens']:
            raise BudgetError('invalid_output_reservation', 400)
        if request.get('arm') not in ('kz', 'dsh', 'acceptance'):
            raise BudgetError('invalid_arm', 400)
        if not all(isinstance(request.get(k), str) and 0 < len(request[k]) <= 180 for k in ('id', 'job')):
            raise BudgetError('invalid_request_identity', 400)
        # Full model input ceiling + requested output, including cached input.
        # Conservative reservation is released only after trustworthy final usage.
        reserve = p['input_ceiling_tokens'] + maximum
        with self.db() as db:
            old = db.execute('SELECT job,arm,reserved,state FROM calls WHERE id=?', (request['id'],)).fetchone()
            if old:
                if old != (request['job'], request['arm'], reserve, 'reserved'):
                    raise BudgetError('lease_already_used_or_changed', 409)
                return dict(id=request['id'], reserved_tokens=reserve)
            status = self._status(db)
            if status['halt_reason']:
                raise BudgetError(status['halt_reason'])
            if status['settled_tokens'] + status['uncertain_tokens'] + reserve > self.limit:
                raise BudgetError('campaign_budget_exhausted')
            if status['remaining_tokens'] < reserve:
                raise BudgetError('waiting_for_inflight_usage', 409)
            db.execute('INSERT INTO calls VALUES (?,?,?,?,NULL,?,?)',
                       (request['id'], request['job'], request['arm'], reserve, 'reserved', time.time()))
        return dict(id=request['id'], reserved_tokens=reserve)

    def settle(self, request):
        actual = request.get('tokens')
        if actual is not None and (type(actual) is not int or actual < 0):
            raise BudgetError('invalid_usage', 400)
        with self.db() as db:
            row = db.execute('SELECT reserved,actual,state FROM calls WHERE id=?', (request.get('id'),)).fetchone()
            if row is None:
                raise BudgetError('unknown_lease', 400)
            reserve, previous, state = row
            if state != 'reserved':
                if previous != actual:
                    raise BudgetError('conflicting_settlement', 409)
                return self._status(db)
            db.execute('UPDATE calls SET actual=?,state=? WHERE id=?',
                       (actual, 'unknown' if actual is None else 'settled', request['id']))
            # An explicitly conservative settlement retains the entire maximum
            # request charge. Further requests can proceed within the SAME cap.
            # Default callers still fail closed on absent usage.
            if (actual is None and request.get('conservative') is not True) or (actual is not None and actual > reserve):
                db.execute("INSERT OR REPLACE INTO meta VALUES ('halt',?)",
                           ('usage_unavailable' if actual is None else 'usage_exceeds_model_ceiling',))
            return self._status(db)

    def reconcile_restart(self):
        # Do not silently free reservations after a crash: the provider may have billed.
        with self.db() as db:
            if db.execute("SELECT 1 FROM calls WHERE state='reserved' LIMIT 1").fetchone():
                db.execute("UPDATE calls SET state='unknown' WHERE state='reserved'")
                db.execute("INSERT OR REPLACE INTO meta VALUES ('halt','unsettled_requests_after_restart')")

    def halt(self, reason):
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO meta VALUES ('halt',?)", (reason,))


def server_for(ledger, token, host='10.123.0.1', port=28485):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            status = 200
            try:
                if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+token):
                    raise BudgetError('unauthorized', 403)
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8192:
                    raise BudgetError('invalid_body_size', 400)
                body = json.loads(self.rfile.read(size))
                if self.path == '/reserve': value = ledger.reserve(body)
                elif self.path == '/settle': value = ledger.settle(body)
                elif self.path == '/status': value = ledger.status()
                else: raise BudgetError('unknown_route', 404)
            except BudgetError as error:
                status, value = error.status, dict(error=error.reason)
            except Exception:
                status, value = 503, dict(error='budget_service_unavailable')
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    return ThreadingHTTPServer((host, port), Handler)


class BudgetService:
    def __init__(self, root, host='10.123.0.1', port=28485):
        self.profile = json.loads((Path(root)/'budget-profile.json').read_text())
        self.ledger = Ledger(Path(root)/'spending.sqlite', self.profile)
        self.ledger.reconcile_restart()
        self.token = secrets.token_urlsafe(32)
        self.url = f'http://{host}:{port}'
        self.server = server_for(self.ledger, self.token, host, port)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def snapshot(self): return self.ledger.status()
    def close(self):
        self.server.shutdown()
        self.server.server_close()
