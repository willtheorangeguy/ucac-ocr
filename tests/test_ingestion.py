import io
import zipfile
import pytest
from app.config import settings
from app.ingestion import add_sources,expand,decode
from app.db import query
from conftest import make_job
from PIL import Image


def mpo_photo():
    primary=Image.new('RGB',(80,60),(210,40,40))
    auxiliary=Image.new('RGB',(20,10),(40,40,210))
    primary.getexif()[274]=6  # The primary photo must still be EXIF-oriented.
    data=io.BytesIO()
    primary.save(data,format='MPO',save_all=True,append_images=[auxiliary],exif=primary.getexif())
    return data.getvalue()


def test_iphone_jpeg_mpo_uses_primary_photo_and_orientation():
    raw=mpo_photo()
    with Image.open(io.BytesIO(raw)) as im:
        assert im.format=='MPO' and im.n_frames==2
    photo=decode(raw)
    assert photo.mode=='RGB' and photo.size==(60,80)
    red,green,blue=photo.getpixel((30,40))
    assert red>180 and green<70 and blue<70


def test_mpo_primary_still_obeys_pixel_limit(monkeypatch):
    monkeypatch.setattr(settings,'max_pixels',3000)
    with pytest.raises(ValueError,match='pixel limit'):decode(mpo_photo())


def test_icloud_zip_skips_video_and_imports_primary_photo(data):
    raw=mpo_photo();archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('iCloud Photos/IMG_1234.JPEG',raw)
        z.writestr('iCloud Photos/IMG_1234.MOV',b'Live Photo clip')
        z.writestr('iCloud Photos/IMG_1234.mov',b'Another clip')
    job=make_job(data)
    assert add_sources(job,[('iCloud Photos.zip',archive.getvalue())])==1
    source=query('SELECT * FROM sources',one=True)
    assert source['state']=='pending' and source['filename']=='iCloud Photos/IMG_1234.JPEG'
    with Image.open(source['normalized']) as normalized:
        assert normalized.format=='PNG' and normalized.size==(60,80)
    assert not query("SELECT * FROM issues WHERE kind='invalid_source'")
    assert add_sources(job,[('iCloud Photos.zip',archive.getvalue())])==0


def test_mov_uploads_are_ignored():
    assert expand([('IMG_1234.MOV',b'Live Photo clip')])==[]


def test_skipped_mov_still_cannot_use_unsafe_zip_path():
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:z.writestr('../IMG_1234.MOV',b'clip')
    with pytest.raises(ValueError,match='Unsafe ZIP path'):expand([('photos.zip',archive.getvalue())])


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
