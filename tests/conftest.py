import io
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pytest
from PIL import Image
from app.config import settings
from app.db import migrate, transaction


@pytest.fixture(autouse=True)
def original_strict_profile(monkeypatch):
    # Historical strict-mode tests remain useful; fast-mode tests override these.
    for name,value in dict(rough_counts=False,verification='always',think=True,num_ctx=16384,num_predict=8192,rows_per_band=6).items():
        monkeypatch.setattr(settings,name,value)


@pytest.fixture
def data(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'data_dir',tmp_path/'data')
    monkeypatch.setattr(settings,'retry_delays','0.01,0.02,0.03,0.04,0.05')
    monkeypatch.setattr(settings,'disconnect_cooldown',.01)
    migrate()
    return settings.data_dir


@pytest.fixture
def photo():
    b=io.BytesIO(); Image.new('RGB',(100,100),'white').save(b,format='PNG');return b.getvalue()


def make_job(data,job=None):
    from app.storage import sha, atomic_write
    job=job or uuid.uuid4().hex
    template=Path(__file__).parent/'fixtures/Head Counts.xlsx'
    path=data/job/'template.xlsx';atomic_write(path,template.read_bytes())
    with transaction() as db:
        db.execute('INSERT INTO jobs(id,year,month,mode,template,template_hash,created,updated) VALUES(?,?,?,?,?,?,?,?)',(job,2026,10,'new-month',str(path),sha(path.read_bytes()),time.time(),time.time()))
    return job


def reading(value=0):
    return {'raw_text':str(value),'kind':'integer','terms':[value],'ambiguous':False,'reason':None}


def result(times,day='2026-10-09'):
    return dict(date=day,section='morning' if not times or times[0]<'13:00' else 'afternoon',ambiguous=False,reason=None,
                rows=[dict(time=t,public=reading(),group=reading(32),dry=reading(2)) for t in times])


class MockState:
    def __init__(self):
        self.mode='good';self.delay=0;self.requests=[];self.active=0;self.max_active=0;self.started=threading.Event()


@pytest.fixture
def ollama(monkeypatch):
    state=MockState()
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*a):pass
        def send_json(self,status,obj):
            b=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        def do_GET(self):
            self.send_json(200,{'version':'0.35.0'} if self.path=='/api/version' else {'models':[{'name':settings.ollama_model,'digest':'mock'}]})
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/show':self.send_json(200,{'capabilities':['vision','thinking']});return
            state.requests.append(body);state.active+=1;state.max_active=max(state.max_active,state.active);state.started.set()
            try:
                if state.mode in ('503','400','oom'):
                    self.send_json(503 if state.mode=='503' else (500 if state.mode=='oom' else 400),{'error':'out of memory' if state.mode=='oom' else state.mode});return
                prompt=body['messages'][1]['content']
                times=json.loads(prompt.split('Expected visible times in exact order: ')[1].split('. Check')[0]) if 'Expected visible' in prompt else []
                text=json.dumps(result(times)) if state.mode!='malformed' else '{"broken":1}'
                if state.mode=='disconnect':text=text[:20]
                chunks=[{'message':{'thinking':'audit thought','content':text[:len(text)//2]},'done':False},
                        {'message':{'content':text[len(text)//2:]},'done':False}]
                if state.mode!='disconnect':chunks.append({'message':{'content':''},'done':True,'done_reason':'length' if state.mode=='truncated' else 'stop','eval_count':20})
                if state.mode=='invalid_message':chunks[0]['message']['content']=7
                self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.send_header('Connection','close');self.end_headers()
                time.sleep(state.delay)
                for chunk in chunks:
                    self.wfile.write((json.dumps(chunk)+'\n').encode());self.wfile.flush()
                    if state.mode=='gaps':time.sleep(state.delay)
                self.close_connection=True
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
            finally:state.active-=1
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setattr(settings,'ollama_base_url',f'http://127.0.0.1:{server.server_port}')
    yield state
    server.shutdown();server.server_close();thread.join()
