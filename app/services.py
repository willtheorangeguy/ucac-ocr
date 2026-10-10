import json
import time
from datetime import date
from .db import query, transaction, bump
from .reconciliation import reconcile


def status(job):
    item=query('SELECT * FROM jobs WHERE id=?',(job,),True)
    if not item:raise ValueError('Unknown job')
    item['sources']=query('SELECT * FROM sources WHERE job_id=? ORDER BY rowid',(job,))
    item['tasks']=query('SELECT * FROM tasks WHERE job_id=? ORDER BY id',(job,))
    item['issues']=query('SELECT * FROM issues WHERE job_id=? AND resolved=0 ORDER BY id',(job,))
    item['exports']=query('SELECT * FROM exports WHERE job_id=? ORDER BY revision DESC',(job,))
    item['worker']=query('SELECT * FROM worker_owner WHERE singleton=1',one=True)
    item['attempts']=query('SELECT a.* FROM attempts a JOIN tasks t ON t.id=a.task_id WHERE t.job_id=? ORDER BY a.id DESC',(job,))
    item['cells']=query('SELECT * FROM cells WHERE job_id=? ORDER BY key',(job,))
    durations=[a['finished']-a['started'] for a in item['attempts'] if a['status']=='succeeded']
    pending=sum(t['state'] in ('pending','retry_wait','in_flight') for t in item['tasks'])
    item['eta_seconds']=sum(durations)/len(durations)*pending if len(durations)>=3 else None
    return item


def control(job,action):
    if action=='refresh':return refresh_counts(job)
    with transaction() as db:
        current=db.execute('SELECT state FROM jobs WHERE id=?',(job,)).fetchone()
        if not current:raise ValueError('Unknown job')
        if action in ('pause','cancel'):
            db.execute('UPDATE jobs SET state=?,updated=? WHERE id=?',('paused' if action=='pause' else 'cancelled',time.time(),job))
        elif action=='resume':db.execute("UPDATE jobs SET state='queued',diagnostic=NULL WHERE id=?",(job,))
        elif action=='retry':
            db.execute("UPDATE tasks SET state='pending',content_failures=0,availability_failures=0,next_at=0 WHERE job_id=? AND state='failed'",(job,))
            db.execute("UPDATE sources SET state='processing' WHERE job_id=? AND state='deferred'",(job,))
            db.execute("UPDATE issues SET resolved=1 WHERE job_id=? AND kind='failed_task'",(job,));bump(db,job)
        elif action=='coverage':
            db.execute('UPDATE jobs SET coverage_ack=1 WHERE id=?',(job,))
            db.execute('INSERT INTO decisions(job_id,action,note,reviewer,created) VALUES(?,?,?,?,?)',(job,'coverage','Missing days acknowledged as no source/not applicable','operator',time.time()));bump(db,job)
        else:raise ValueError('Unknown action')


def refresh_counts(job):
    from .config import settings
    if query("SELECT 1 FROM tasks WHERE job_id=? AND state='in_flight'",(job,),True):
        raise ValueError('Pause and wait for active OCR before refreshing counts')
    with transaction() as db:
        if not db.execute('SELECT 1 FROM jobs WHERE id=?',(job,)).fetchone():raise ValueError('Unknown job')
        if settings.verification=='off':
            db.execute("UPDATE tasks SET state='skipped' WHERE job_id=? AND pass='B' AND state IN ('pending','retry_wait','failed')",(job,))
            db.execute("UPDATE issues SET resolved=1 WHERE job_id=? AND kind='failed_task' AND key IN (SELECT 'task:'||id FROM tasks WHERE pass='B' AND state='skipped')",(job,))
        db.execute('INSERT INTO decisions(job_id,action,note,reviewer,created) VALUES(?,?,?,?,?)',
            (job,'count_profile',json.dumps({'rough_counts':settings.rough_counts,'verification':settings.verification}), 'operator',time.time()))
    for source in query("SELECT * FROM sources WHERE job_id=? AND state IN ('succeeded','deferred','needs_review')",(job,)):
        if query("SELECT 1 FROM tasks WHERE source_id=? AND version=? AND pass='A' AND state='succeeded'",(source['id'],source['version']),True):
            reconcile(source['id'])


