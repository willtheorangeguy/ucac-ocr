import json
from app.db import query,transaction
from app.worker import Worker
from conftest import make_job
from test_worker import add_tasks


async def test_oom_smaller_profile_and_band_split(data,photo,ollama):
    job=make_job(data);add_tasks(data,job,photo)
    with transaction() as db:
        db.execute('UPDATE tasks SET expected=?',(json.dumps(['05:15','05:30','05:45','06:00']),))
    worker=Worker();worker.acquire()
    try:
        ollama.mode='oom';await worker.tick()
        assert query('SELECT state FROM tasks ORDER BY id LIMIT 1',one=True)['state']=='superseded'
        split=query('SELECT * FROM tasks WHERE smaller=1 AND state="pending"')
        assert len(split)==2
        assert all(len(json.loads(t['expected']))==2 for t in split)
        ollama.mode='good'
        # Sibling pass stays first in image ordering; all still sequential.
        await worker.tick();await worker.tick()
        assert any(r['options']['num_ctx']==8192 and r['options']['num_predict']==16384 for r in ollama.requests)
        assert ollama.max_active==1
    finally:worker.release()
