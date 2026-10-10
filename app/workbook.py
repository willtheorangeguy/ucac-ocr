"""Narrow OOXML adapter: preserve original parts, clone BLANK XML and relationships.

openpyxl is used for layout/readback validation only. No private image APIs.
Shared drawings/media/printer settings are immutable and may be referenced by
multiple daily sheets. This avoids openpyxl's destructive round-trip of parts.
"""
import copy
import io
import posixpath
import re
import zipfile
from datetime import datetime, time
from lxml import etree as E
from openpyxl import load_workbook
from openpyxl.utils.datetime import to_excel
from .layout import SCHEDULE, EXCEL_COLS, dates
from .storage import atomic_write

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
NS = {'s':S}

# Excel reduces a 3-D range to 'Boundary B' after its first daily tab is deleted.
# Accept that empty-template reference, and equivalent whitespace/absolute cells,
# while still requiring AVERAGE, the empty-string fallback and the correct anchor.
MASTER_AVERAGE = re.compile(
    r'''^=\s*IFERROR\s*\(\s*AVERAGE\s*\(\s*(?P<reference>'(?:[^']|'')+'|[A-Za-z0-9_ :]+)!\s*(?P<cell>\$?[CDEFGH]\$?\d+)\s*\)\s*,\s*""\s*\)\s*$''',
    re.IGNORECASE,
)


def master_reference(formula, coordinate=None):
    match=MASTER_AVERAGE.fullmatch(formula) if isinstance(formula,str) else None
    if match:
        reference=match.group('reference')
        name=reference[1:-1].replace("''", "'") if reference.startswith("'") else reference.strip()
        endpoints=name.split(':')
        valid=(endpoints==['Boundary B'] or (len(endpoints)==2 and bool(endpoints[0]) and endpoints[1]=='Boundary B'))
        cell=match.group('cell').replace('$','').upper()
        if valid and (coordinate is None or cell==coordinate):return match
    return None


def parse(data):
    return E.fromstring(data,E.XMLParser(resolve_entities=False,no_network=True))


def xml(root):
    return E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)


def parts(path):
    with zipfile.ZipFile(path) as z:
        if len(z.namelist())>10000 or sum(i.file_size for i in z.infolist())>200_000_000:
            raise ValueError('Workbook expanded size exceeds limits')
        return {n:z.read(n) for n in z.namelist()}


def sheets(p):
    wb=parse(p['xl/workbook.xml']); rel=parse(p['xl/_rels/workbook.xml.rels'])
    targets={r.get('Id'):posixpath.normpath('xl/'+r.get('Target')) for r in rel}
    return wb,rel,{s.get('name'):(s,targets[s.get('{'+R+'}id')]) for s in wb.find('{'+S+'}sheets')}


def validate_template(path):
    p=parts(path)
    wb,rel,ss=sheets(p)
    for name in ('BLANK','MASTER','Boundary B'):
        if name not in ss: raise ValueError(f'Missing sheet {name}')
    values=load_workbook(path,data_only=True)
    formulas=load_workbook(path,data_only=False)
    try:
        b=values['BLANK']; f=formulas['BLANK']
        for label in ('Public','User','Dry'):
            if not any(label.lower() in str(c.value).lower() for row in b.iter_rows(min_row=1,max_row=9) for c in row):
                raise ValueError(f'Missing expected column label: {label}')
        if 'E3:H4' not in {str(r) for r in b.merged_cells.ranges}: raise ValueError('Date merge changed')
        found=set()
        for t,row in SCHEDULE.items():
            v=b[f'B{row}'].value
            minute=round(v*1440) if isinstance(v,(float,int)) else (v.hour*60+v.minute if isinstance(v,time) else None)
            if minute != int(t[:2])*60+int(t[3:]) or minute in found: raise ValueError(f'Time mapping changed at B{row}')
            found.add(minute)
            for col in 'CDE':
                if f'{col}{row}:{col}{row+1}' not in {str(r) for r in b.merged_cells.ranges}: raise ValueError('Count merges changed')
                if f[f'{col}{row}'].value is not None: raise ValueError('BLANK count inputs are not blank')
                if values['Boundary B'][f'{col}{row}'].value is not None: raise ValueError('Boundary has counts')
                mf=formulas['MASTER'][f'{col}{row}'].value
                if not master_reference(mf,f'{col}{row}'):
                    raise ValueError(f'MASTER!{col}{row} must average the matching cell through Boundary B, with an empty-string IFERROR fallback. Found: {mf!r}')
        if str(b.print_area) != "'BLANK'!$B$1:$H$149": raise ValueError('Print area changed')
        daily=[]
        for name in ss:
            if name in ('BLANK','MASTER','Boundary B','IMPORT REPORT'): continue
            d=values[name]['E3'].value
            if not isinstance(d,datetime): raise ValueError(f'Unrecognized daily sheet: {name}')
            counts={t+'|'+c:values[name][f'{col}{row}'].value for t,row in SCHEDULE.items() for c,col in EXCEL_COLS.items()}
            daily.append(dict(name=name,date=d.date().isoformat(),counts=counts))
        return daily
    finally:
        values.close(); formulas.close()


