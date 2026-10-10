import io
import json
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from PIL import Image, ImageOps
from .config import settings
from .db import transaction, issue, bump
from .storage import atomic_write, sha
from .workbook import validate_template

FORMATS={'JPEG','PNG','WEBP'}


def expand(files):
    output=[]; total=0
    for name,data in files:
        if len(data)>settings.max_expanded_bytes: raise ValueError('Upload exceeds size limit')
        if name.lower().endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for entry in z.infolist():
                    p=PurePosixPath(entry.filename.replace('\\','/'))
                    if p.is_absolute() or '..' in p.parts or ':' in entry.filename or (entry.external_attr>>16)&0o170000==0o120000:
                        raise ValueError('Unsafe ZIP path or symlink')
                    if entry.is_dir():continue
                    if entry.file_size>settings.max_file_bytes: raise ValueError('Expanded file exceeds limit')
                    total+=entry.file_size
                    if total>settings.max_expanded_bytes or len(output)>=settings.max_files: raise ValueError('Expanded ZIP limits exceeded')
                    output.append((entry.filename,z.read(entry)))
        else:
            total+=len(data)
            if len(data)>settings.max_file_bytes or total>settings.max_expanded_bytes or len(output)>=settings.max_files: raise ValueError('Batch limits exceeded')
            output.append((name,data))
    return output


def decode(data):
    Image.MAX_IMAGE_PIXELS=settings.max_pixels
    with Image.open(io.BytesIO(data)) as im:
        if im.format not in FORMATS: raise ValueError('Unsupported format; supported: JPEG, PNG, WebP')
        if im.width*im.height>settings.max_pixels: raise ValueError('Decoded image exceeds pixel limit')
        im.load()
        return ImageOps.exif_transpose(im).convert('RGB')


def create_job(year,month,template,mode,files):
    from .layout import dates
    dates(year,month)
    if mode not in ('new-month','continuation'):raise ValueError('Choose new-month or continuation')
    job=uuid.uuid4().hex
    path=settings.data_dir/job/'template.xlsx'
    atomic_write(path,template)
    daily=validate_template(path)
    if mode=='continuation' and any(not x['date'].startswith(f'{year:04}-{month:02}-') for x in daily):
        raise ValueError('Continuation requires daily sheets in selected month')
    now=time.time()
    expanded=expand(files)
    if not expanded:raise ValueError('Select at least one photo or a nonempty ZIP')
    with transaction() as db:
        db.execute('INSERT INTO jobs(id,year,month,mode,template,template_hash,created,updated,state) VALUES(?,?,?,?,?,?,?,?,?)',
                   (job,year,month,mode,str(path),sha(template),now,now,'ingesting'))
        # Existing numbers are protected and reconciled like another observation.
        if mode=='continuation':
            from .layout import key
            for day in daily:
                for tc,value in day['counts'].items():
                    if value is None:continue
                    t,c=tc.split('|')
                    db.execute('INSERT INTO cells(job_id,key,date,time,column_name,value,kind,status,provenance) VALUES(?,?,?,?,?,?,?,?,?)',
                               (job,key(day['date'],t,c),day['date'],t,c,value,'integer','accepted',json.dumps([{'template':sha(template)}])))
    add_sources(job,expanded,expanded=True)
    return job


def add_sources(job,files,expanded=False):
    from .db import query
    if not query('SELECT id FROM jobs WHERE id=?',(job,),True): raise ValueError('Unknown job')
    files=files if expanded else expand(files)
    prepared=[]
    for name,data in files:
        digest=sha(data); sid=uuid.uuid4().hex
        path=settings.data_dir/job/'originals'/digest
        atomic_write(path,data)
        normalized=None; error=None
        try:
            im=decode(data); b=io.BytesIO(); im.save(b,format='PNG')
            normalized=atomic_write(settings.data_dir/job/'images'/f'{sid}.png',b.getvalue())
        except Exception as e: error=str(e)
        prepared.append((sid,digest,name,str(path),normalized,error))
    with transaction() as db:
        state=db.execute('SELECT state FROM jobs WHERE id=?',(job,)).fetchone()['state']
        if state=='cancelled':raise ValueError('Resume cancelled job before adding files')
        added=0
        for sid,digest,name,path,normalized,error in prepared:
            r=db.execute('INSERT OR IGNORE INTO sources(id,job_id,hash,filename,path,normalized,state) VALUES(?,?,?,?,?,?,?)',
                        (sid,job,digest,name,path,normalized,'failed' if error else 'pending'))
            if r.rowcount:
                added+=1
                if error:issue(db,job,'source:'+sid,'invalid_source',{'error':error,'filename':name},sid)
        if added:
            db.execute('UPDATE jobs SET coverage_ack=0 WHERE id=?',(job,)); bump(db,job)
    return added
