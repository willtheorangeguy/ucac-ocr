import io
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.db import issue, migrate, query, transaction
from app.ingestion import add_sources
from app.main import app
from app.preprocessing import VERSION, detect, identify_section, preprocess
from app.services import configure_source, control
from app.worker import Worker
from conftest import make_job


def grid(rows=31, perspective=False, missing_column=False, missing_row=False, heading=True):
    image=Image.new('RGB',(1000,rows*24+200),'white');draw=ImageDraw.Draw(image)
    xs=[60,120,250,380,510,640,770,900];top=90;bottom=top+rows*24
    for i,x in enumerate(xs):
        if missing_column and i==3:continue
        draw.line((x,top if i==0 or not heading else top-24,x,bottom),fill='black',width=3)
    if heading:draw.line((xs[1],top-24,xs[-1],top-24),fill='black',width=3)
    for i in range(rows+1):
        if missing_row and i==12:continue
        draw.line((xs[0],top+i*24,xs[-1],top+i*24),fill='black',width=3)
    if perspective:
        w,h=image.size
        transform=cv2.getPerspectiveTransform(np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]),
                                            np.float32([[30,20],[w-60,0],[w-5,h-30],[5,h-1]]))
        image=Image.fromarray(cv2.warpPerspective(np.array(image),transform,(w,h),borderValue=(255,255,255)))
    buffer=io.BytesIO();image.save(buffer,format='PNG');return image,buffer.getvalue()


@pytest.mark.parametrize('rows,section',[(31,'morning'),(36,'afternoon'),(67,'both')])
@pytest.mark.parametrize('perspective',[False,True])
def test_detects_count_table_and_excludes_heading(rows,section,perspective):
    image,_=grid(rows,perspective)
    specs=detect(image)
    assert len(specs)==1 and specs[0]['section']==section
    assert identify_section(image,specs[0]['corners'])==section


@pytest.mark.parametrize('kwargs',[{'rows':30},{'rows':35},{'rows':66},{'missing_column':True}])
def test_incomplete_grid_requires_manual_review(kwargs):
    image,_=grid(**kwargs)
    with pytest.raises(ValueError,match='Automatic table detection'):detect(image)


def test_detects_two_separate_sections():
    morning,_=grid(31,heading=False);afternoon,_=grid(36,heading=False)
    image=Image.new('RGB',(1000,morning.height+afternoon.height),'white')
    image.paste(morning,(0,0));image.paste(afternoon,(0,morning.height))
    specs=detect(image)
    assert [s['section'] for s in specs]==['morning','afternoon']
    assert all(identify_section(image,s['corners'])==s['section'] for s in specs)


def test_real_perspective_photo_needs_no_corner_clicks(data):
    photo=(Path(__file__).parent/'fixtures/morning-2026-10-09.jpg').read_bytes()
    job=make_job(data);add_sources(job,[('real.jpg',photo)])
    preprocess(query('SELECT * FROM sources',one=True))
    source=query('SELECT * FROM sources',one=True)
    assert source['state']=='processing'
    spec=json.loads(source['geometry'])[0]
    assert spec['section']=='morning'
    assert max(p[1] for p in spec['corners'][:2])<270  # Start at count rows, below the heading.
    assert min(p[1] for p in spec['corners'][:2])>240
    for pass_name in ('A','B'):
        times=[t for task in query('SELECT * FROM tasks WHERE pass=?',(pass_name,)) for t in json.loads(task['expected'])]
        assert len(times)==31 and times[0]=='05:15' and times[-1]=='12:45'


@pytest.mark.parametrize('zip_upload',[False,True])
def test_batch_and_zip_detect_each_image_and_keep_invalid_fallback(data,zip_upload):
    job=make_job(data)
    files=[('morning.png',grid()[1]),('nested/afternoon.png',grid(36,True)[1]),
           ('incomplete.png',grid(rows=20)[1]),('corrupt.jpg',b'bad')]
    if zip_upload:
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            for name,raw in files:archive.writestr(name,raw)
        files=[('batch.zip',buffer.getvalue())]
    with TestClient(app) as client:
        response=client.post(f'/api/jobs/{job}/photos',data={'photo_layout':'new-paper'},files=[('photos',(name,raw)) for name,raw in files])
        assert response.status_code==200 and response.json()['added']==4
    for source in query("SELECT * FROM sources WHERE state='pending'"):
        if source['filename']=='incomplete.png':
            with pytest.raises(ValueError):preprocess(source)
        else:preprocess(source)
    sources={s['filename']:s for s in query('SELECT * FROM sources')}
    assert json.loads(sources['morning.png']['geometry'])[0]['section']=='morning'
    assert json.loads(sources['nested/afternoon.png']['geometry'])[0]['section']=='afternoon'
    assert all(json.loads(s['geometry'])[0]['layout']=='new-paper' for s in sources.values() if s['geometry'])
    assert sources['incomplete.png']['geometry'] is None
    assert sources['corrupt.jpg']['state']=='failed'
    # Every ZIP member's normalized image is independently available to the picker.
    with TestClient(app) as client:
        for source in sources.values():
            if source['normalized']:assert client.get('/files/source/'+source['id']).status_code==200


