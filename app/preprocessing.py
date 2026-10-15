import io
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from .config import settings
from .layout import MORNING, AFTERNOON
from .storage import atomic_write, sha
from .db import transaction, issue

VERSION='grid-6'


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
    """Find perspective table borders, then match the grid to a known schedule.

    Printed headings may omit the narrow time column, giving the outer contour
    a fifth corner. Intersect its four main edges before examining count rows.
    Small gaps in row-line evidence are repaired from the surrounding spacing.
    """
    preview=image.copy();preview.thumbnail((1600,1600))
    scale=np.array([image.width/preview.width,image.height/preview.height])
    gray=cv2.cvtColor(np.array(preview),cv2.COLOR_RGB2GRAY)
    bw=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,35,15)
    pages=[]
    for mask in (bw,cv2.morphologyEx(bw,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))):
        contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours,key=cv2.contourArea,reverse=True)[:30]:
            if cv2.contourArea(contour)<preview.width*preview.height*.04:continue
            hull=cv2.convexHull(contour)
            polygon=cv2.approxPolyDP(hull,.002*cv2.arcLength(hull,True),True).reshape(-1,2).astype(float)
            if not 4<=len(polygon)<=8:continue
            edges=[(p,q) for p,q in zip(polygon,np.roll(polygon,-1,axis=0))]
            main=sorted(sorted(range(len(edges)),key=lambda i:np.linalg.norm(edges[i][1]-edges[i][0]),reverse=True)[:4])
            vertices=[]
            for first,second in zip(main,main[1:]+main[:1]):
                p,q=edges[first];r,s=edges[second]
                matrix=np.column_stack((q-p,r-s))
                if abs(np.linalg.det(matrix))<1:break
                t,_=np.linalg.solve(matrix,r-p);vertices.append((p+t*(q-p))*scale)
            if len(vertices)!=4:continue
            vertices=sorted(vertices,key=lambda p:p[1])
            tl,tr=sorted(vertices[:2],key=lambda p:p[0]);bl,br=sorted(vertices[2:],key=lambda p:p[0])
            corners=np.array([tl,tr,br,bl])
            if np.any(corners<0) or np.any(corners[:,0]>=image.width) or np.any(corners[:,1]>=image.height):continue
            try:
                table,transform=aligned_table(image,corners)
                gray_table=cv2.cvtColor(np.array(table),cv2.COLOR_RGB2GRAY)
                binary=cv2.adaptiveThreshold(gray_table,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,35,12)
                ys,horizontal=observed_rows(binary)
                if len(ys)<3:continue
                # Detect headings independently of the expected row count: a
                # heading must never stand in for a missing count row.
                y=round(ys[0]);ink=np.where(horizontal[max(0,y-2):y+3].max(axis=0)>0)[0]
                outline=cv2.perspectiveTransform(np.float32([polygon*scale]),np.array(transform))[0]
                pitch=float(np.median(np.diff(ys)))
                inset_heading=(any(abs(x)<table.width*.03 and pitch*.5<y<pitch*1.5 for x,y in outline)
                               and any(abs(y)<pitch*.25 and table.width*.035<x<table.width*.25 for x,y in outline))
                has_heading=inset_heading or bool(len(ink) and ink[0]>table.width*.035)
                ys=fit_rows(ys,table.height,{33,38,69} if has_heading else {32,37,68})
                if has_heading:ys=ys[1:]
                sections={32:'morning',37:'afternoon',68:'both'}
                if len(ys) not in sections:continue
                xs=column_boundaries(table,binary)
                bounds=np.float32([[[xs[0],ys[0]],[xs[-1],ys[0]],[xs[-1],ys[-1]],[xs[0],ys[-1]]]])
                mapped=cv2.perspectiveTransform(bounds,np.linalg.inv(np.array(transform)))[0]
                mapped[:,0]=np.clip(mapped[:,0],0,image.width-1)
                mapped[:,1]=np.clip(mapped[:,1],0,image.height-1)
                spec=dict(section=sections[len(ys)],corners=mapped.tolist(),layout='auto')
                checked,_=aligned_table(image,spec['corners'])
                lines,checked_bw=row_boundaries(checked)
                if len(lines)!=len(ys):continue
                column_boundaries(checked,checked_bw)
            except (ValueError,cv2.error,np.linalg.LinAlgError):continue
            # Threshold variants often find the same table. Keep one outline.
            if any(cv2.intersectConvexConvex(np.float32(p['corners']),mapped)[0]>.5*cv2.contourArea(mapped) for p in pages):continue
            pages.append(spec)
    if not pages or len(pages)>2 or len({p['section'] for p in pages})!=len(pages) or (len(pages)>1 and any(p['section']=='both' for p in pages)):
        raise ValueError('Automatic table detection could not verify all seven columns and count rows. Mark the four table corners.')
    pages.sort(key=lambda p:min(c[1] for c in p['corners']))
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


