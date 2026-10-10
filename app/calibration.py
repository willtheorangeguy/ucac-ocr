"""Small, explicitly manual truth benchmark. Never claims whole-sheet accuracy."""
import argparse
import asyncio
import json
from pathlib import Path
from .config import settings
from .db import migrate, query
from .ingestion import create_job
from .services import configure_source
from .preprocessing import preprocess, save_image
from .ollama_client import preflight, extract
from .storage import atomic_write
from PIL import Image


async def run(output):
    output.mkdir(parents=True,exist_ok=True)
    info=await preflight()
    fixture=Path(__file__).parent.parent/'tests/fixtures'
    photo=fixture/'morning-2026-10-09.jpg'
    migrate()
    job=create_job(2026,10,(fixture/'Head Counts.xlsx').read_bytes(),'new-month',[(photo.name,photo.read_bytes())])
    source=query('SELECT * FROM sources WHERE job_id=?',(job,),True)
    configure_source(job,source['id'],'2026-10-09',[{'section':'morning','corners':[[154,262],[918,252],[968,1185],[138,1200]]}])
    preprocess(query('SELECT * FROM sources WHERE id=?',(source['id'],),True))
    page=query('SELECT * FROM pages WHERE source_id=?',(source['id'],),True)
    table=Image.open(page['path'])
    # Verified boundaries from saved transform: requested columns end at x=494.
    a=save_image(output/'A.png',table.crop((0,0,495,31)))
    b=save_image(output/'B.png',table.crop((0,0,495,62)))
    tasks=query('SELECT * FROM tasks WHERE source_id=?',(source['id'],))
    calls=[('header-A',next(t['crop'] for t in tasks if t['pass']=='A' and t['expected']=='[]'),[]),
           ('header-B',next(t['crop'] for t in tasks if t['pass']=='B' and t['expected']=='[]'),[]),
           ('A',a,['05:15']),('B',b,['05:15','05:30'])]
    from .prompts import VERSION as PROMPT_VERSION, SCHEMA_VERSION
    report={'scope':'Only date and first row, four sequential requests; not a whole-sheet benchmark','prompt_version':PROMPT_VERSION,'schema_version':SCHEMA_VERSION,'server':info,'options':settings.profile(),'think':settings.think,'job':job,'results':{}}
    from .worker import Worker
    # Same global lock/owner record as production; no other local worker can infer.
    worker=Worker();worker.acquire()
    try:
        for name,path,expected in calls:
            print('Starting',name,flush=True)
            try:
                r,metrics=await extract(path,expected,output/f'{name}.ndjson')
                report['results'][name]={'result':r.model_dump(),'metrics':metrics}
                atomic_write(output/f'{name}.json',r.model_dump_json().encode())
                print('Finished',name,flush=True)
            except Exception as e:report['results'][name]={'error':str(e)};print('Failed',name,str(e),flush=True)
            atomic_write(output/'report.json',json.dumps(report,indent=2).encode())
        expected_values={'public':0,'group':32,'dry':2}
        checks={}
        for name in ('A','B'):
            r=report['results'][name].get('result')
            if r:
                from .schemas import Extraction
                row=Extraction.model_validate(r).rows[0]
                checks[name]={c:getattr(row,c).value==v for c,v in expected_values.items()}
        report['manually_checked_first_row']={'truth':expected_values,'checks':checks}
        report['date_checks']={n:report['results'][n].get('result',{}).get('date')=='2026-10-09' for n in ('header-A','header-B')}
        atomic_write(output/'report.json',json.dumps(report,indent=2).encode())
    finally:worker.release()
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('calibration-output'));args=p.parse_args()
    asyncio.run(run(args.output))