def test_detect_endpoint_and_manual_override(data):
    job=make_job(data);add_sources(job,[('table.png',grid()[1])])
    source=query('SELECT * FROM sources',one=True)
    with TestClient(app) as client:
        response=client.post(f'/api/jobs/{job}/sources/{source["id"]}/detect')
        assert response.status_code==200
        geometry=response.json()['geometry'];geometry[0]['layout']='new-paper'
        response=client.post(f'/api/jobs/{job}/sources/{source["id"]}',json={'geometry':geometry})
        assert response.status_code==200
        response=client.post(f'/api/jobs/{job}/sources/{source["id"]}/detect')
        assert response.status_code==200 and response.json()['geometry'][0]['layout']=='new-paper'
        assert client.post(f'/api/jobs/wrong/sources/{source["id"]}/detect').status_code==400
    preprocess(query('SELECT * FROM sources',one=True))
    assert json.loads(query('SELECT geometry FROM sources',one=True)['geometry'])[0]['layout']=='new-paper'


def test_detection_cannot_overwrite_concurrent_manual_change(data,monkeypatch):
    job=make_job(data);add_sources(job,[('table.png',grid()[1])]);source=query('SELECT * FROM sources',one=True)
    original=detect
    def racing(image):
        geometry=original(image);geometry[0]['layout']='new-paper'
        configure_source(job,source['id'],geometry=geometry)
        return original(image)
    monkeypatch.setattr('app.preprocessing.detect',racing)
    with TestClient(app) as client:
        assert client.post(f'/api/jobs/{job}/sources/{source["id"]}/detect').status_code==400
    assert json.loads(query('SELECT geometry FROM sources',one=True)['geometry'])[0]['layout']=='new-paper'


async def test_old_failed_detection_retries_once_and_preserves_pause(data):
    job=make_job(data);add_sources(job,[('incomplete.png',grid(rows=20)[1])])
    source=query('SELECT * FROM sources',one=True)
    with transaction() as db:
        db.execute("UPDATE sources SET state='needs_review' WHERE id=?",(source['id'],))
        issue(db,job,'old-geometry','geometry',{'error':'Old detector failure'},source['id'])
    control(job,'pause')
    worker=Worker();worker.acquire()
    try:
        assert query('SELECT state FROM jobs',one=True)['state']=='paused'
        assert query('SELECT state FROM sources',one=True)['state']=='pending'
        control(job,'resume');await worker.tick()
        assert query('SELECT state FROM sources',one=True)['state']=='needs_review'
        detail=json.loads(query('SELECT detail FROM issues WHERE resolved=0 AND kind=\'geometry\'',one=True)['detail'])
        assert detail['detector_version']==VERSION
    finally:worker.release()
    worker=Worker();worker.acquire()
    try:assert query('SELECT version,state FROM sources',one=True)=={'version':2,'state':'needs_review'}
    finally:worker.release()


def test_batch_creation_applies_photo_layout_before_automatic_reading(data):
    template=(Path(__file__).parent/'fixtures/Head Counts.xlsx').read_bytes()
    with TestClient(app) as client:
        response=client.post('/jobs',data={'month':'2026-10','mode':'new-month','photo_layout':'monthly'},
                             files=[('template',('template.xlsx',template)),('photos',('table.png',grid(67)[1]))],follow_redirects=False)
        assert response.status_code==303
    source=query('SELECT * FROM sources',one=True)
    assert source['layout_hint']=='monthly'
    preprocess(source)
    assert json.loads(query('SELECT geometry FROM sources',one=True)['geometry'])[0]['layout']=='monthly'


def test_layout_hint_upgrade_keeps_existing_sources(data,photo):
    job=make_job(data);add_sources(job,[('photo.png',photo)])
    source=query('SELECT * FROM sources',one=True)
    with transaction() as db:db.execute('ALTER TABLE sources DROP COLUMN layout_hint')
    migrate();migrate()
    saved=query('SELECT * FROM sources',one=True)
    assert saved['layout_hint']=='auto'
    assert {k:v for k,v in saved.items() if k!='layout_hint'}=={k:v for k,v in source.items() if k!='layout_hint'}
