"""Persistent, process-safe provider circuit. No GPT task or model call."""
from pathlib import Path
import sqlite3,time

class Circuit:
    def __init__(self,path,clock=time.time,cooldown=60,success_gap=10):
        self.path=str(path);self.clock=clock;self.cooldown=cooldown;self.success_gap=success_gap
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS circuit (id INTEGER PRIMARY KEY, state TEXT, generation INTEGER, failures INTEGER, successes INTEGER, retry_at REAL, last_success REAL, reason TEXT)')
            db.execute("INSERT OR IGNORE INTO circuit VALUES(1,'open',0,0,0,0,0,'startup_validation_required')")
            db.execute('CREATE TABLE IF NOT EXISTS events(time REAL,kind TEXT,generation INTEGER,reason TEXT)')
    def db(self):
        db=sqlite3.connect(self.path,timeout=20);db.row_factory=sqlite3.Row
        db.execute('PRAGMA busy_timeout=20000');return db
    def status(self):
        with self.db() as db:return dict(db.execute('SELECT * FROM circuit WHERE id=1').fetchone())
    def fail(self,reason):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE circuit SET state='open',generation=generation+1,failures=failures+1,successes=0,retry_at=?,last_success=0,reason=? WHERE id=1",(self.clock()+self.cooldown,str(reason)[:180]))
            generation=db.execute('SELECT generation FROM circuit').fetchone()[0]
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(self.clock(),'open',generation,str(reason)[:180]))
    def probe_ticket(self):
        s=self.status()
        return s['generation'] if self.clock()>=max(s['retry_at'],s['last_success']+self.success_gap) else None
    def success(self,generation,paid_canary=False):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');s=dict(db.execute('SELECT * FROM circuit WHERE id=1').fetchone())
            # A probe that started before a concurrent transport failure cannot
            # close the circuit or authorize the next paid task.
            if s['generation']!=generation:return False
            if paid_canary:
                if s['successes']<3:return False
                db.execute("UPDATE circuit SET state='closed',reason=NULL WHERE id=1")
                db.execute('INSERT INTO events VALUES(?,?,?,?)',(self.clock(),'closed',generation,'three spaced checks and full Messages canary'))
                return True
            if self.clock()<max(s['retry_at'],s['last_success']+self.success_gap):return False
            db.execute("UPDATE circuit SET state='half_open',successes=successes+1,last_success=? WHERE id=1",(self.clock(),))
            return True
    def admit(self):return self.status()['state']=='closed'

def provider_fault(result):
    """A numeric score never cancels a transport/accounting failure."""
    stops=result.get('stops',{})
    provider=stops.get('provider-stop.json') or result.get('provider_stop') or {}
    budget=stops.get('budget-stop.json') or result.get('budget_stop') or {}
    return provider.get('kind') in {'transport','protocol','temporary_exhausted','credentials','quota','accounting'} or budget.get('reason')=='usage_unavailable'
