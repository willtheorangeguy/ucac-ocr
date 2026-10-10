import json
import pytest
from app.db import transaction,query
from app.services import control
from app.worker import Worker
from app.exporting import export_job,recalculate
from conftest import make_job
from test_worker import add_tasks
from test_review import success_all


async def test_pause_after_active_request_checkpoints(data,photo,ollama):
    import asyncio
    job=make_job(data);add_tasks(data,job,photo);ollama.delay=.1
    worker=Worker();worker.acquire()
    try:
        active=asyncio.create_task(worker.tick())
        for _ in range(100):
            if ollama.started.is_set():break
            await asyncio.sleep(.01)
        control(job,'pause')
        await active
        assert query('SELECT state FROM jobs',one=True)['state']=='paused'
        assert query("SELECT count(*) AS n FROM tasks WHERE state='succeeded'",one=True)['n']==1
        await worker.tick()
        assert len(ollama.requests)==1
        control(job,'resume');await worker.tick()
        assert len(ollama.requests)==2
    finally:worker.release()


async def test_circuit_breaker_persisted_across_restart(data,photo,ollama):
    import asyncio
    job=make_job(data);add_tasks(data,job,photo);ollama.mode='503'
    worker=Worker();worker.acquire()
    try:
        for _ in range(5):await worker.tick();await asyncio.sleep(.1)
        assert len(ollama.requests)==5
    finally:worker.release()
    worker=Worker();worker.acquire()
    try:
        assert worker.failures==5
        ollama.mode='good';await asyncio.sleep(.1);await worker.tick()
        assert query("SELECT count(*) AS n FROM tasks WHERE state='succeeded'",one=True)['n']==1
        assert query('SELECT sum(content_failures) AS n FROM tasks',one=True)['n']==0
    finally:worker.release()


def test_export_failure_retry_and_edit_during_export(data,photo,monkeypatch):
    import app.exporting as ex
    from app.reconciliation import reconcile
    from app.services import edit_cell
    job=make_job(data);add_tasks(data,job,photo);success_all();reconcile(query('SELECT id FROM sources',one=True)['id'])
    original=ex.generate
    def fail(*a,**k):raise OSError('Disk failure')
    monkeypatch.setattr(ex,'generate',fail)
    with pytest.raises(OSError):export_job(job)
    assert not query('SELECT * FROM exports')
    changed=[False]
    def mutate(*a,**k):
        result=original(*a,**k)
        if not changed[0]:
            cell=query('SELECT key FROM cells WHERE column_name="public"',one=True)['key']
            edit_cell(job,cell,'value',9,'Review during export','R');changed[0]=True
        return result
    monkeypatch.setattr(ex,'generate',mutate)
    first=export_job(job)
    assert query('SELECT exported_revision FROM jobs',one=True)['exported_revision']<query('SELECT revision FROM jobs',one=True)['revision']
    second=export_job(job)
    assert second['revision']>first['revision']
    assert query('SELECT count(*) AS n FROM attempts',one=True)['n']==0
    from app.config import settings
    monkeypatch.setattr(settings,'libreoffice','missing-recalculation-engine')
    with pytest.raises(FileNotFoundError):recalculate(second['id'])
    from pathlib import Path
    assert Path(second['path']).exists()


def test_consistent_backup(data,photo,tmp_path):
    from app.cli import backup
    from pathlib import Path
    import sqlite3
    job=make_job(data);add_tasks(data,job,photo)
    dest=tmp_path/'backup';backup(dest)
    with sqlite3.connect(dest/'jobs.sqlite3') as db:
        template=db.execute('SELECT template FROM jobs').fetchone()[0]
        assert (dest/Path(template).relative_to(data)).exists()
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