def set_cell(root,coord,value,style=None):
    sd=root.find('{'+S+'}sheetData')
    rownum=int(re.search(r'\d+',coord).group())
    row=sd.find(f'{{{S}}}row[@r="{rownum}"]')
    if row is None: row=E.SubElement(sd,'{'+S+'}row',r=str(rownum))
    c=row.find(f'{{{S}}}c[@r="{coord}"]')
    if c is None: c=E.SubElement(row,'{'+S+'}c',r=coord)
    for child in list(c): c.remove(child)
    c.attrib.pop('t',None)
    if style is not None: c.set('s',style)
    if value is not None: E.SubElement(c,'{'+S+'}v').text=str(value)


def report_sheet(lines):
    root=E.Element('{'+S+'}worksheet',nsmap={None:S}); sd=E.SubElement(root,'{'+S+'}sheetData')
    for i,line in enumerate(lines,1):
        row=E.SubElement(sd,'{'+S+'}row',r=str(i))
        for j,text in enumerate(line):
            c=E.SubElement(row,'{'+S+'}c',r=f'{chr(65+j)}{i}',t='inlineStr')
            E.SubElement(E.SubElement(c,'{'+S+'}is'),'{'+S+'}t').text=str(text)
    return xml(root)


def generate(template,output,year,month,records,issues,revision,mode='new-month',coverage_ack=False,source_report=None):
    existing=validate_template(template)
    if mode=='continuation' and any(not x['date'].startswith(f'{year:04}-{month:02}-') for x in existing):
        raise ValueError('Continuation cannot span another month')
    p=parts(template); wb,rel,ss=sheets(p); container=wb.find('{'+S+'}sheets')
    blankpath=ss['BLANK'][1]; blank=p[blankpath]
    date_style='23'
    if existing:
        er=parse(p[ss[existing[0]['name']][1]])
        date_style=er.find('.//{'+S+'}c[@r="E3"]').get('s')
    else:
        # Require a genuine date number format via an isolated openpyxl style build.
        styles=parse(p['xl/styles.xml']); fmts=styles.find('{'+S+'}numFmts')
        if fmts is None: fmts=E.Element('{'+S+'}numFmts',count='0'); styles.insert(0,fmts)
        fmtid=max([163]+[int(x.get('numFmtId')) for x in fmts])+1
        E.SubElement(fmts,'{'+S+'}numFmt',numFmtId=str(fmtid),formatCode='mmmm d, yyyy'); fmts.set('count',str(len(fmts)))
        xfs=styles.find('{'+S+'}cellXfs'); base=copy.deepcopy(xfs[int(parse(blank).find('.//{'+S+'}c[@r="E3"]').get('s'))])
        base.set('numFmtId',str(fmtid)); base.set('applyNumberFormat','1'); date_style=str(len(xfs)); xfs.append(base); xfs.set('count',str(len(xfs))); p['xl/styles.xml']=xml(styles)
    keep={'BLANK','MASTER','Boundary B'}
    if mode=='continuation': keep.update(x['name'] for x in existing)
    for s in list(container):
        if s.get('name') not in keep: container.remove(s)
    # Local print names need sheet-index updates after replacing sample days.
    dn=wb.find('{'+S+'}definedNames')
    if dn is None: dn=E.SubElement(wb,'{'+S+'}definedNames')
    oldnames=[copy.deepcopy(x) for x in dn if x.get('localSheetId') is not None]
    oldorder=list(ss)
    for x in list(dn):
        if x.get('localSheetId') is not None: dn.remove(x)
    types=parse(p['[Content_Types].xml'])
    nextid=max(int(s.get('sheetId')) for s,_ in ss.values())+1
    generated={}; boundary=ss['Boundary B'][0]; boundary.set('state','hidden')
    for day in dates(year,month):
        name=day.strftime('%B ') + str(day.day)
        match=next((x for x in existing if x['date']==day.isoformat()),None) if mode=='continuation' else None
        if match:
            name=match['name']; sp=ss[name][1]; root=parse(p[sp]); s=ss[name][0]
            container.remove(s)
        else:
            sp=f'xl/worksheets/import{nextid}.xml'; root=parse(blank)
            rid=f'import{nextid}'
            s=E.Element('{'+S+'}sheet',name=name,sheetId=str(nextid)); s.set('{'+R+'}id',rid)
            E.SubElement(rel,'{'+P+'}Relationship',Id=rid,Type=R+'/worksheet',Target=sp[3:])
            E.SubElement(types,'{'+CT+'}Override',PartName='/'+sp,ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
            brels=posixpath.dirname(blankpath)+'/_rels/'+posixpath.basename(blankpath)+'.rels'
            if brels in p: p['xl/worksheets/_rels/'+posixpath.basename(sp)+'.rels']=p[brels]
            nextid+=1
            set_cell(root,'E3',to_excel(datetime.combine(day,time())),date_style)
        container.insert(list(container).index(boundary),s)
        generated[day.isoformat()]=(root,sp,name)
    for record in records:
        if record['date'] not in generated or record['time'] not in SCHEDULE or record['column_name'] not in EXCEL_COLS: raise ValueError('Record outside layout/month')
        root=generated[record['date']][0]
        set_cell(root,EXCEL_COLS[record['column_name']]+str(SCHEDULE[record['time']]),record['value'] if record['status']=='accepted' else None)
    for root,sp,_ in generated.values(): p[sp]=xml(root)
    start=next(iter(generated.values()))[2]
    master=parse(p[ss['MASTER'][1]])
    for f in master.findall('.//{'+S+'}f'):
        matched=master_reference('='+f.text) if f.text else None
        if matched:
            begin,end=matched.span('reference')
            # XML formula text omits '=', so adjust the matched string offsets.
            f.text=f.text[:begin-1]+f"'{start}:Boundary B'"+f.text[end-1:]
            parent=f.getparent(); v=parent.find('{'+S+'}v')
            if v is not None: parent.remove(v)
    p[ss['MASTER'][1]]=xml(master)
    for s in container:
        idx=list(container).index(s); name=s.get('name')
        restored=False
        for old in oldnames:
            if oldorder[int(old.get('localSheetId'))]==name:
                d=copy.deepcopy(old); d.set('localSheetId',str(idx)); dn.append(d); restored=True
        if not restored:
            E.SubElement(dn,'{'+S+'}definedName',name='_xlnm.Print_Area',localSheetId=str(idx)).text=f"'{name}'!$B$1:$H$149"
    sourced={r['date'] for r in records if r.get('provenance') and r['status']=='accepted'}
    missing=[d.isoformat() for d in dates(year,month) if d.isoformat() not in sourced]
    coverage={r['date']+'|'+r['time']+'|'+r['column_name'] for r in records}
    missing_slots={d.isoformat():sum(d.isoformat()+'|'+t+'|'+c not in coverage for t in SCHEDULE for c in EXCEL_COLS) for d in dates(year,month)}
    draft=bool(issues or (any(missing_slots.values()) and not coverage_ack))
    lines=[['POOL IMPORT REPORT', 'NEEDS REVIEW' if draft else 'FINAL'],['Revision',revision],['Recalculation','Open in Excel/LibreOffice; cached MASTER values not calculated'],['Meaning','MASTER averages individual time-slot counts; blanks excluded, zeros included']]
    for d in missing: lines.append(['Missing day',d,'No source; acknowledged' if coverage_ack else 'Needs coverage acknowledgement'])
    for d,slots in missing_slots.items():
        if slots and d not in missing:lines.append(['Unobserved cells',d,slots,'No source; acknowledged' if coverage_ack else 'Needs coverage acknowledgement'])
    for i in issues: lines.append(['Unresolved',i.get('kind',''),i.get('cell_key') or i.get('source_id') or '',i.get('detail','')])
    for src in source_report or []:
        lines.append(['Source',src['filename'],src['state'],src.get('assigned_date') or src.get('observed_date') or 'date unassigned',src['hash']])
    means={}
    for t in SCHEDULE:
        for c in EXCEL_COLS:
            nums=[r['value'] for r in records if r['time']==t and r['column_name']==c and r['status']=='accepted' and r['value'] is not None]
            if nums: means[t+'|'+c]=sum(nums)/len(nums); lines.append(['Expected average',t,c,means[t+'|'+c]])
    rp=f'xl/worksheets/import{nextid}.xml'; p[rp]=report_sheet(lines)
    rs=E.SubElement(container,'{'+S+'}sheet',name='IMPORT REPORT',sheetId=str(nextid)); rs.set('{'+R+'}id',f'import{nextid}')
    E.SubElement(rel,'{'+P+'}Relationship',Id=f'import{nextid}',Type=R+'/worksheet',Target=rp[3:])
    E.SubElement(types,'{'+CT+'}Override',PartName='/'+rp,ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
    calc=wb.find('{'+S+'}calcPr')
    if calc is None: calc=E.SubElement(wb,'{'+S+'}calcPr')
    calc.set('fullCalcOnLoad','1'); calc.set('forceFullCalc','1'); calc.set('calcMode','auto')
    for r in list(rel):
        if r.get('Type','').endswith('/calcChain'): rel.remove(r)
    p.pop('xl/calcChain.xml',None)
    for x in list(types):
        if x.get('PartName')=='/xl/calcChain.xml': types.remove(x)
    p['xl/workbook.xml']=xml(wb); p['xl/_rels/workbook.xml.rels']=xml(rel); p['[Content_Types].xml']=xml(types)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in p.items(): z.writestr(name,data)
    atomic_write(output,out.getvalue())
    with zipfile.ZipFile(output) as z:
        if z.testzip(): raise ValueError('Invalid exported archive')
    check=load_workbook(output,read_only=True)
    try:
        expected=['BLANK','MASTER']+[v[2] for v in generated.values()]+['Boundary B','IMPORT REPORT']
        if check.sheetnames!=expected: raise ValueError('Invalid output sheet ordering')
        if check['Boundary B'].sheet_state!='hidden': raise ValueError('Boundary must be hidden')
        validated={}
        for r in records:
            if r['status']=='accepted':
                cell=EXCEL_COLS[r['column_name']]+str(SCHEDULE[r['time']])
                if r['date'] not in validated:
                    validated[r['date']]={c.coordinate:c.value for row in check[generated[r['date']][2]].iter_rows() for c in row if hasattr(c,'coordinate')}
                if validated[r['date']].get(cell) != r['value']: raise ValueError('Export value mismatch')
    finally: check.close()
    return dict(draft=draft,missing_days=missing,missing_slots=missing_slots,expected_averages=means,recalculated=False)
