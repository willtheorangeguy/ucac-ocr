import json
import sqlite3
import time
from contextlib import contextmanager
from .config import settings


def connect():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(settings.data_dir / 'jobs.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=30000')
    return db


@contextmanager
def transaction():
    db = connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def query(sql, args=(), one=False):
    db=connect()
    try:
        rows = [dict(r) for r in db.execute(sql, args)]
    finally:db.close()
    return (rows[0] if rows else None) if one else rows


def migrate():
    from contextlib import closing
    with closing(connect()) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript((__import__('pathlib').Path(__file__).parent / 'migrations/001.sql').read_text())


def issue(db, job, key, kind, detail, source=None, cell=None):
    db.execute('INSERT OR IGNORE INTO issues(job_id,key,kind,detail,source_id,cell_key) VALUES(?,?,?,?,?,?)',
               (job, key, kind, json.dumps(detail), source, cell))


def bump(db, job):
    db.execute("UPDATE jobs SET revision=revision+1, state=CASE WHEN state IN ('paused','cancelled') THEN state ELSE 'queued' END, updated=? WHERE id=?", (time.time(), job))
