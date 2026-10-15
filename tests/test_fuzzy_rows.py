import io
import json

import cv2
import numpy as np
import pytest
from PIL import Image,ImageDraw

from app.db import issue,query,transaction
from app.ingestion import add_sources
from app.preprocessing import aligned_table,detect,identify_section,preprocess,row_boundaries
from app.services import configure_source
from app.worker import Worker
from conftest import make_job


def fuzzy_table(rows=31,missing=(),jitter=False,curve=0):
    image=Image.new('RGB',(900,rows*24+100),'white');draw=ImageDraw.Draw(image)
    xs=[40,100,240,380,520,660,780,860]
    ys=[40+i*24+(3*(-1)**i if jitter and 0<i<rows else 0) for i in range(rows+1)]
    for x in xs:draw.line((x,ys[0],x,ys[-1]),fill='black',width=2)
    for i,y in enumerate(ys):
        if i not in missing:draw.line((xs[0],y,xs[-1],y),fill='black',width=2)
    if curve:
        yy,xx=np.indices((image.height,image.width),dtype=np.float32)
        # Simulate paper bowing: lines curve vertically by a few pixels.
        image=Image.fromarray(cv2.remap(np.array(image),xx,yy-curve*np.sin(xx/image.width*np.pi),cv2.INTER_LINEAR,borderValue=(255,255,255)))
    corners=[[40,40],[860,40],[860,40+rows*24],[40,40+rows*24]]
    return image,corners,ys


@pytest.mark.parametrize('padding',[12,20,28])
def test_generous_corner_padding_does_not_create_extra_rows(padding):
    image,corners,_=fuzzy_table()
    corners=[[x+dx*padding,y+dy*padding] for (x,y),(dx,dy) in zip(corners,[(-1,-1),(1,-1),(1,1),(-1,1)])]
    assert identify_section(image,corners)=='morning'


@pytest.mark.parametrize('offset',[-22,-12,12,22])
def test_residual_slant_from_imprecise_clicks_is_corrected(offset):
    image,corners,_=fuzzy_table()
    corners[0][1]-=offset;corners[1][1]+=offset
    corners[2][1]+=offset;corners[3][1]-=offset
    assert identify_section(image,corners)=='morning'
    table,_=aligned_table(image,corners)
    ys,_=row_boundaries(table)
    assert len(ys)==32


@pytest.mark.parametrize('rows,section',[(31,'morning'),(36,'afternoon'),(67,'both')])
def test_faint_separators_are_interpolated_without_shifting_times(data,rows,section):
    image,corners,_=fuzzy_table(rows,missing=(8,18),jitter=True,curve=4)
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    job=make_job(data);add_sources(job,[('fuzzy.png',buffer.getvalue())])
    source=query('SELECT * FROM sources',one=True)
    configure_source(job,source['id'],geometry=[dict(section='auto',corners=corners)])
    preprocess(query('SELECT * FROM sources',one=True))
    times=[t for task in query("SELECT expected FROM tasks WHERE pass='A' ORDER BY id") for t in json.loads(task['expected'])]
    assert len(times)==rows and len(set(times))==rows
    assert times[0]==('13:00' if section=='afternoon' else '05:15')
    assert times[-1]==('12:45' if section=='morning' else '21:45')
    geometry=json.loads(query('SELECT geometry FROM pages',one=True)['geometry'])
    assert len(geometry['row_boundaries'])==rows+1


def test_one_missing_separator_still_detects_automatically():
    image,_,_=fuzzy_table(missing=(12,))
    assert detect(image)[0]['section']=='morning'


def test_large_missing_region_still_needs_review():
    image,corners,_=fuzzy_table(missing=tuple(range(8,17)))
    with pytest.raises(ValueError):identify_section(image,corners)


def test_blank_page_never_gets_synthetic_rows():
    image=Image.new('RGB',(900,900),'white')
    with pytest.raises(ValueError):identify_section(image,[[40,40],[860,40],[860,860],[40,860]])


def test_upgrade_retries_saved_corners_without_replacing_them(data):
    image,corners,_=fuzzy_table(missing=(8,18))
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    job=make_job(data);add_sources(job,[('manual.png',buffer.getvalue())])
    source=query('SELECT * FROM sources',one=True)
    geometry=json.dumps([dict(section='morning',corners=corners,layout='legacy')])
    with transaction() as db:
        db.execute("UPDATE sources SET state='needs_review',geometry=? WHERE id=?",(geometry,source['id']))
        issue(db,job,'old-rows','geometry',{'error':'Row geometry uncertain','detector_version':'grid-5'},source['id'])
    worker=Worker();worker.acquire()
    try:
        source=query('SELECT * FROM sources',one=True)
        assert source['state']=='pending' and source['geometry']==geometry
        preprocess(source)
        assert query('SELECT state FROM sources',one=True)['state']=='processing'
        assert not query("SELECT id FROM issues WHERE kind='geometry' AND resolved=0")
    finally:worker.release()