def grid_segments(bw):
    scale=min(1.,900/max(bw.shape))
    if scale<1:bw=cv2.resize(bw,None,fx=scale,fy=scale,interpolation=cv2.INTER_NEAREST)
    h,w=bw.shape
    found=cv2.HoughLinesP(bw,1,np.pi/360,threshold=max(30,w//8),
                          minLineLength=max(20,w//5),maxLineGap=max(8,w//40))
    if found is None:return []
    segments=[]
    for line in found.reshape(-1,4):
        x1,y1,x2,y2=map(int,line)
        if abs(x2-x1)<w*.2 or abs((y2-y1)/(x2-x1))>=.14:continue
        xx=np.rint(np.linspace(x1,x2,abs(x2-x1)+1)).astype(int)
        yy=np.rint(np.linspace(y1,y2,len(xx))).astype(int)
        support=np.maximum.reduce([bw[np.clip(yy+offset,0,h-1),xx] for offset in (-1,0,1)])
        if np.mean(support>0)>=.65:segments.append(line.astype(float)/scale)
    return segments


def aligned_table(image,corners):
    """Remove residual row slant after an imprecise perspective selection."""
    table,transform=rectify(image,corners)
    gray=cv2.cvtColor(np.array(table),cv2.COLOR_RGB2GRAY)
    bw=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,35,12)
    observed,_=observed_rows(bw)
    if len(observed)>=24:return table,transform
    segments=grid_segments(bw)
    if len(segments)<8:return table,transform
    slopes=[(y2-y1)/(x2-x1) for x1,y1,x2,y2 in segments]
    slope=float(np.median(slopes))
    if abs(slope)<.003:return table,transform
    # A vertical shear straightens rows without shifting column boundaries.
    shear=np.array([[1.,0.,0.],[-slope,1.,slope*(table.width-1)/2],[0.,0.,1.]])
    corrected=cv2.warpPerspective(np.array(table),shear,table.size,borderValue=(255,255,255))
    return Image.fromarray(corrected),(shear@np.array(transform)).tolist()


def observed_rows(bw):
    h,w=bw.shape
    horizontal=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((1,max(10,w//3)),np.uint8))
    lines=line_centers(horizontal,1,w*.45)
    pitch=float(np.median(np.diff(lines))) if len(lines)>3 else h/40
    return strip_boundaries(bw,lines,True,max(4,min(10,pitch*.25))),horizontal


def strip_boundaries(bw,observed,horizontal,tolerance):
    """Vote across image strips so bent/faint lines need not be pixel-perfect."""
    if not horizontal:bw=bw.T
    h,w=bw.shape
    candidates=[(y,-1) for y in observed]
    for index,strip in enumerate(np.array_split(bw,5,axis=1)):
        mask=cv2.morphologyEx(strip,cv2.MORPH_OPEN,np.ones((1,max(8,strip.shape[1]//2)),np.uint8))
        candidates.extend((y,index) for y in line_centers(mask,1,strip.shape[1]*.6))
    groups=[]
    for point in sorted(candidates):
        if not groups or point[0]-np.median([p[0] for p in groups[-1]])>tolerance:groups.append([])
        groups[-1].append(point)
    return [float(np.median([p[0] for p in group])) for group in groups
            if -1 in {p[1] for p in group} or len({p[1] for p in group})>=3]


def fit_rows(lines,height,supported=None):
    """Keep observed spacing, merging doubled lines and repairing short gaps.

    At least 88% of the boundaries must be observed, with at most two adjacent
    missing separators. The caller still requires an exact supported row count.
    """
    if len(lines)<8:raise ValueError('Table grid lines could not be identified')
    pitch=float(np.median(np.diff(lines)))
    if pitch<5:raise ValueError('Table row spacing could not be identified')
    merged=[]
    for y in lines:
        if merged and y-merged[-1]<pitch*.45:merged[-1]=(merged[-1]+y)/2
        else:merged.append(float(y))
    pitch=float(np.median(np.diff(merged)))
    # Small white margins are normal for approximate clicks. Do not mistake
    # that padding for an extra row when the observed schedule already fits.
    if merged[0]>pitch*1.4 or height-1-merged[-1]>pitch*1.4:
        raise ValueError('Keep the box near the first and last count rows; exclude headings')
    fitted=[merged[0]];missing=0
    for first,last in zip(merged,merged[1:]):
        steps=max(1,round((last-first)/pitch))
        if steps>3 or abs((last-first)/steps-pitch)>pitch*.4:
            raise ValueError('Too many table rows are obscured; adjust the box or use a clearer photo')
        missing+=steps-1
        fitted.extend(np.linspace(first,last,steps+1)[1:].tolist())
    if missing>max(2,int((len(fitted)-1)*.12)) or np.std(np.diff(fitted))/np.mean(np.diff(fitted))>.3:
        raise ValueError('Table row spacing could not be matched reliably; adjust the box')
    supported={32,37,68} if supported is None else supported
    if len(fitted) not in supported:
        possible=[]
        top=pitch*.55<fitted[0]<pitch*1.4
        bottom=pitch*.55<height-1-fitted[-1]<pitch*1.4
        if top:possible.append([0.]+fitted)
        if bottom:possible.append(fitted+[float(height-1)])
        if top and bottom:possible.append([0.]+fitted+[float(height-1)])
        possible=[candidate for candidate in possible if len(candidate) in supported]
        if len(possible)==1:fitted=possible[0]
    return fitted


def row_boundaries(table):
    gray=cv2.cvtColor(np.array(table),cv2.COLOR_RGB2GRAY)
    bw=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,35,12)
    lines,_=observed_rows(bw)
    return fit_rows(lines,table.height),bw


def identify_section(image,corners):
    table,_=aligned_table(image,corners)
    ys,_=row_boundaries(table)
    if len(ys)==32:return 'morning'
    if len(ys)==37:return 'afternoon'
    if len(ys)==68:return 'both'
    raise ValueError(f'Found {len(ys)-1} rows. Expected 31 morning, 36 afternoon, or 67 full-day rows. Include the whole count table and exclude headings.')


def column_boundaries(table,bw):
    vertical=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((max(10,table.height//3),1),np.uint8))
    xs=line_centers(vertical,0,table.height*.4)
    xs=strip_boundaries(bw,xs,False,max(5,min(15,table.width*.012)))
    if len(xs)<6:
        candidates=[(x,table.height) for x in xs]
        for y1,x1,y2,x2 in grid_segments(bw.T):
            x=x1+((table.height-1)/2-y1)*(x2-x1)/(y2-y1)
            if 0<=x<table.width:candidates.append((float(x),abs(y2-y1)))
        groups=[]
        tolerance=max(5,min(15,table.width*.012))
        for point in sorted(candidates):
            if not groups or point[0]-np.median([p[0] for p in groups[-1]])>tolerance:groups.append([])
            groups[-1].append(point)
        xs=[float(np.median([p[0] for p in group])) for group in groups if max(p[1] for p in group)>table.height*.35]
    pitch=float(np.median(np.diff(xs))) if len(xs)>1 else table.width/7
    edge_tolerance=max(8,min(pitch*.2,table.width*.025))
    if not xs or xs[0]>edge_tolerance:xs.insert(0,0)
    if table.width-1-xs[-1]>edge_tolerance:xs.append(table.width-1)
    if xs[0]>edge_tolerance or table.width-1-xs[-1]>edge_tolerance:
        raise ValueError('Column geometry uncertain; mark close to the table borders')
    if len(xs)!=8:raise ValueError('Column geometry uncertain; corners must include all seven columns')
    return xs


def preprocess(source):
    image=Image.open(source['normalized']).convert('RGB')
    specifications=json.loads(source['geometry']) if source['geometry'] else detect(image)
    if not source['geometry']:
        for spec in specifications:spec['layout']=source.get('layout_hint','auto')
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
        if section not in ('morning','afternoon','both'):raise ValueError('Section must be morning, afternoon or both')
        table,transform=aligned_table(image,spec['corners'])
        ys,bw=row_boundaries(table)
        xs=column_boundaries(table,bw)
        expected=MORNING if section=='morning' else AFTERNOON if section=='afternoon' else MORNING+AFTERNOON
        if len(ys)!=len(expected)+1:
            raise ValueError(f'Found {len(ys)-1} rows; {section} expects {len(expected)}. Include the whole count table and exclude headings.')
        tablepath=save_image(directory/f'{section}.png',table)
        page_specs.append((section,json.dumps({**spec,'row_boundaries':ys,'row_method':VERSION}),json.dumps(transform),tablepath))
        layout=spec.get('layout','auto')
        if layout=='auto':layout='monthly' if section=='both' else 'legacy'
        mapping={'legacy':[0,1,None,2,3],'new-paper':[0,1,2,3,4],'monthly':[1,2,3,4,5]}
        if layout not in mapping:raise ValueError('Unknown sheet layout')
        for pass_name,size in [('A',settings.rows_per_band),('B',max(1,settings.rows_per_band//2))]:
            if pass_name=='B' and settings.verification=='off':continue
            for start in range(0,len(expected),size):
                stop=min(start+size,len(expected))
                # Normalize both source layouts to time/public/external/internal/dry.
                top=max(0,int(ys[start])-2);bottom=min(table.height,int(ys[stop])+2)
                strips=[]
                for index in mapping[layout]:
                    if index is None:strips.append(Image.new('RGB',(max(40,round(xs[2]-xs[1])),bottom-top),'white'))
                    else:strips.append(table.crop((int(xs[index]),top,int(xs[index+1])+1,bottom)))
                crop_im=Image.new('RGB',(sum(s.width for s in strips),bottom-top+22),'white')
                draw=ImageDraw.Draw(crop_im);left=0
                for label,strip in zip(['TIME','PUBLIC','EXTERNAL','INTERNAL','DRY'],strips):
                    crop_im.paste(strip,(left,22));draw.text((left+2,3),label,fill='black');left+=strip.width
                name=f'{section}-{pass_name}-{start:02}'
                crop=save_image(directory/f'{name}.png',crop_im)
                task_specs.append((pass_name,crop,expected[start:stop],name))
    from .prompts import VERSION as PROMPT_VERSION, SCHEMA_VERSION
    fingerprint=sha(json.dumps({'version':VERSION,'prompt':PROMPT_VERSION,'schema':SCHEMA_VERSION,'rows':settings.rows_per_band,'geometry':specifications,'profile':settings.profile(),'model':settings.ollama_model,'think':settings.think,'rough_counts':settings.rough_counts,'verification':settings.verification},sort_keys=True).encode())
    with transaction() as db:
        current=db.execute('SELECT version,state FROM sources WHERE id=?',(source['id'],)).fetchone()
        if not current or current['version']!=source['version'] or current['state']!='pending':return
        for section,geometry,transform,path in page_specs:
            db.execute('INSERT OR IGNORE INTO pages(source_id,version,section,geometry,transform,path) VALUES(?,?,?,?,?,?)',(source['id'],source['version'],section,geometry,transform,path))
        for pass_name,crop,expected,name in task_specs:
            task_key=f"{source['hash']}:{source['version']}:{fingerprint}:{name}"
            db.execute('INSERT OR IGNORE INTO tasks(job_id,source_id,key,version,pass,crop,expected) VALUES(?,?,?,?,?,?,?)',(source['job_id'],source['id'],task_key,source['version'],pass_name,crop,json.dumps(expected)))
        db.execute("UPDATE sources SET state='processing',geometry=? WHERE id=?",(json.dumps(specifications),source['id']))
        db.execute("UPDATE issues SET resolved=1 WHERE source_id=? AND kind='geometry'",(source['id'],))
