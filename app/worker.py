import asyncio
import json
import logging
import logging.handlers
import random
import time
import uuid
from pathlib import Path
from filelock import FileLock, Timeout
from .config import settings
from .db import migrate, transaction, query, issue, bump
from .preprocessing import preprocess, VERSION, save_image
from .prompts import VERSION as PROMPT_VERSION, SCHEMA_VERSION
from .ollama_client import preflight, health, extract, AvailabilityError, ContentError, PermanentError, ResourceError
from .reconciliation import reconcile
from .exporting import export_job

log=logging.getLogger('pool.worker')


class Worker:
    def __init__(self):
        self.generation=uuid.uuid4().hex
        self.lock=FileLock(settings.data_dir/'worker.lock')
        self.info=None
        self.failures=0
        self.cooldown=0

    def acquire(self):
        settings.data_dir.mkdir(parents=True,exist_ok=True)
        self.lock.acquire(timeout=0)
        migrate()
        with transaction() as db:
            interrupted=db.execute("SELECT COUNT(*) FROM tasks WHERE state='in_flight'").fetchone()[0]
            old=db.execute('SELECT cooldown_until FROM worker_owner WHERE singleton=1').fetchone()
            self.cooldown=max(time.time()+settings.disconnect_cooldown if interrupted else 0,old[0] if old else 0)
            for a in db.execute("SELECT id,raw_path FROM attempts WHERE status='in_flight'").fetchall():
                if a['raw_path'] and '.partial.ndjson' in a['raw_path']:
                    completed=Path(a['raw_path'].replace('.partial.ndjson','.ndjson'))
                    if completed.exists():db.execute('UPDATE attempts SET raw_path=? WHERE id=?',(str(completed),a['id']))
            db.execute("UPDATE attempts SET status='interrupted',finished=? WHERE status='in_flight'",(time.time(),))
            db.execute("UPDATE tasks SET state='retry_wait',owner=NULL,next_at=? WHERE state='in_flight'",(self.cooldown,))
            db.execute('INSERT INTO worker_owner(singleton,generation,heartbeat,cooldown_until) VALUES(1,?,?,?) ON CONFLICT(singleton) DO UPDATE SET generation=excluded.generation,heartbeat=excluded.heartbeat,active_task=NULL,cooldown_until=excluded.cooldown_until',(self.generation,time.time(),self.cooldown))
            # Try the improved detector once for old, unresolved failures. Never
            # reopen an acknowledged image or replace operator-supplied corners.
            retry=db.execute("SELECT DISTINCT s.id,s.job_id FROM sources s JOIN issues i ON i.source_id=s.id WHERE s.state='needs_review' AND s.normalized IS NOT NULL AND i.kind='geometry' AND i.resolved=0 AND COALESCE(json_extract(i.detail,'$.detector_version'),'')!=? AND NOT EXISTS(SELECT 1 FROM tasks t WHERE t.source_id=s.id AND t.version=s.version)",(VERSION,)).fetchall()
            for source in retry:
                db.execute("UPDATE sources SET state='pending',version=version+1 WHERE id=?",(source['id'],))
                db.execute("UPDATE issues SET resolved=1 WHERE source_id=? AND kind='geometry'",(source['id'],))
            for job_id in {s['job_id'] for s in retry}:bump(db,job_id)
            for a in db.execute('SELECT status FROM attempts ORDER BY id DESC LIMIT 5'):
                if a['status']=='AvailabilityError':self.failures+=1
                else:break

    def release(self):
        self.lock.release()

    async def heartbeat(self):
        while True:
            with transaction() as db:
                db.execute('UPDATE worker_owner SET heartbeat=? WHERE singleton=1 AND generation=?',(time.time(),self.generation))
            await asyncio.sleep(settings.heartbeat_interval)

    async def tick(self):
        if settings.verification=='off':
            with transaction() as db:
                db.execute("UPDATE tasks SET state='skipped' WHERE pass='B' AND state IN ('pending','retry_wait','failed')")
                db.execute("UPDATE issues SET resolved=1 WHERE kind='failed_task' AND key IN (SELECT 'task:'||id FROM tasks WHERE pass='B' AND state='skipped')")
        jobs=query("SELECT * FROM jobs WHERE state NOT IN ('paused','cancelled','ingesting') ORDER BY created")
        for job in jobs:
            for source in query("SELECT * FROM sources WHERE job_id=? AND state='pending'",(job['id'],)):
                try:await asyncio.to_thread(preprocess,source)
                except Exception as e:
                    with transaction() as db:
                        updated=db.execute("UPDATE sources SET state='needs_review' WHERE id=? AND version=? AND state='pending'",(source['id'],source['version']))
                        if not updated.rowcount:continue
                        issue(db,job['id'],f'geometry:{source["id"]}:{source["version"]}','geometry',{'error':str(e),'message':'Assign table corners and section','detector_version':VERSION},source['id'])
                        db.execute('UPDATE jobs SET revision=revision+1 WHERE id=?',(job['id'],))
            sources=query("SELECT * FROM sources WHERE job_id=? AND state='processing'",(job['id'],))
            for source in sources:
                active=query("SELECT count(*) AS n FROM tasks WHERE source_id=? AND version=? AND state IN ('pending','in_flight','retry_wait')",(source['id'],source['version']),True)['n']
                if not active:reconcile(source['id'])
        # A waiting band is deferred, so later images can still progress if the server works.
        task=query("SELECT t.* FROM tasks t JOIN jobs j ON j.id=t.job_id JOIN sources s ON s.id=t.source_id WHERE j.state NOT IN ('paused','cancelled','ingesting') AND s.state='processing' AND t.version=s.version AND t.state IN ('pending','retry_wait') AND t.next_at<=? ORDER BY j.created,s.rowid,t.id LIMIT 1",(time.time(),),True)
        if task:
            if settings.pause_start and settings.pause_end:
                from datetime import datetime
                now=datetime.now().strftime('%H:%M');start=settings.pause_start;end=settings.pause_end
                if (start<=now<end if start<end else now>=start or now<end):return False
            if time.time()<self.cooldown:return False
            if self.failures>=5:
                if not await health():self.cooldown=time.time()+settings.delays[-1];return False
                self.failures=0;self.info=None
            if self.info is None:
                try:self.info=await preflight()
                except PermanentError as e:
                    with transaction() as db:db.execute("UPDATE jobs SET state='paused',diagnostic=? WHERE id=?",(str(e),task['job_id']))
                    return True
                except AvailabilityError as e:
                    self.failures+=1;self.cooldown=time.time()+settings.delays[min(self.failures-1,len(settings.delays)-1)]
                    with transaction() as db:db.execute("UPDATE jobs SET state='waiting_for_ollama',diagnostic=? WHERE id=?",(str(e),task['job_id']))
                    return False
            await self.run_task(task)
            return True
        # Export only when all currently possible work has settled.
        for job in jobs:
            active=query("SELECT count(*) AS n FROM sources WHERE job_id=? AND state IN ('pending','processing')",(job['id'],),True)['n']
            latest=query('SELECT revision,exported_revision FROM jobs WHERE id=?',(job['id'],),True)
            if not active and latest['revision']>latest['exported_revision']:
                try:await asyncio.to_thread(export_job,job['id'])
                except Exception as e:
                    log.exception('Export failed')
                    with transaction() as db:db.execute("UPDATE jobs SET state='awaiting_review',diagnostic=? WHERE id=?",('Export failed; retry export: '+str(e),job['id']))
                    return False
                return True
        return False

    async def run_task(self,task):
        now=time.time()
        with transaction() as db:
            owner=db.execute('SELECT generation,active_task FROM worker_owner WHERE singleton=1').fetchone()
            if owner['generation']!=self.generation or owner['active_task'] is not None:raise RuntimeError('Inference ownership lost')
            current=db.execute('SELECT state FROM jobs WHERE id=?',(task['job_id'],)).fetchone()[0]
            if current in ('paused','cancelled'):return
            db.execute("UPDATE tasks SET state='in_flight',owner=?,attempts=attempts+1 WHERE id=?",(self.generation,task['id']))
            attempt=db.execute('INSERT INTO attempts(task_id,owner,started,status,profile,model,model_digest,prompt_version,schema_version,preprocessing_version) VALUES(?,?,?,?,?,?,?,?,?,?)',(task['id'],self.generation,now,'in_flight',json.dumps({'options':settings.profile(bool(task['smaller'])),'think':settings.think,'keep_alive':settings.keep_alive,'rough_counts':settings.rough_counts,'verification':settings.verification}),settings.ollama_model,self.info.get('digest'),PROMPT_VERSION,SCHEMA_VERSION,VERSION)).lastrowid
            raw=settings.data_dir/task['job_id']/'attempts'/f'{attempt}.partial.ndjson'
            db.execute('UPDATE attempts SET raw_path=? WHERE id=?',(str(raw),attempt))
            db.execute('UPDATE worker_owner SET active_task=? WHERE singleton=1',(task['id'],))
            db.execute("UPDATE jobs SET state='running',diagnostic=NULL WHERE id=?",(task['job_id'],))
        last=[0]
        def chunk(arrival):
            if arrival-last[0]>1:
                with transaction() as db:db.execute('UPDATE tasks SET latest_chunk=? WHERE id=?',(arrival,task['id']))
                last[0]=arrival
        try:
            result,metrics=await extract(task['crop'],json.loads(task['expected']),raw,bool(task['smaller']),chunk)
            completed=raw.with_name(f'{attempt}.ndjson'); raw.replace(completed)
            with transaction() as db:
                db.execute("UPDATE attempts SET status='succeeded',finished=?,metrics=?,raw_path=? WHERE id=?",(time.time(),json.dumps(metrics),str(completed),attempt))
                db.execute("UPDATE tasks SET state='succeeded',result=?,owner=NULL WHERE id=?",(result.model_dump_json(),task['id']))
                for row in result.rows:
                    for col in ('public','group','dry','external'):
                        db.execute('INSERT OR REPLACE INTO readings(task_id,cell_key,reading) VALUES(?,?,?)',(task['id'],row.time+'|'+col,getattr(row,col).model_dump_json()))
            self.failures=0
        except (AvailabilityError,ContentError,PermanentError,ResourceError) as e:
            delay=settings.delays[min(task['attempts'],len(settings.delays)-1)]*random.uniform(.9,1.1)
            state='retry_wait'; content=task['content_failures']; available=task['availability_failures']; smaller=task['smaller']
            if isinstance(e,AvailabilityError):
                available+=1;self.failures+=1;self.info=None
                self.cooldown=time.time()+max(settings.disconnect_cooldown,delay)
            elif isinstance(e,ContentError):
                content+=1
                if content==3:smaller=1
                if content>=4:state='failed'
            elif isinstance(e,ResourceError):
                if smaller:state='failed'
                else:smaller=1
            elif isinstance(e,PermanentError):state='retry_wait'
            split=[]
            expected=json.loads(task['expected'])
            if smaller and not task['smaller'] and len(expected)>1 and isinstance(e,(ContentError,ResourceError)):
                from PIL import Image
                im=Image.open(task['crop']); mid=len(expected)//2
                for label,start,stop in [('left',0,mid),('right',mid,len(expected))]:
                    part=im.crop((0,max(0,round(im.height*start/len(expected))-2),im.width,min(im.height,round(im.height*stop/len(expected))+2)))
                    path=save_image(Path(task['crop']).with_name(Path(task['crop']).stem+'-'+label+'.png'),part)
                    split.append((label,path,expected[start:stop]))
                state='superseded'
            with transaction() as db:
                db.execute('UPDATE attempts SET status=?,finished=?,error=? WHERE id=?',(type(e).__name__,time.time(),str(e),attempt))
                db.execute('UPDATE tasks SET state=?,owner=NULL,next_at=?,content_failures=?,availability_failures=?,smaller=? WHERE id=?',(state,time.time()+delay,content,available,smaller,task['id']))
                for label,path,subset in split:
                    db.execute('INSERT OR IGNORE INTO tasks(job_id,source_id,key,version,pass,crop,expected,smaller) VALUES(?,?,?,?,?,?,?,1)',(task['job_id'],task['source_id'],task['key']+':split:'+label,task['version'],task['pass'],path,json.dumps(subset)))
                if state=='failed':issue(db,task['job_id'],f'task:{task["id"]}','failed_task',{'error':str(e),'task':task['id']},task['source_id'])
                if isinstance(e,PermanentError):db.execute("UPDATE jobs SET state='paused',diagnostic=? WHERE id=? AND state!='cancelled'",(str(e),task['job_id']))
                elif isinstance(e,AvailabilityError):db.execute("UPDATE jobs SET state='waiting_for_ollama',diagnostic=? WHERE id=? AND state NOT IN ('paused','cancelled')",(str(e),task['job_id']))
        except Exception as e:
            log.exception('Local task/checkpoint failure')
            with transaction() as db:
                db.execute("UPDATE attempts SET status='local_error',finished=?,error=? WHERE id=?",(time.time(),str(e),attempt))
                db.execute("UPDATE tasks SET state='retry_wait',owner=NULL,next_at=? WHERE id=?",(time.time()+settings.disconnect_cooldown,task['id']))
                db.execute("UPDATE jobs SET state='paused',diagnostic=? WHERE id=? AND state!='cancelled'",('Local storage/checkpoint error; repair then resume: '+str(e),task['job_id']))
        finally:
            # extract has exited its response/client contexts before releasing the slot.
            with transaction() as db:db.execute('UPDATE worker_owner SET active_task=NULL,cooldown_until=? WHERE singleton=1 AND generation=?',(self.cooldown,self.generation))

    async def run(self):
        self.acquire()
        pulse=asyncio.create_task(self.heartbeat())
        try:
            while True:
                try:worked=await self.tick()
                except Exception:
                    log.exception('Worker iteration failed');worked=False
                await asyncio.sleep(.1 if worked else 2)
        finally:
            pulse.cancel()
            await asyncio.gather(pulse,return_exceptions=True)
            self.release()


def main():
    settings.data_dir.mkdir(parents=True,exist_ok=True)
    handler=logging.handlers.RotatingFileHandler(settings.data_dir/'worker.log',maxBytes=5_000_000,backupCount=4)
    logging.basicConfig(level=logging.INFO,handlers=[handler,logging.StreamHandler()])
    try:asyncio.run(Worker().run())
    except Timeout:raise SystemExit('Another worker owns the data directory')


if __name__=='__main__':main()
