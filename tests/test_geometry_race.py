import json
from pathlib import Path

from app.db import query,transaction
from app.ingestion import add_sources
from app.preprocessing import preprocess
from app.services import configure_source
from app.worker import Worker
from conftest import make_job


CORNERS=[[154,262],[918,252],[968,1185],[138,1200]]


async def test_stale_automatic_failure_cannot_overwrite_saved_corners(data,photo,monkeypatch):
    job=make_job(data);add_sources(job,[('photo.png',photo)])
    def old_attempt(source):
        # Reproduce a web save committing while the worker detects the old image.
        with transaction() as db:
            db.execute("UPDATE sources SET version=version+1,state='pending',geometry=? WHERE id=?",(json.dumps([dict(section='morning',corners=CORNERS)]),source['id']))
        raise ValueError('Old automatic grid failure')
    monkeypatch.setattr('app.worker.preprocess',old_attempt)
    worker=Worker();worker.acquire()
    try:await worker.tick()
    finally:worker.release()
    source=query('SELECT * FROM sources',one=True)
    assert source['version']==2 and source['state']=='pending'
    assert not query("SELECT * FROM issues WHERE kind='geometry'")
    assert not query('SELECT * FROM exports')


def test_stale_success_cannot_commit_old_pages_or_tasks(data,monkeypatch):
    job=make_job(data)
    add_sources(job,[('real.jpg',(Path(__file__).parent/'fixtures/morning-2026-10-09.jpg').read_bytes())])
    source=query('SELECT * FROM sources',one=True)
    configure_source(job,source['id'],geometry=[dict(section='morning',corners=CORNERS)])
    source=query('SELECT * FROM sources',one=True)
    from app.preprocessing import save_image
    changed=[False]
    def save_during_preprocessing(path,image):
        if not changed[0]:
            changed[0]=True
            configure_source(job,source['id'],geometry=[dict(section='morning',corners=CORNERS,layout='legacy')])
        return save_image(path,image)
    monkeypatch.setattr('app.preprocessing.save_image',save_during_preprocessing)
    preprocess(source)
    current=query('SELECT * FROM sources',one=True)
    assert current['version']==source['version']+1 and current['state']=='pending'
    assert not query('SELECT * FROM tasks')
    assert not query('SELECT * FROM pages')
    preprocess(current)
    assert query('SELECT state FROM sources',one=True)['state']=='processing'
    assert {t['version'] for t in query('SELECT * FROM tasks')}=={current['version']}
