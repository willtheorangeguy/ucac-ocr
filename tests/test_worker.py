import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
import pytest
from filelock import Timeout
from app.config import settings
from app.db import transaction, query
from app.worker import Worker
from conftest import make_job, result


def add_tasks(data,job,photo,count=1,mixed=False):
    path=data/'crop.png';path.write_bytes(photo)
    with transaction() as db:
        for i in range(count):
            sid=uuid.uuid4().hex
            db.execute('INSERT INTO sources(id,job_id,hash,filename,path,normalized,state,assigned_date) VALUES(?,?,?,?,?,?,?,?)',(sid,job,str(i),'mock.png',str(path),str(path),'processing','2026-10-09'))
            for pass_name in ('A','B'):
                times=['13:00','21:45'] if mixed and i%2 else ['05:15']
                db.execute('INSERT INTO tasks(job_id,source_id,key,version,pass,crop,expected) VALUES(?,?,?,?,?,?,?)',(job,sid,sid+pass_name,1,pass_name,str(path),json.dumps(times)))


async def test_62_sources_sequential_resume_and_autoexport(data,photo,ollama):
    job=make_job(data);add_tasks(data,job,photo,62,mixed=True)
    from app.ingestion import add_sources
    add_sources(job,[('deliberately-corrupt.jpg',b'broken photo')])
    worker=Worker();worker.acquire()
    try:
        for i in range(20):await worker.tick()
        finished=query("SELECT id FROM tasks WHERE state='succeeded'")
        assert len(finished)==20
    finally:worker.release()
    worker=Worker();worker.acquire()
    try:
        for _ in range(150):
            await worker.tick()
            if query('SELECT * FROM exports'):break
        assert len(ollama.requests)==124
        assert ollama.max_active==1
        assert len(query("SELECT id FROM tasks WHERE state='succeeded'"))==124
        assert query('SELECT state FROM jobs',one=True)['state']=='completed_with_issues'
        export=query('SELECT * FROM exports',one=True)
        assert Path(export['path']).is_file() and export['draft']==1
        assert len(query('SELECT * FROM cells'))==12
        assert query('SELECT value FROM cells WHERE column_name="group"',one=True)['value']==32
        await worker.tick()
        assert len(ollama.requests)==124
    finally:worker.release()


async def test_outage_is_recoverable_without_content_budget(data,photo,ollama):
    job=make_job(data);add_tasks(data,job,photo)
    worker=Worker();worker.acquire();ollama.mode='503'
    try:
        await worker.tick()
        task=query('SELECT * FROM tasks ORDER BY id LIMIT 1',one=True)
        assert task['state']=='retry_wait' and task['content_failures']==0
        ollama.mode='good';await asyncio.sleep(.1)
        for _ in range(4):await worker.tick()
        assert query('SELECT state FROM tasks WHERE id=?',(task['id'],),True)['state']=='succeeded'
    finally:worker.release()


def test_second_worker_refused_and_interrupted_checkpoint(data,photo):
    job=make_job(data);add_tasks(data,job,photo)
    with transaction() as db:
        tasks=db.execute('SELECT id FROM tasks ORDER BY id').fetchall()
        db.execute("UPDATE tasks SET state='succeeded',result=? WHERE id=?",(json.dumps(result(['05:15'])),tasks[0]['id']))
        db.execute("UPDATE tasks SET state='in_flight',owner='old' WHERE id=?",(tasks[1]['id'],))
        db.execute("INSERT INTO attempts(task_id,owner,status,started) VALUES(?,'old','in_flight',?)",(tasks[1]['id'],time.time()))
    first=Worker();first.acquire()
    try:
        with pytest.raises(Timeout):Worker().acquire()
        assert query('SELECT state FROM tasks ORDER BY id')[0]['state']=='succeeded'
        assert query('SELECT state FROM tasks ORDER BY id')[1]['state']=='retry_wait'
        assert query('SELECT status FROM attempts',one=True)['status']=='interrupted'
    finally:first.release()


def test_actual_killed_worker_reruns_only_interrupted_task(data,photo,ollama):
    job=make_job(data);add_tasks(data,job,photo)
    ollama.delay=30  # Leave enough time for Windows taskkill to reach the interpreter.
    env=os.environ.copy();env.update(DATA_DIR=str(data),OLLAMA_BASE_URL=settings.ollama_base_url,DISCONNECT_COOLDOWN='0.5',RETRY_DELAYS='0.01,0.02,0.03,0.04,0.05')
    executable=sys.executable
    if os.name=='nt':
        # Launch the actual interpreter, avoiding the venv launcher process.
        executable=sys._base_executable
        env['PYTHONPATH']=str(Path(sys.prefix)/'Lib/site-packages')+os.pathsep+str(Path.cwd())
    child_log=(data/'child.log').open('wb')
    process=subprocess.Popen([executable,'-m','app.worker'],env=env,stdout=child_log,stderr=child_log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        for _ in range(60):
            if ollama.started.wait(1) or process.poll() is not None:break
        assert ollama.started.is_set(), (data/'child.log').read_text(errors='replace')
        process.kill()
        process.wait(timeout=10)
        assert query("SELECT count(*) AS n FROM tasks WHERE state='in_flight'",one=True)['n']==1
        worker=Worker();worker.acquire()
        try:
            assert query('SELECT status FROM attempts',one=True)['status']=='interrupted'
            assert query("SELECT count(*) AS n FROM tasks WHERE state='retry_wait'",one=True)['n']==1
        finally:worker.release()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        child_log.close()


async def test_permanent_error_pauses_and_content_error_defers(data,photo,ollama):
    job=make_job(data);add_tasks(data,job,photo,2)
    worker=Worker();worker.acquire()
    try:
        ollama.mode='400';await worker.tick()
        assert query('SELECT state FROM jobs',one=True)['state']=='paused'
        from app.services import control
        control(job,'resume');ollama.mode='malformed'
        for _ in range(20):await asyncio.sleep(.05);await worker.tick()
        assert query("SELECT count(*) AS n FROM tasks WHERE state='failed'",one=True)['n']==4
        assert query('SELECT * FROM exports',one=True)['draft']==1
        assert query('SELECT * FROM issues')
    finally:worker.release()
