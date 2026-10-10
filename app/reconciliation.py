import json
from collections import defaultdict
from datetime import date
from .db import transaction, issue, bump
from .layout import COLUMNS, SCHEDULE, key
from .schemas import Reading, equivalent
from .config import settings


def resolve_carries(db,job,day):
    """Resolve in chronological order, independent of crops and upload order."""
    times=list(SCHEDULE)
    previous={time:times[i-1] if i else None for i,time in enumerate(times)}
    for cell in db.execute("SELECT * FROM cells WHERE job_id=? AND date=? AND kind='carry' AND reviewed=0 ORDER BY time,column_name",(job,day)).fetchall():
        above_time=previous.get(cell['time'])
        above_key=key(day,above_time,cell['column_name']) if above_time else None
        above=db.execute('SELECT * FROM cells WHERE job_id=? AND key=?',(job,above_key)).fetchone() if above_key else None
        observations=json.loads(cell['provenance'] or '[]')
        valid=above is not None and above['status']=='accepted'
        expected=above['value'] if valid else None
        if valid:
            for o in observations:
                if 'reading' not in o:valid=False;break
                reading=Reading.model_validate(o['reading'])
                if reading.kind!='carry' and (reading.kind=='unclear' or reading.value!=expected):valid=False;break
        if valid and settings.verification=='always':
            groups=defaultdict(dict)
            for o in observations:groups[(o.get('source'),o.get('version'))][o.get('pass_name')]=o['reading']
            valid=all('A' in g and 'B' in g and equivalent(g['A'],g['B']) for g in groups.values())
        for o in observations:
            if o.get('reading',{}).get('kind')=='carry':o['carried_from']=above_key
        db.execute('UPDATE cells SET value=?,status=?,provenance=? WHERE job_id=? AND key=?',
            (expected if valid else None,'accepted' if valid else 'needs_review',json.dumps(observations),job,cell['key']))
        if valid:
            db.execute("UPDATE issues SET resolved=1 WHERE job_id=? AND cell_key=? AND kind='cell'",(job,cell['key']))
        else:
            detail={'message':'The immediately preceding cell is unavailable or conflicts with another reading.','observations':observations}
            issue(db,job,'cell:'+cell['key'],'cell',detail,cell=cell['key'])
            db.execute('UPDATE issues SET detail=?,resolved=0 WHERE job_id=? AND key=?',(json.dumps(detail),job,'cell:'+cell['key']))


