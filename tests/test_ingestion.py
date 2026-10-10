import io
import zipfile
import pytest
from app.config import settings
from app.ingestion import add_sources,expand,decode
from app.db import query
from conftest import make_job


def test_decoded_dedup_and_corrupt_continue(data,photo):
    job=make_job(data)
    assert add_sources(job,[('a.png',photo),('duplicate.jpg',photo),('corrupt.jpg',b'bad')])==2
    sources=query('SELECT * FROM sources')
    assert len(sources)==2
    assert sum(s['state']=='failed' for s in sources)==1
    assert query('SELECT * FROM issues')[0]['kind']=='invalid_source'
    assert add_sources(job,[('again.png',photo)])==0


@pytest.mark.parametrize('name',['../evil.jpg','/root/a.jpg','C:\\a.jpg','x/../../a.jpg'])
def test_zip_paths(name):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr(name,b'a')
    with pytest.raises(ValueError):expand([('files.zip',b.getvalue())])


def test_zip_limits(monkeypatch):
    monkeypatch.setattr(settings,'max_file_bytes',5)
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('a.png',b'x'*6)
    with pytest.raises(ValueError):expand([('files.zip',b.getvalue())])


def test_real_photo_geometry(data):
    from pathlib import Path
    from app.preprocessing import preprocess
    from app.services import configure_source
    job=make_job(data)
    add_sources(job,[('reference.jpg',(Path(__file__).parent/'fixtures/morning-2026-10-09.jpg').read_bytes())])
    s=query('SELECT * FROM sources',one=True)
    configure_source(job,s['id'],'2026-10-09',[{'section':'morning','corners':[[154,262],[918,252],[968,1185],[138,1200]]}])
    preprocess(query('SELECT * FROM sources',one=True))
    tasks=query('SELECT * FROM tasks')
    import json
    assert len(tasks)==19
    for pass_name in ('A','B'):
        times=[t for task in tasks if task['pass']==pass_name for t in json.loads(task['expected'])]
        assert len(times)==31 and times[0]=='05:15' and times[-1]=='12:45'