def configure_source(job,sid,assigned_date=None,geometry=None,reviewer='operator',confirm=False):
    rerun=False
    with transaction() as db:
        source=db.execute('SELECT * FROM sources WHERE id=? AND job_id=?',(sid,job)).fetchone()
        if not source:raise ValueError('Unknown source')
        j=db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
        if db.execute("SELECT 1 FROM tasks WHERE source_id=? AND state='in_flight'",(sid,)).fetchone():raise ValueError('Pause and wait for active request before changing source')
        if assigned_date:
            d=date.fromisoformat(assigned_date)
            if (d.year,d.month)!=(j['year'],j['month']):raise ValueError('Date outside selected month')
        if geometry:
            from .preprocessing import rectify,identify_section
            from PIL import Image
            specs=geometry
            if not isinstance(specs,list) or not 1<=len(specs)<=2:raise ValueError('One or two table definitions required')
            for spec in specs:
                if spec['section']=='auto':spec['section']=identify_section(Image.open(source['normalized']).convert('RGB'),spec['corners'])
                if spec['section'] not in ('morning','afternoon'):raise ValueError('Invalid section')
                rectify(Image.open(source['normalized']).convert('RGB'),spec['corners'])
            db.execute("UPDATE sources SET geometry=?,version=version+1,state='pending' WHERE id=?",(json.dumps(geometry),sid))
            db.execute("UPDATE tasks SET state='failed' WHERE source_id=? AND state IN ('pending','retry_wait')",(sid,))
            rerun=True
        if assigned_date:
            db.execute('UPDATE sources SET assigned_date=?,date_confirmed=? WHERE id=?',(assigned_date,int(confirm),sid))
        db.execute('UPDATE issues SET resolved=1 WHERE job_id=? AND source_id=? AND kind IN (\'geometry\',\'date\',\'failed_task\')',(job,sid))
        db.execute('INSERT INTO decisions(job_id,action,note,reviewer,created) VALUES(?,?,?,?,?)',(job,'configure_source',json.dumps({'source':sid,'date':assigned_date,'confirm_conflict':confirm,'geometry':geometry}),reviewer,time.time()))
        bump(db,job)
    if not rerun and query('SELECT 1 FROM tasks WHERE source_id=? AND state="succeeded"',(sid,),True):reconcile(sid)


def reprocess(job,sid):
    with transaction() as db:
        if db.execute("SELECT 1 FROM tasks WHERE source_id=? AND state='in_flight'",(sid,)).fetchone():raise ValueError('Wait for active request before reprocessing')
        if not db.execute('SELECT 1 FROM sources WHERE id=? AND job_id=?',(sid,job)).fetchone():raise ValueError('Unknown source')
        db.execute("UPDATE sources SET version=version+1,state='pending' WHERE id=?",(sid,))
        db.execute("UPDATE tasks SET state='failed' WHERE source_id=? AND state IN ('pending','retry_wait')",(sid,));bump(db,job)


def edit_cell(job,cell_key,action,value,note,reviewer):
    from .db import issue
    from .reconciliation import decide
    import uuid
    with transaction() as db:
        if not db.execute('SELECT 1 FROM cells WHERE job_id=? AND key=?',(job,cell_key)).fetchone():raise ValueError('Unknown cell; no source provenance')
        k='manual:'+uuid.uuid4().hex
        issue(db,job,k,'cell',{'message':'Operator correction'},cell=cell_key)
        issue_id=db.execute('SELECT id FROM issues WHERE job_id=? AND key=?',(job,k)).fetchone()[0]
    decide(job,issue_id,action,value,note,reviewer)
