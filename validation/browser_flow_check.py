"""Browser checks against mocked job APIs; never changes operator counts."""
import copy
import json
import re
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

HOST='http://localhost:8000'
with urllib.request.urlopen(HOST+'/') as response:home=response.read().decode()
JOB=re.search(r'href="/jobs/([a-f0-9]+)"',home).group(1)
with urllib.request.urlopen(HOST+'/api/jobs/'+JOB) as response:original=json.load(response)
out=Path(__file__).parent/'screenshots';out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1100,'height':850})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(HOST)
    assert page.locator('section.step').count()==4
    assert page.locator('.step-number').all_text_contents()==['1','2','3','4']
    page.screenshot(path=str(out/'numbered-main-page.png'),full_page=True)
    page.goto(HOST+'/jobs/'+JOB)
    page.wait_for_selector('.download')
    assert page.locator('section.step').count()==4
    assert page.locator('#exports a').count()==1
    assert page.locator('dialog, details').count()==0
    assert page.get_by_text('Attempts and evidence').count()==0
    page.wait_for_function("[...document.images].every(im=>im.complete&&im.naturalWidth>0)")
    page.screenshot(path=str(out/'simple-report.png'),full_page=True)
    with page.expect_download() as info:page.locator('.download').click()
    assert info.value.suggested_filename==f"{original['year']}-{original['month']:02}-headcounts.xlsx"

    state=copy.deepcopy(original);source=state['sources'][0];sid=source['id']
    state.update(tasks=[],cells=[],exports=[],issues=[{'id':999,'source_id':sid,'kind':'geometry','cell_key':None,'detail':'{}'}])
    source.update(geometry=None,state='needs_review',normalized='mock.png')
    state['sources']=[source];calls=[]
    def route_api(route):
        request=route.request
        if request.method=='POST':
            calls.append((request.url,request.post_data_json))
            if '/sources/' in request.url:
                source.update(geometry=json.dumps(request.post_data_json['geometry']),state='processing')
                state['issues']=[]
            elif '/review/' in request.url:
                issue_id=int(request.url.rsplit('/',1)[-1]);state['issues']=[i for i in state['issues'] if i['id']!=issue_id]
            route.fulfill(json={'ok':True})
        else:route.fulfill(json=state)
    page.route('**/api/jobs/**',route_api)
    from PIL import Image
    import io
    image_bytes=io.BytesIO();Image.open(Path(__file__).parent.parent/'tests/fixtures/morning-2026-10-09.jpg').save(image_bytes,format='PNG')
    page.route('**/files/source/*',lambda route:route.fulfill(body=image_bytes.getvalue(),content_type='image/png'))
    page.reload();page.wait_for_function("document.getElementById('corner-canvas').width===1080")
    page.screenshot(path=str(out/'simple-report-corners.png'),full_page=True)
    canvas=page.locator('#corner-canvas');box=canvas.bounding_box()
    for x,y in [[154,262],[918,252],[968,1185],[138,1200]]:
        canvas.click(position={'x':x*box['width']/1080,'y':y*box['height']/1440})
    page.wait_for_function("document.getElementById('corner-editor').hidden")
    assert len(calls)==1 and calls[0][1]['geometry'][0]['section']=='auto'
    corners=calls[0][1]['geometry'][0]['corners']
    assert all(abs(a-b)<2 for actual,expected in zip(corners,[[154,262],[918,252],[968,1185],[138,1200]]) for a,b in zip(actual,expected))

    source['state']='succeeded';state['revision']+=1
    state['exports']=original['exports'][:2]
    state['issues']=[];state['cells']=[]
    for i,column in enumerate(['public','group','dry'],1000):
        key=f'2026-10-09|12:00|{column}'
        state['issues'].append({'id':i,'source_id':sid,'kind':'cell','cell_key':key,'detail':'{}'})
        state['cells'].append({'key':key,'date':'2026-10-09','time':'12:00','column_name':column,'value':None,'provenance':'[]'})
    page.reload();page.wait_for_selector('.fix-image')
    assert page.locator('.fix-image').count()==1
    page.locator('#value-1000').fill('7');page.locator('#value-1001').fill('0');page.locator('#blank-1002').check()
    page.get_by_role('button',name='Save corrections').click()
    page.wait_for_function("document.querySelectorAll('.fix-image').length===0")
    assert len(calls)==4
    assert calls[-1][1]['action']=='blank'
    assert page.locator('#exports a').count()==1
    page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(out/'simple-report-mobile.png'),full_page=True)
    assert not errors,errors
    browser.close()
print('Browser flow passed: four clicks, automatic save, grouped fixes, blank/zero, latest download, mobile; no page errors.')
