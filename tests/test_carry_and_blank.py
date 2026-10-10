import json
import uuid
import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.db import transaction,query
from app.schemas import Reading
from app.reconciliation import reconcile
from app.services import edit_cell
from app.main import app
from conftest import make_job,result,reading


@pytest.fixture
def rough(monkeypatch):
    monkeypatch.setattr(settings,'rough_counts',True)
    monkeypatch.setattr(settings,'verification','off')


@pytest.mark.parametrize('mark',['↓','↑','→','↧','"',"''",'“','”','〃','ditto','down arrow'])
def test_copy_marker(rough,mark):
    r=Reading(raw_text=mark,kind='unclear',terms=None,ambiguous=True,reason=None)
    assert r.kind=='carry' and r.raw_text==mark


@pytest.mark.parametrize('raw,kind,reason',[(None,'blank','uncertain'),('  ','blank',None),('probably blank','unclear',None),('blank?','unclear',None),('?', 'unclear','Looks blank'),(None,'unclear','Probably empty')])
def test_likely_blank(rough,raw,kind,reason):
    r=Reading(raw_text=raw,kind=kind,terms=None,ambiguous=True,reason=reason)
    assert r.kind=='blank' and not r.ambiguous and r.value is None


def source_with_bands(data,job,bands,day='2026-10-09'):
    sid=uuid.uuid4().hex
    with transaction() as db:
        db.execute('INSERT INTO sources(id,job_id,hash,filename,path,state,assigned_date) VALUES(?,?,?,?,?,?,?)',
            (sid,job,sid,'test.png','fixture','processing',day))
        for rows in bands:
            r=result([row['time'] for row in rows],day);r['rows']=rows
            db.execute('INSERT INTO tasks(job_id,source_id,key,version,pass,crop,expected,state,result) VALUES(?,?,?,?,?,?,?,?,?)',
                (job,sid,uuid.uuid4().hex,1,'A','fixture',json.dumps([row['time'] for row in rows]),'succeeded',json.dumps(r)))
    return sid


def row(time,public,group,dry):return dict(time=time,public=public,group=group,dry=dry)


def marker(raw='↓'):return dict(raw_text=raw,kind='unclear',terms=None,ambiguous=True,reason='Arrow/ditto mark')


def test_chain_across_bands_and_edits(rough,data):
    job=make_job(data)
    first=row('05:15',reading(7),reading(32),reading(0))
    blank=dict(raw_text=None,kind='blank',terms=None,ambiguous=True,reason='Likely blank')
    second=row('05:30',marker(),marker('"'),blank)
    third=row('05:45',marker('〃'),marker('"'),marker())
    # Deliberately insert the last band first; reconciliation must use time order.
    sid=source_with_bands(data,job,[[third],[first,second]])
    reconcile(sid)
    cells={c['key']:c for c in query('SELECT * FROM cells')}
    assert cells['2026-10-09|05:45|public']['value']==7
    assert cells['2026-10-09|05:45|group']['value']==32
    assert cells['2026-10-09|05:45|dry']['value'] is None
    assert cells['2026-10-09|05:45|dry']['status']=='accepted'
    assert not query('SELECT * FROM issues WHERE resolved=0')
    provenance=json.loads(cells['2026-10-09|05:45|public']['provenance'])
    assert provenance[0]['carried_from']=='2026-10-09|05:30|public'
    edit_cell(job,'2026-10-09|05:15|public','value',0,'Correction','R')
    assert query('SELECT value FROM cells WHERE time="05:45" AND column_name="public"',one=True)['value']==0
    edit_cell(job,'2026-10-09|05:30|public','value',9,'Manual override','R')
    edit_cell(job,'2026-10-09|05:15|public','value',4,'Correction','R')
    assert query('SELECT value FROM cells WHERE time="05:45" AND column_name="public"',one=True)['value']==9


def test_later_upload_resolves_carry_and_no_skipping_missing_slot(rough,data):
    job=make_job(data)
    sid=source_with_bands(data,job,[[row('05:45',marker(),reading(0),reading(0))]])
    reconcile(sid)
    assert query('SELECT status FROM cells WHERE column_name="public"',one=True)['status']=='needs_review'
    earlier=source_with_bands(data,job,[[row('05:15',reading(6),reading(0),reading(0))]])
    reconcile(earlier)
    assert query('SELECT status FROM cells WHERE time="05:45" AND column_name="public"',one=True)['status']=='needs_review'
    middle=source_with_bands(data,job,[[row('05:30',reading(3),reading(0),reading(0))]])
    reconcile(middle)
    assert query('SELECT value FROM cells WHERE time="05:45" AND column_name="public"',one=True)['value']==3
    assert not query('SELECT * FROM issues WHERE resolved=0')


def test_first_row_does_not_copy_another_day(rough,data):
    job=make_job(data)
    yesterday=source_with_bands(data,job,[[row('21:45',reading(55),reading(0),reading(0))]],'2026-10-08')
    reconcile(yesterday)
    today=source_with_bands(data,job,[[row('05:15',marker(),reading(0),reading(0))]])
    reconcile(today)
    cell=query('SELECT * FROM cells WHERE date="2026-10-09" AND column_name="public"',one=True)
    assert cell['value'] is None and cell['status']=='needs_review'


def test_main_page_numbered_design(data):
    with TestClient(app) as client:
        html=client.get('/').text
        headings=['Choose the month','Add the workbook','Add the photos','Start the import']
        assert [html.index(h) for h in headings]==sorted(html.index(h) for h in headings)
        assert html.count('class="step-number"')==4
