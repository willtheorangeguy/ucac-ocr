import json
from pathlib import Path
import pytest
from app.config import settings
from app.schemas import Reading, QuickExtraction
from app.count_text import numeric_text
from app.db import query,transaction
from app.reconciliation import reconcile
from conftest import make_job,result
from test_worker import add_tasks


@pytest.fixture
def fast(monkeypatch):
    for k,v in dict(rough_counts=True,verification='off',think=False,rows_per_band=12,num_ctx=8192,num_predict=4096).items():monkeypatch.setattr(settings,k,v)


@pytest.mark.parametrize('raw,value',[('O',0),('o',0),('Q',0),('D',0),('L',1),('l',1),('I',1),('|',1),('S',5),('Z',2),('G',6),('B',8),('lO',10),('3O + L',31),('B + Z + S',15)])
def test_letter_substitutions(fast,raw,value):
    r=Reading(raw_text=raw,kind='unclear',terms=None,ambiguous=True,reason=None)
    assert r.value==value and r.raw_text==raw
    assert 'normalized' in r.reason


def test_compact_counts_blank_unknown_and_local_sums(fast):
    x=QuickExtraction.model_validate({'rows':[{'time':'05:15','public':'L','group':'30 + 2','dry':None}]}).expand().check(['05:15'])
    assert x.rows[0].public.value==1 and x.rows[0].group.value==32 and x.rows[0].dry.kind=='blank'
    assert numeric_text('Staff') is None
    r=Reading(raw_text='?',kind='integer',terms=[0],ambiguous=False,reason=None)
    assert r.kind=='unclear' and r.value is None
    assert numeric_text('2 * 3') is None
    numeric=QuickExtraction.model_validate({'rows':[{'time':'05:15','public':0,'group':32,'dry':2}]}).expand()
    assert numeric.rows[0].public.value==0 and numeric.rows[0].group.value==32


def test_single_pass_accepts_and_ignores_old_b_disagreement(fast,data,photo):
    job=make_job(data);add_tasks(data,job,photo)
    with transaction() as db:
        for t in db.execute('SELECT * FROM tasks').fetchall():
            r=result(['05:15']);r['rows'][0]['public'].update(raw_text='O',terms=[0])
            if t['pass']=='B':r['rows'][0]['group'].update(raw_text='99',terms=[99])
            db.execute("UPDATE tasks SET state='succeeded',result=? WHERE id=?",(json.dumps(r),t['id']))
    reconcile(query('SELECT id FROM sources',one=True)['id'])
    assert query('SELECT value FROM cells WHERE column_name="public"',one=True)['value']==0
    assert query('SELECT value FROM cells WHERE column_name="group"',one=True)['value']==32
    assert not query('SELECT * FROM issues WHERE resolved=0')


def test_fast_photo_needs_four_requests(fast,data):
    from app.ingestion import add_sources
    from app.services import configure_source
    from app.preprocessing import preprocess
    job=make_job(data)
    add_sources(job,[('reference.jpg',(Path(__file__).parent/'fixtures/morning-2026-10-09.jpg').read_bytes())])
    s=query('SELECT * FROM sources',one=True)
    configure_source(job,s['id'],'2026-10-09',[{'section':'morning','corners':[[154,262],[918,252],[968,1185],[138,1200]]}])
    preprocess(query('SELECT * FROM sources',one=True))
    tasks=query('SELECT * FROM tasks')
    assert len(tasks)==4 and all(t['pass']=='A' for t in tasks)
    assert [len(json.loads(t['expected'])) for t in tasks]==[0,12,12,7]


async def test_request_disables_thinking(fast,ollama,data,photo,tmp_path):
    from app.ollama_client import extract
    p=tmp_path/'crop.png';p.write_bytes(photo)
    await extract(p,['05:15'],tmp_path/'raw.ndjson')
    request=ollama.requests[0]
    assert request['think'] is False
    assert request['options']['num_ctx']==8192
    assert set(request['format']['properties'])=={'rows'}
