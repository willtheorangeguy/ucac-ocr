import io
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from .config import settings
from .layout import MORNING, AFTERNOON
from .storage import atomic_write, sha
from .db import transaction, issue

VERSION='grid-3'


def save_image(path,image):
    b=io.BytesIO(); image.save(b,format='PNG'); return atomic_write(path,b.getvalue())


def line_centers(mask,axis,threshold):
    strength=np.sum(mask>0,axis=axis)
    positions=np.where(strength>threshold)[0]
    groups=[]
    for p in positions:
        if not groups or p>groups[-1][-1]+2:groups.append([int(p)])
        else:groups[-1].append(int(p))
    return [sum(g)/len(g) for g in groups]


def detect(image):
    gray=cv2.cvtColor(np.array(image),cv2.COLOR_RGB2GRAY)
    bw=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,35,15)
    h,w=bw.shape
    horizontal=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((1,max(20,w//4)),np.uint8))
    vertical=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((max(20,h//5),1),np.uint8))
    xs=line_centers(vertical,0,h*.25)
    ys=line_centers(horizontal,1,w*.45)
    if len(xs)!=8:raise ValueError('Grid must expose eight column boundaries; assign table corners manually')
    # Accept only maximal uniform runs of exactly the known schedule lengths.
    runs=[]; current=[]
    for y in ys:
        if len(current)<2 or abs((y-current[-1])-(current[-1]-current[-2]))<max(3,(current[-1]-current[-2])*.12):current.append(y)
        else:
            if len(current)>=3:runs.append(current)
            current=[current[-1],y]
    if len(current)>=3:runs.append(current)
    pages=[]
    for run in runs:
        if len(run) not in (32,37):continue
        section='morning' if len(run)==32 else 'afternoon'
        pages.append(dict(section=section,corners=[[xs[0],run[0]],[xs[-1],run[0]],[xs[-1],run[-1]],[xs[0],run[-1]]]))
    if not pages or len({p['section'] for p in pages})!=len(pages):raise ValueError('Grid row coverage uncertain; assign table corners manually')
    return pages


def rectify(image,corners):
    a=np.asarray(corners,dtype=np.float32)
    if a.shape!=(4,2) or not np.isfinite(a).all():raise ValueError('Four corners required: top-left, top-right, bottom-right, bottom-left')
    w,h=image.size
    if np.any(a[:,0]<0) or np.any(a[:,0]>w) or np.any(a[:,1]<0) or np.any(a[:,1]>h):raise ValueError('Corners outside image')
    if not cv2.isContourConvex(a.astype(np.int32)) or cv2.contourArea(a)<1000:raise ValueError('Invalid table quadrilateral')
    tw=round(max(np.linalg.norm(a[1]-a[0]),np.linalg.norm(a[2]-a[3])))
    th=round(max(np.linalg.norm(a[3]-a[0]),np.linalg.norm(a[2]-a[1])))
    matrix=cv2.getPerspectiveTransform(a,np.float32([[0,0],[tw-1,0],[tw-1,th-1],[0,th-1]]))
    arr=cv2.warpPerspective(np.array(image),matrix,(tw,th))
    return Image.fromarray(arr),matrix.tolist()


def identify_section(image,corners):
    table,_=rectify(image,corners)
    gray=cv2.cvtColor(np.array(table),cv2.COLOR_RGB2GRAY)
    bw=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,35,12)
    horizontal=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((1,max(10,table.width//3)),np.uint8))
    ys=[0]+[y for y in line_centers(horizontal,1,table.width*.55) if y>5 and y<table.height-5]+[table.height-1]
    if len(ys)==32:return 'morning'
    if len(ys)==37:return 'afternoon'
    raise ValueError('The table rows could not be identified. Mark all count rows and exclude the column heading.')


def preprocess(source):
    image=Image.open(source['normalized']).convert('RGB')
    specifications=json.loads(source['geometry']) if source['geometry'] else detect(image)
    if not specifications:raise ValueError('No tables assigned')
    task_specs=[]; page_specs=[]
    directory=settings.data_dir/source['job_id']/'crops'/source['id']/str(source['version'])
    # Optional verification retains independent alternate crops.
    header_bottom=max(1,round(min(c[1] for spec in specifications for c in spec['corners'])))
    header=image.crop((0,0,image.width,header_bottom))
    # Independent alternate framing; neither header crop includes numerical rows.
    for pass_name,im in [('A',header),('B',image.crop((round(image.width*.08),0,image.width,header_bottom)))]:
        if pass_name=='B' and settings.verification=='off':continue
        crop=save_image(directory/f'header-{pass_name}.png',im)
        task_specs.append((pass_name,crop,[],f'header-{pass_name}'))
    for spec in specifications:
        section=spec['section']
        if section not in ('morning','afternoon'):raise ValueError('Section must be morning or afternoon')
        table,transform=rectify(image,spec['corners'])
        gray=cv2.cvtColor(np.array(table),cv2.COLOR_RGB2GRAY)
        bw=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,35,12)
        vertical=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((max(10,table.height//3),1),np.uint8))
        xs=line_centers(vertical,0,table.height*.4)
        # Borders can be lost at warp edges; include them and require internal separators.
        xs=[0]+[x for x in xs if x>8 and x<table.width-8]+[table.width-1]
        if len(xs)!=8:raise ValueError('Column geometry uncertain; corners must include all seven columns')
        expected=MORNING if section=='morning' else AFTERNOON
        horizontal=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((1,max(10,table.width//3)),np.uint8))
        ys=[0]+[y for y in line_centers(horizontal,1,table.width*.55) if y>5 and y<table.height-5]+[table.height-1]
        if len(ys)!=len(expected)+1 or np.std(np.diff(ys))/np.mean(np.diff(ys))>.15:
            raise ValueError('Row geometry uncertain; corners must bound count rows without headers')
        tablepath=save_image(directory/f'{section}.png',table)
        page_specs.append((section,json.dumps(spec),json.dumps(transform),tablepath))
        for pass_name,size in [('A',settings.rows_per_band),('B',max(1,settings.rows_per_band//2))]:
            if pass_name=='B' and settings.verification=='off':continue
            for start in range(0,len(expected),size):
                stop=min(start+size,len(expected))
                # Include printed time and requested numerical columns only.
                crop_im=table.crop((0,max(0,int(ys[start])-2),int(xs[4])+1,min(table.height,int(ys[stop])+2)))
                name=f'{section}-{pass_name}-{start:02}'
                crop=save_image(directory/f'{name}.png',crop_im)
                task_specs.append((pass_name,crop,expected[start:stop],name))
    from .prompts import VERSION as PROMPT_VERSION, SCHEMA_VERSION
    fingerprint=sha(json.dumps({'version':VERSION,'prompt':PROMPT_VERSION,'schema':SCHEMA_VERSION,'rows':settings.rows_per_band,'geometry':specifications,'profile':settings.profile(),'model':settings.ollama_model,'think':settings.think,'rough_counts':settings.rough_counts,'verification':settings.verification},sort_keys=True).encode())
    with transaction() as db:
        for section,geometry,transform,path in page_specs:
            db.execute('INSERT OR IGNORE INTO pages(source_id,version,section,geometry,transform,path) VALUES(?,?,?,?,?,?)',(source['id'],source['version'],section,geometry,transform,path))
        for pass_name,crop,expected,name in task_specs:
            task_key=f"{source['hash']}:{source['version']}:{fingerprint}:{name}"
            db.execute('INSERT OR IGNORE INTO tasks(job_id,source_id,key,version,pass,crop,expected) VALUES(?,?,?,?,?,?,?)',(source['job_id'],source['id'],task_key,source['version'],pass_name,crop,json.dumps(expected)))
        db.execute("UPDATE sources SET state='processing' WHERE id=?",(source['id'],))
