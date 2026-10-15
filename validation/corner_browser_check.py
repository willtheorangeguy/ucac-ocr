"""Exercise the actual corner-picker JS at desktop/mobile sizes using local mocks.

Run with the app's Python environment and websocket-client, with a local Chromium
binary passed as the first argument. No operator database or OCR server is used.
"""
import copy
import io
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
import websocket

ROOT=Path(__file__).resolve().parents[1]
SOURCE=dict(id='photo',filename='morning.jpg',normalized='photo.png',state='pending',geometry=None,version=1)
INITIAL=dict(id='browsercheck',year=2026,month=10,revision=1,state='queued',diagnostic=None,
             tasks=[],sources=[SOURCE],cells=[],exports=[],issues=[dict(id=1,source_id='photo',kind='geometry')])
state=copy.deepcopy(INITIAL);calls=[];paths=[];reject=[False];delays={}
small=io.BytesIO()
with Image.open(ROOT/'tests/fixtures/morning-2026-10-09.jpg') as photo:photo.resize((540,720)).save(small,format='PNG')
html=Environment(loader=FileSystemLoader(ROOT/'app/templates'),autoescape=select_autoescape()).get_template('job.html').render(job=INITIAL)


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass

    def send(self,data,kind='application/json',status=200):
        self.send_response(status);self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith('/api/jobs/'):self.send(json.dumps(state).encode())
        elif self.path.startswith('/files/source/'):
            sid=self.path.rsplit('/',1)[-1]
            time.sleep(delays.get(sid,0))
            self.send(small.getvalue() if sid=='slow' else (ROOT/'tests/fixtures/morning-2026-10-09.jpg').read_bytes(),'image/png' if sid=='slow' else 'image/jpeg')
        elif self.path.startswith('/static/'):
            path=ROOT/'app'/self.path.split('?',1)[0].lstrip('/')
            self.send(path.read_bytes(),'text/javascript' if path.suffix=='.js' else 'text/css')
        else:self.send(html.encode(),'text/html')

    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        calls.append(body)
        paths.append(self.path)
        if reject[0]:
            reject[0]=False;self.send(b'{"error":"Test rejection"}',status=400);return
        sid=self.path.rsplit('/',1)[-1]
        source=next(s for s in state['sources'] if s['id']==sid)
        source.update(geometry=json.dumps(body['geometry']),state='processing')
        state['issues']=[i for i in state['issues'] if i['source_id']!=sid]
        self.send(b'{"ok":true}')


server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
with socket.socket() as port_socket:
    port_socket.bind(('127.0.0.1',0));port=port_socket.getsockname()[1]