def reconcile(source_id):
    with transaction() as db:
        source=dict(db.execute('SELECT * FROM sources WHERE id=?',(source_id,)).fetchone())
        job=dict(db.execute('SELECT * FROM jobs WHERE id=?',(source['job_id'],)).fetchone())
        tasks=[dict(r) for r in db.execute('SELECT * FROM tasks WHERE source_id=? AND version=?',(source_id,source['version']))]
        if settings.verification=='off':tasks=[t for t in tasks if t['pass']=='A']
        results=[(t,json.loads(t['result'])) for t in tasks if t['state']=='succeeded']
        dates_seen={r['date'] for _,r in results if r['date'] is not None}
        headers=[r for t,r in results if not json.loads(t['expected'])]
        assigned=source['assigned_date']
        day=assigned or (next(iter(dates_seen)) if len(dates_seen)==1 and len(headers)>=(1 if settings.verification=='off' else 2) and all(r['date'] in dates_seen and not r['ambiguous'] for r in headers) else None)
        conflict=(len(dates_seen)>1 or (assigned and any(x!=assigned for x in dates_seen))) and not source['date_confirmed']
        if conflict or not day or not day.startswith(f"{job['year']:04}-{job['month']:02}-"):
            issue(db,job['id'],f'date:{source_id}:{source["version"]}','date',{'observed':sorted(dates_seen),'assigned':assigned,'message':'Assign/confirm date and reprocess; conflicting date needs explicit acknowledgement'},source_id)
            db.execute("UPDATE sources SET state='needs_review',observed_date=? WHERE id=?",(','.join(sorted(dates_seen)),source_id))
            bump(db,job['id']); return
        # Operator date confirmation overrides recognized dates only with audited explicit flag.
        db.execute('UPDATE sources SET observed_date=? WHERE id=?',(next(iter(dates_seen),None),source_id))
        observations=defaultdict(list)
        for t,result in results:
            expected=json.loads(t['expected'])
            for row in result['rows']:
                for c in COLUMNS:
                    reading=Reading.model_validate(row[c]).model_dump()
                    if result['ambiguous'] or result['section'] not in ('both','unknown','morning' if row['time']<'13:00' else 'afternoon'):
                        reading={**reading,'ambiguous':True,'reason':'Date/section/alignment uncertainty'}
                    observations[(row['time'],c)].append(dict(pass_name=t['pass'],reading=reading,task=t['id'],source=source_id,crop=t['crop'],version=source['version']))
        # Failed bands create missing observations, distinct from blanks.
        expected_times={time for t in tasks for time in json.loads(t['expected'])}
        for time in sorted(expected_times):
            for c in COLUMNS:
                obs=observations[(time,c)]
                k=key(day,time,c)
                a=[o for o in obs if o['pass_name']=='A']; b=[o for o in obs if o['pass_name']=='B']
                matches=bool(len(a)==1 and (settings.verification=='off' or len(b)==1 and equivalent(a[0]['reading'],b[0]['reading'])))
                first=Reading.model_validate(obs[0]['reading']) if obs else None
                accepted=matches and first and first.kind!='unclear' and (settings.rough_counts or not first.ambiguous)
                value=first.value if accepted else None
                kind=first.kind if first else 'failure'
                old=db.execute('SELECT * FROM cells WHERE job_id=? AND key=?',(job['id'],k)).fetchone()
                if old and old['reviewed']:
                    # Decisions are immutable to automatic processing; retain new evidence as an issue.
                    known=json.loads(old['provenance'] or '[]')
                    if not any(o.get('source')==source_id and o.get('version')==source['version'] for o in known):
                        issue(db,job['id'],f'locked:{source_id}:{source["version"]}:{k}','reviewed_new_evidence',{'observations':obs,'previous':dict(old)},source_id,k)
                    continue
                provenance=obs
                if old:
                    previous=json.loads(old['provenance'] or '[]')
                    # Reprocessing this source replaces its automatic evidence, never other sources.
                    other=[o for o in previous if o.get('source')!=source_id]
                    for o in other:
                        if 'template' in o and 'reading' not in o and old['value'] is not None:
                            o['reading']={'raw_text':str(old['value']),'kind':'integer','terms':[old['value']],'ambiguous':False,'reason':None}
                    provenance=other+obs
                    if other:
                        old_agreed=old['status']=='accepted' and old['value']==value and (settings.rough_counts or old['kind']==kind)
                        # Same totals from different sum terms do not count as agreement.
                        old_readings=[o['reading'] for o in other if 'reading' in o]
                        if not accepted or not old_agreed or (not settings.rough_counts and any(not equivalent(r,obs[0]['reading']) for r in old_readings)):accepted=False; value=None
                db.execute('INSERT INTO cells(job_id,key,date,time,column_name,value,kind,status,provenance) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(job_id,key) DO UPDATE SET value=excluded.value,kind=excluded.kind,status=excluded.status,provenance=excluded.provenance',
                    (job['id'],k,day,time,c,value,kind,'accepted' if accepted else 'needs_review',json.dumps(provenance)))
                if not accepted:issue(db,job['id'],'cell:'+k,'cell',{'message':'Missing pass, unclear ink, disagreement or conflicting sources','observations':provenance},source_id,k)
                else:db.execute('UPDATE issues SET resolved=1 WHERE job_id=? AND cell_key=? AND kind="cell"',(job['id'],k))
        resolve_carries(db,job['id'],day)
        db.execute("UPDATE sources SET state=? WHERE id=?",('deferred' if any(t['state']=='failed' for t in tasks) else 'succeeded',source_id))
        bump(db,job['id'])


def decide(job,issue_id,action,value,note,reviewer):
    if action not in ('value','blank','acknowledge'):raise ValueError('Choose value, blank or acknowledge')
    if action=='value' and (type(value) is not int or value<0 or value>1_000_000_000):raise ValueError('Nonnegative integer required')
    if not reviewer.strip():raise ValueError('Reviewer name required')
    import time
    with transaction() as db:
        row=db.execute('SELECT * FROM issues WHERE id=? AND job_id=?',(issue_id,job)).fetchone()
        if row is None:raise ValueError('Unknown issue')
        if row['cell_key']:
            if action=='acknowledge' and row['kind']!='reviewed_new_evidence':raise ValueError('Cell requires explicit numeric or blank decision')
            if action!='acknowledge':
                db.execute("UPDATE cells SET value=?,kind=?,status='accepted',reviewed=1 WHERE job_id=? AND key=?",(value if action=='value' else None,'integer' if action=='value' else 'blank',job,row['cell_key']))
            db.execute('UPDATE issues SET resolved=1 WHERE job_id=? AND cell_key=?',(job,row['cell_key']))
        else:
            if action!='acknowledge':raise ValueError('Source issues require acknowledgement or source repair')
            db.execute('UPDATE issues SET resolved=1 WHERE id=?',(issue_id,))
        db.execute('INSERT INTO decisions(job_id,issue_id,cell_key,action,value,note,reviewer,created) VALUES(?,?,?,?,?,?,?,?)',(job,issue_id,row['cell_key'],action,value,note,reviewer,time.time()))
        if row['cell_key']:
            cell=db.execute('SELECT date FROM cells WHERE job_id=? AND key=?',(job,row['cell_key'])).fetchone()
            if cell:resolve_carries(db,job,cell['date'])
        bump(db,job)
