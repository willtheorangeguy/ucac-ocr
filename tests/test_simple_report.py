import json,time
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.db import query,transaction
from app.storage import atomic_write
from app.services import configure_source
from app.ingestion import add_sources
from conftest import make_job


def test_numbered_report_and_clean_existing_download(data):
    job=make_job(data)
    path=data/job/'exports/old-needs-review.xlsx';atomic_write(path,b'fixture-download')
    with transaction() as db:
        export=db.execute('INSERT INTO exports(job_id,revision,path,checksum,draft,created,report) VALUES(?,?,?,?,?,?,?)',(job,1,str(path),'fixture',1,time.time(),'{}')).lastrowid
    with TestClient(app) as client:
        html=client.get('/jobs/'+job).text
        headings=['Check the table boxes','Track progress','Fix flagged images','Download the workbook']
        assert [html.index(h) for h in headings]==sorted(html.index(h) for h in headings)
        for old in ('Add photos','All extracted cells','Attempts and evidence','Export approved snapshot','Cancel batch','Review note','Connection</a>'):
            assert old not in html
        response=client.get('/files/export/'+str(export))
        assert response.status_code==200
        assert '2026-10-headcounts.xlsx' in response.headers['content-disposition']
        assert 'needs-review' not in response.headers['content-disposition']
        assert path.exists()  # Old artifact remains immutable.


def test_four_corners_detect_section_without_extra_input(data):
    job=make_job(data)
    photo=Path(__file__).parent/'fixtures/morning-2026-10-09.jpg'
    add_sources(job,[(photo.name,photo.read_bytes())])
    source=query('SELECT * FROM sources',one=True)
    configure_source(job,source['id'],geometry=[{'section':'auto','corners':[[154,262],[918,252],[968,1185],[138,1200]]}])
    saved=query('SELECT * FROM sources',one=True)
    assert json.loads(saved['geometry'])[0]['section']=='morning'
    assert saved['state']=='pending'