corners=[[154,262],[918,252],[968,1185],[138,1200]]
with tempfile.TemporaryDirectory(prefix='pool-corner-browser-') as profile:
    process=subprocess.Popen([sys.argv[1],'--headless','--no-first-run','--disable-extensions',
        '--remote-allow-origins=*',f'--remote-debugging-port={port}',f'--user-data-dir={profile}','about:blank'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        for _ in range(100):
            try:
                req=urllib.request.Request(f'http://127.0.0.1:{port}/json/new?about:blank',method='PUT')
                with urllib.request.urlopen(req) as response:target=json.load(response)
                break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Chromium did not start')
        ws=websocket.create_connection(target['webSocketDebuggerUrl'],timeout=15)
        serial=0

        def cdp(method,params=None):
            global serial
            serial+=1;seq=serial;ws.send(json.dumps(dict(id=seq,method=method,params=params or {})))
            while True:
                result=json.loads(ws.recv())
                if result.get('id')==seq:
                    if 'error' in result:raise AssertionError(result['error'])
                    return result.get('result',{})

        def js(expression):
            result=cdp('Runtime.evaluate',dict(expression=expression,returnByValue=True,awaitPromise=True))
            if 'exceptionDetails' in result:raise AssertionError(result['exceptionDetails'])
            return result.get('result',{}).get('value')

        def until(expression):
            for _ in range(150):
                if js(expression):return
                time.sleep(.05)
            raise AssertionError(expression)

        def click_corner(point):
            x,y=point
            js(f"(()=>{{const c=document.getElementById('corner-canvas'),r=c.getBoundingClientRect();c.dispatchEvent(new MouseEvent('click',{{clientX:r.left+{x}*r.width/1080,clientY:r.top+{y}*r.height/1440,bubbles:true}}))}})()")

        cdp('Page.enable');cdp('Runtime.enable')
        for width in [1100,390]:
            state=copy.deepcopy(INITIAL);calls.clear()
            cdp('Emulation.setDeviceMetricsOverride',dict(width=width,height=900,deviceScaleFactor=1,mobile=False))
            cdp('Page.navigate',dict(url=f'http://127.0.0.1:{server.server_port}/jobs/browsercheck'))
            until("document.getElementById('corner-canvas')?.width===1080")
            tolerance=js("1080/document.getElementById('corner-canvas').getBoundingClientRect().width")+.01
            js("document.getElementById('corner-layout').value='legacy'")
            for point in corners[:2]:click_corner(point)
            state['sources'][0]['state']='processing';state['issues']=[]
            # A real polling cycle must not hide or reset partially selected corners.
            time.sleep(5.3)
            assert js("!document.getElementById('corner-editor').hidden && document.getElementById('corner-status').textContent.startsWith('2 of 4')")
            reject[0]=True
            for point in corners[2:]:click_corner(point)
            until("document.getElementById('corner-status').textContent.includes('Test rejection')")
            js("document.getElementById('clear-corners').click()")
            for point in corners:click_corner(point)
            until("document.getElementById('corner-editor').hidden")
            assert len(calls)==2
            geometry=calls[-1]['geometry'][0]
            assert geometry['section']=='auto' and geometry['layout']=='legacy'
            # MouseEvent coordinates have CSS-pixel precision; the source photo
            # is larger than the canvas at both viewport sizes.
            assert all(abs(a-b)<tolerance for actual,expected in zip(geometry['corners'],corners) for a,b in zip(actual,expected)),geometry['corners']
            assert js("document.querySelectorAll('canvas').length===1")
            print(f'{width}px: scaled corner coordinates, stable polling, error/reset/retry, and four-click save passed')

            # Simulate three extracted ZIP members with independent worker states.
            state=copy.deepcopy(INITIAL);calls.clear();paths.clear()
            state['sources'] += [dict(SOURCE,id='second',filename='nested/second.jpg'),dict(SOURCE,id='third',filename='nested/third.jpg')]
            state['issues'] += [dict(id=2,source_id='second',kind='geometry'),dict(id=3,source_id='third',kind='geometry')]
            cdp('Page.navigate',dict(url=f'http://127.0.0.1:{server.server_port}/jobs/browsercheck'))
            until("document.getElementById('corner-canvas')?.width===1080")
            js("document.getElementById('corner-photo').value='second';document.getElementById('corner-photo').dispatchEvent(new Event('change'))")
            until("document.getElementById('corner-status').textContent.startsWith('0 of 4')")
            for point in corners[:2]:click_corner(point)
            state['sources'][0].update(geometry=json.dumps([dict(section='morning',corners=corners,layout='legacy')]),state='processing')
            state['issues']=[i for i in state['issues'] if i['source_id']!='photo']
            time.sleep(5.3)
            assert js("document.getElementById('corner-photo').value==='second' && document.getElementById('corner-status').textContent.startsWith('2 of 4')")
            for point in corners[2:]:click_corner(point)
            until("document.getElementById('corner-photo').value==='third'")
            assert paths[-1].endswith('/sources/second')
            until("document.getElementById('corner-status').textContent.startsWith('0 of 4')")
            for point in corners:click_corner(point)
            until("document.getElementById('corner-editor').hidden")
            assert paths[-1].endswith('/sources/third')
            js("document.getElementById('review-boxes').click()")
            until("document.getElementById('corner-status').textContent.includes('Table box saved')")
            assert js("document.getElementById('corner-photo').options.length===3")
            assert js("(()=>{const p=document.getElementById('corner-canvas').getContext('2d').getImageData(152,260,5,5).data;for(let i=0;i<p.length;i+=4)if(p[i]>200&&p[i+1]<100&&p[i+2]<100)return true;return false})()")
            # A late response for a previous image must never replace the selection.
            state['sources'].append(dict(SOURCE,id='slow',filename='slow.png'));delays['slow']=.5
            time.sleep(5.3)
            js("document.getElementById('corner-photo').value='slow';document.getElementById('corner-photo').dispatchEvent(new Event('change'));document.getElementById('corner-photo').value='photo';document.getElementById('corner-photo').dispatchEvent(new Event('change'))")
            time.sleep(.8)
            assert js("document.getElementById('corner-photo').value==='photo' && document.getElementById('corner-canvas').width===1080")
            print(f'{width}px: ZIP-member switching, polling stability, source-specific saves, saved outlines, and image-load race passed')
        ws.close()
    finally:
        process.terminate();process.wait(timeout=15)
        server.shutdown();server.server_close()
