"""Process-safe experiment and cumulative arm/task accounting, including probes."""
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class SharedBudget:
    def __init__(self, config):
        self.path=Path(config['path'])
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.bucket=config['bucket']
        self.total_limit=float(config['total_limit_cny'])
        self.bucket_limit=float(config['bucket_limit_cny'])
        if not self.bucket or not 0 < self.bucket_limit <= self.total_limit:
            raise ValueError('Invalid shared budget limits')
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, bucket TEXT, role TEXT, charge REAL, status TEXT, created REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS limits (name TEXT PRIMARY KEY, amount REAL)')
            for name,value in [('total',self.total_limit),('bucket:'+self.bucket,self.bucket_limit)]:
                db.execute('INSERT OR IGNORE INTO limits VALUES (?,?)',(name,value))
                if db.execute('SELECT amount FROM limits WHERE name=?',(name,)).fetchone()[0]!=value:
                    raise ValueError('Existing budget limit cannot be silently changed')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self,role,amount):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            total=db.execute('SELECT COALESCE(SUM(charge),0) FROM calls').fetchone()[0]
            bucket=db.execute('SELECT COALESCE(SUM(charge),0) FROM calls WHERE bucket=?',(self.bucket,)).fetchone()[0]
            if total+amount > self.total_limit+1e-12 or bucket+amount > self.bucket_limit+1e-12:
                raise ValueError('Shared experiment or cumulative task budget cannot reserve next request')
            identity=str(uuid.uuid4())
            db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?)',(identity,self.bucket,role,amount,'reserved',time.time()))
        return identity

    def settle(self,identity,amount):
        with self.connect() as db:
            cursor=db.execute('UPDATE calls SET charge=?,status=? WHERE id=? AND bucket=?',(amount,'settled',identity,self.bucket))
            if cursor.rowcount!=1:raise ValueError('Unknown shared reservation')
