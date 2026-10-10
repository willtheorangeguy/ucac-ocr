import argparse
import asyncio
import json
import shutil
import sqlite3
import time
from pathlib import Path
from .config import settings
from .db import migrate, connect, query
from .ingestion import create_job, add_sources
from .services import status, control
from .exporting import export_job, recalculate
from .ollama_client import preflight


def folder_files(path):
    if path.is_dir():
        candidates=[p for p in path.rglob('*') if p.is_file()]
        if len(candidates)>settings.max_files:raise ValueError('Folder file-count limit exceeded')
        if sum(p.stat().st_size for p in candidates)>settings.max_expanded_bytes:raise ValueError('Folder size limit exceeded')
        return [(str(p.relative_to(path)),p.read_bytes()) for p in candidates]
    return [(path.name,path.read_bytes())]


def backup(destination):
    destination=Path(destination).resolve(); original=settings.data_dir.resolve()
    if destination==original or original in destination.parents:raise ValueError('Backup destination must be outside data directory')
    destination.mkdir(parents=True,exist_ok=False)
    snapshot=destination/'jobs.sqlite3'
    with connect() as source,sqlite3.connect(snapshot) as target:source.backup(target)
    # Snapshot first, then immutable artifacts; no automatic deletion occurs in the app.
    with sqlite3.connect(snapshot) as db:
        paths=[]
        for table,cols in [('jobs',['template']),('sources',['path','normalized']),('pages',['path']),('tasks',['crop']),('attempts',['raw_path']),('exports',['path'])]:
            for row in db.execute('SELECT '+','.join(cols)+' FROM '+table):paths.extend(p for p in row if p)
        for row in db.execute('SELECT report FROM exports'):
            path=json.loads(row[0]).get('recalculated_path')
            if path:paths.append(path)
        for path in set(paths):
            p=Path(path).resolve()
            if not p.is_relative_to(original):raise ValueError('Backup references external artifact')
            if p.is_file():
                dest=destination/p.relative_to(original);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    (destination/'restore.json').write_text(json.dumps({'original_data_dir':str(original),'created':time.time()}))
    return str(destination)


def main():
    parser=argparse.ArgumentParser(description='Durable pool headcount importer')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('migrate');sub.add_parser('worker-health');sub.add_parser('diagnostics')
    p=sub.add_parser('import-month');p.add_argument('--month',required=True);p.add_argument('--template',type=Path,required=True);p.add_argument('--photos',type=Path,required=True);p.add_argument('--mode',choices=['new-month','continuation'],default='new-month')
    for action in ['status','resume','pause','cancel','retry','coverage','refresh','export']:
        p=sub.add_parser(action);p.add_argument('job')
    p=sub.add_parser('add');p.add_argument('job');p.add_argument('photos',type=Path)
    p=sub.add_parser('backup');p.add_argument('destination',type=Path)
    p=sub.add_parser('recalculate');p.add_argument('export_id',type=int)
    args=parser.parse_args()
    if args.command=='worker-health':
        owner=query('SELECT heartbeat FROM worker_owner WHERE singleton=1',one=True)
        raise SystemExit(0 if owner and time.time()-owner['heartbeat']<max(60,settings.heartbeat_interval*4) else 1)
    migrate()
    if args.command=='migrate':return
    if args.command=='diagnostics':result=asyncio.run(preflight())
    elif args.command=='import-month':
        year,month=map(int,args.month.split('-'));result={'job':create_job(year,month,args.template.read_bytes(),args.mode,folder_files(args.photos))}
    elif args.command=='status':result=status(args.job)
    elif args.command=='export':result=export_job(args.job)
    elif args.command=='add':result={'added':add_sources(args.job,folder_files(args.photos))}
    elif args.command=='backup':result={'backup':backup(args.destination)}
    elif args.command=='recalculate':result={'path':str(recalculate(args.export_id))}
    else:control(args.job,args.command);result={'ok':True}
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
