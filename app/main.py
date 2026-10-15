import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .config import settings
from .db import migrate, query
from .ingestion import create_job, add_sources
from .services import status, control, configure_source, reprocess, edit_cell
from .reconciliation import decide
from .exporting import export_job, recalculate
from .ollama_client import preflight

ROOT=Path(__file__).parent


@asynccontextmanager
async def lifespan(app):
    migrate(); yield


app=FastAPI(title='Pool Headcount',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
templates=Jinja2Templates(directory=ROOT/'templates')


@app.middleware('http')
async def same_origin(request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin and urlsplit(origin).netloc!=request.headers.get('host'):
            return JSONResponse({'error':'Cross-origin write rejected'},status_code=403)
    return await call_next(request)


@app.exception_handler(ValueError)
async def invalid(request,e):return JSONResponse({'error':str(e)},status_code=400)


@app.get('/health')
def health_route():
    query('SELECT version FROM schema_version')
    return {'web':'ok'}


@app.get('/')
def home(request:Request):
    return templates.TemplateResponse(request=request,name='index.html',context={'jobs':query('SELECT * FROM jobs ORDER BY created DESC')})


@app.get('/jobs/{job}')
def job_page(request:Request,job:str):
    return templates.TemplateResponse(request=request,name='job.html',context={'job':status(job)})


@app.get('/settings')
def settings_page(request:Request):
    return templates.TemplateResponse(request=request,name='settings.html',context={'settings':settings})


@app.get('/api/settings/diagnostics')
async def diagnostics():
    try:return {'ok':True,**await preflight()}
    except Exception as e:return {'ok':False,'diagnostic':str(e)}


async def uploaded(files):
    result=[]; total=0
    if len(files)>settings.max_files:raise ValueError('Too many uploaded files')
    for f in files:
        data=await f.read(settings.max_expanded_bytes+1 if f.filename.lower().endswith('.zip') else settings.max_file_bytes+1)
        await f.close(); total+=len(data)
        if total>settings.max_expanded_bytes:raise ValueError('Upload size limit exceeded')
        result.append((f.filename,data))
    return result


@app.post('/jobs')
async def new_job(month:str=Form(...),mode:str=Form(...),template:UploadFile=File(...),photos:list[UploadFile]=File(...),photo_layout:str=Form('auto')):
    year,mo=map(int,month.split('-'))
    data=await template.read(settings.max_file_bytes+1); await template.close()
    if len(data)>settings.max_file_bytes:raise ValueError('Template too large')
    job=await asyncio.to_thread(create_job,year,mo,data,mode,await uploaded(photos),photo_layout)
    return RedirectResponse(f'/jobs/{job}',status_code=303)


@app.get('/api/jobs/{job}')
def job_status(job:str):return status(job)


@app.post('/api/jobs/{job}/photos')
async def more_photos(job:str,photos:list[UploadFile]=File(...),photo_layout:str=Form('auto')):
    return {'added':await asyncio.to_thread(add_sources,job,await uploaded(photos),photo_layout=photo_layout)}


@app.post('/api/jobs/{job}/control/{action}')
def job_control(job:str,action:str):control(job,action);return {'ok':True}


@app.post('/api/jobs/{job}/export')
async def job_export(job:str):return await asyncio.to_thread(export_job,job)


@app.post('/api/jobs/{job}/sources/{sid}')
async def source_config(job:str,sid:str,request:Request):
    data=await request.json()
    configure_source(job,sid,data.get('date'),data.get('geometry'),data.get('reviewer','operator'),data.get('confirm',False))
    return {'ok':True}


@app.post('/api/jobs/{job}/sources/{sid}/reprocess')
def source_reprocess(job:str,sid:str):reprocess(job,sid);return {'ok':True}


@app.post('/api/jobs/{job}/sources/{sid}/detect')
def source_detect(job:str,sid:str):
    from PIL import Image
    from .preprocessing import detect
    source=query('SELECT * FROM sources WHERE id=? AND job_id=?',(sid,job),True)
    if not source or not source['normalized']:raise ValueError('No readable image for this source')
    with Image.open(source['normalized']) as image:geometry=detect(image.convert('RGB'))
    saved={spec['section']:spec.get('layout','auto') for spec in json.loads(source['geometry'] or '[]')}
    for spec in geometry:spec['layout']=saved.get(spec['section'],source['layout_hint'])
    configure_source(job,sid,geometry=geometry,reviewer='automatic detection',expected_version=source['version'])
    return {'geometry':geometry}


@app.post('/api/jobs/{job}/review/{issue_id}')
async def review(job:str,issue_id:int,request:Request):
    d=await request.json(); decide(job,issue_id,d['action'],d.get('value'),d.get('note',''),d.get('reviewer',''))
    return {'ok':True}


@app.post('/api/jobs/{job}/cells')
async def cell_edit(job:str,request:Request):
    d=await request.json(); edit_cell(job,d['key'],d['action'],d.get('value'),d.get('note',''),d.get('reviewer',''))
    return {'ok':True}


@app.get('/files/source/{sid}')
def source_file(sid:str,original:bool=False):
    source=query('SELECT * FROM sources WHERE id=?',(sid,),True)
    if not source:raise HTTPException(404)
    path=source['path'] if original else source['normalized']
    if not path:raise HTTPException(404)
    return FileResponse(path,filename=Path(source['filename']).name if original else None,media_type=None if original else 'image/png')


@app.get('/files/crop/{task_id}')
def crop_file(task_id:int):
    task=query('SELECT crop FROM tasks WHERE id=?',(task_id,),True)
    if not task:raise HTTPException(404)
    return FileResponse(task['crop'],media_type='image/png')


@app.get('/files/attempt/{attempt_id}')
def attempt_file(attempt_id:int):
    a=query('SELECT raw_path FROM attempts WHERE id=?',(attempt_id,),True)
    if not a or not Path(a['raw_path']).is_file():raise HTTPException(404)
    return FileResponse(a['raw_path'],filename=f'attempt-{attempt_id}.ndjson')


@app.get('/files/export/{export_id}')
def export_file(export_id:int,recalculated:bool=False):
    e=query('SELECT * FROM exports WHERE id=?',(export_id,),True)
    if not e:raise HTTPException(404)
    path=json.loads(e['report']).get('recalculated_path') if recalculated else e['path']
    if not path:raise HTTPException(404)
    job=query('SELECT year,month FROM jobs WHERE id=?',(e['job_id'],),True)
    return FileResponse(path,filename=f"{job['year']}-{job['month']:02}-headcounts.xlsx")


@app.post('/api/exports/{export_id}/recalculate')
async def recalc(export_id:int):return {'path':str(await asyncio.to_thread(recalculate,export_id))}
