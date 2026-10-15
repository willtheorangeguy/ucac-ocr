"""Check real normalized photos locally, without OCR or operator DB writes.

Pass a folder containing PNGs and sources.json downloaded from the local job API.
Only a summary is written to the repository; all generated tasks/crops are temporary.
"""
import json
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.config import settings
from app.db import migrate,query
from app.ingestion import create_job
from app.preprocessing import VERSION,preprocess


folder=Path(sys.argv[1]);started=time.monotonic();results=[]
originals={Path(s['filename']).stem:s for s in json.loads((folder/'sources.json').read_text())}
with tempfile.TemporaryDirectory(prefix='pool-fuzzy-validation-') as directory:
    settings.data_dir=Path(directory);settings.verification='off';settings.rows_per_band=12
    migrate()
    job=create_job(2026,10,(ROOT/'app/assets/monthly-template.xlsx').read_bytes(),'new-month',
                   [(p.name,p.read_bytes()) for p in sorted(folder.glob('*.png'))])
    for source in query('SELECT * FROM sources ORDER BY filename'):
        result={'filename':source['filename'],'previously_blocked':originals[Path(source['filename']).stem]['geometry'] is None}
        try:
            preprocess(source)
            page=query('SELECT * FROM pages WHERE source_id=?',(source['id'],),True)
            geometry=json.loads(page['geometry'])
            tasks=query("SELECT expected FROM tasks WHERE source_id=? AND pass='A' ORDER BY id",(source['id'],))
            times=[t for task in tasks for t in json.loads(task['expected'])]
            result.update(section=page['section'],rows=len(times),first_time=times[0],last_time=times[-1],
                          boundaries=len(geometry['row_boundaries']),status='passed')
            assert len(times)==(31 if page['section']=='morning' else 36)
            assert len(set(times))==len(times)
        except Exception as error:result.update(status='failed',error=str(error))
        results.append(result);print(json.dumps(result),flush=True)
report={'version':VERSION,'photos':len(results),'passed':sum(r['status']=='passed' for r in results),
        'seconds':round(time.monotonic()-started,2),'ocr_requests':0,'results':results}
(ROOT/'validation/fuzzy-rows-photos.json').write_text(json.dumps(report,indent=2))
if report['passed']!=report['photos']:raise SystemExit(1)
