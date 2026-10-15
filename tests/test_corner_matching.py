import io
import json
from pathlib import Path
import pytest
from PIL import Image, ImageDraw
from app.db import query
from app.ingestion import add_sources
from app.preprocessing import identify_section, preprocess, rectify
from app.services import configure_source
from conftest import make_job


@pytest.mark.parametrize('padding',[-8,-3,0,3,8])
def test_real_photo_accepts_small_corner_imprecision(data,padding):
    image=Image.open(Path(__file__).parent/'fixtures/morning-2026-10-09.jpg').convert('RGB')
    corners=[[154-padding,262-padding],[918+padding,252-padding],[968+padding,1185+padding],[138-padding,1200+padding]]
    assert identify_section(image,corners)=='morning'
    b=io.BytesIO();image.save(b,format='PNG');job=make_job(data)
    add_sources(job,[('real.png',b.getvalue())]);source=query('SELECT * FROM sources',one=True)
    configure_source(job,source['id'],geometry=[dict(section='auto',layout='legacy',corners=corners)])
    preprocess(query('SELECT * FROM sources',one=True))
    tasks=query('SELECT * FROM tasks WHERE expected!=\'[]\' AND pass=\'A\' ORDER BY id')
    assert sum(len(json.loads(task['expected'])) for task in tasks)==31


@pytest.mark.parametrize('corners',[
    [[0,0],[200,200],[200,0],[0,200]],
    [[0,0],[2,0],[2,2],[0,2]],
    [[-1,0],[200,0],[200,200],[0,200]],
])
def test_invalid_corner_selection_is_rejected(corners):
    with pytest.raises(ValueError):rectify(Image.new('RGB',(300,300),'white'),corners)


@pytest.mark.parametrize('layout,section,rows,pitch',[
    ('legacy','morning',31,24),('new-paper','morning',31,24),('monthly','both',67,18),
])
def test_canonical_crops_keep_external_internal_and_dry_distinct(data,monkeypatch,layout,section,rows,pitch):
    from app.config import settings
    monkeypatch.setattr(settings,'verification','off')
    image=Image.new('RGB',(800,rows*pitch+110),'white');draw=ImageDraw.Draw(image)
    for i in range(8):draw.line((40+i*100,60,40+i*100,60+rows*pitch),fill='black',width=2)
    for i in range(rows+1):draw.line((40,60+i*pitch,740,60+i*pitch),fill='black',width=2)
    indexes={'legacy':[1,None,2,3],'new-paper':[1,2,3,4],'monthly':[2,3,4,5]}[layout]
    colors=[(220,40,40),(40,180,40),(40,40,220),(220,180,40)]
    for col,color in zip(indexes,colors):
        if col is not None:
            x=40+col*100+50;y=60+pitch//2
            draw.rectangle((x-12,y-4,x+12,y+4),fill=color)
    b=io.BytesIO();image.save(b,format='PNG');job=make_job(data)
    add_sources(job,[('grid.png',b.getvalue())]);source=query('SELECT * FROM sources',one=True)
    corners=[[40,60],[740,60],[740,60+rows*pitch],[40,60+rows*pitch]]
    assert identify_section(image,corners)==section
    configure_source(job,source['id'],'2026-10-09',[dict(section='auto',layout=layout,corners=corners)])
    preprocess(query('SELECT * FROM sources',one=True))
    tasks=query('SELECT * FROM tasks WHERE expected!=\'[]\' ORDER BY id')
    times=[t for task in tasks for t in json.loads(task['expected'])]
    assert len(times)==rows and times[0]=='05:15'
    assert times[-1]==('21:45' if section=='both' else '12:45')
    crop=Image.open(tasks[0]['crop'])
    for i,color in enumerate(colors,1):
        actual=crop.getpixel((round((i+.5)*crop.width/5),22+pitch//2))
        assert actual==((255,255,255) if layout=='legacy' and i==2 else color)
