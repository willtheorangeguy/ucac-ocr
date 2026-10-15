"""OOXML helpers and validation for legacy daily and new monthly workbooks."""
import posixpath
import re
import zipfile
from lxml import etree as E
from openpyxl.utils.datetime import from_excel, CALENDAR_MAC_1904
from .layout import SCHEDULE, LEGACY_EXCEL_COLS as EXCEL_COLS

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
    targets={r.get('Id'):posixpath.normpath(r.get('Target').lstrip('/') if r.get('Target').startswith('/') else 'xl/'+r.get('Target')) for r in rel}
    return wb,rel,{s.get('name'):(s,targets[s.get('{'+R+'}id')]) for s in wb.find('{'+S+'}sheets')}


def validate_template(path,year=None,month=None):
    p=parts(path)
    wb,rel,ss=sheets(p)
    from .monthly_workbook import is_monthly, read_monthly
    if is_monthly(p):return read_monthly(p,year,month)
    for name in ('BLANK','MASTER','Boundary B'):
        if name not in ss: raise ValueError(f'Missing sheet {name}')
    from .monthly_workbook import cells, strings, value
    shared=strings(p)
    blank=parse(p[ss['BLANK'][1]]); b=cells(blank)
    master=cells(parse(p[ss['MASTER'][1]])); boundary=cells(parse(p[ss['Boundary B'][1]]))
    merges={r.get('ref') for r in blank.findall('{'+S+'}mergeCells/{'+S+'}mergeCell')}
    labels=[str(value(c,shared)).lower() for coord,c in b.items() if int(re.search(r'\d+',coord).group())<=9]
    for label in ('public','user','dry'):
        if not any(label in text for text in labels):raise ValueError(f'Missing expected column label: {label}')
    if 'E3:H4' not in merges:raise ValueError('Date merge changed')
    for t,row in SCHEDULE.items():
        v=value(b.get(f'B{row}'),shared)
        if not isinstance(v,(int,float)) or round(v*1440)!=int(t[:2])*60+int(t[3:]):raise ValueError(f'Time mapping changed at B{row}')
        for col in 'CDE':
            coord=f'{col}{row}'
            if f'{coord}:{col}{row+1}' not in merges:raise ValueError('Count merges changed')
            c=b.get(coord)
            if value(c,shared) is not None or (c is not None and c.find('{'+S+'}f') is not None):raise ValueError('BLANK count inputs are not blank')
            if value(boundary.get(coord),shared) is not None:raise ValueError('Boundary has counts')
            c=master.get(coord);f=c.find('{'+S+'}f') if c is not None else None
            mf='='+f.text if f is not None and f.text else None
            if not master_reference(mf,coord):raise ValueError(f'MASTER!{coord} must average the matching cell through Boundary B, with an empty-string IFERROR fallback. Found: {mf!r}')
    names=wb.find('{'+S+'}definedNames')
    blank_index=list(ss).index('BLANK')
    if names is None or not any(n.get('name')=='_xlnm.Print_Area' and n.get('localSheetId')==str(blank_index) and n.text in ("'BLANK'!$B$1:$H$149",'BLANK!$B$1:$H$149') for n in names):raise ValueError('Print area changed')
    props=wb.find('{'+S+'}workbookPr')
    epoch={'epoch':CALENDAR_MAC_1904} if props is not None and props.get('date1904') in ('1','true') else {}
    daily=[]
    for name,(_,path) in ss.items():
        if name in ('BLANK','MASTER','Boundary B','IMPORT REPORT'):continue
        cs=cells(parse(p[path]));v=value(cs.get('E3'),shared)
        if not isinstance(v,(int,float)):raise ValueError(f'Unrecognized daily sheet: {name}')
        d=from_excel(v,**epoch)
        counts={t+'|'+c:value(cs.get(f'{col}{row}'),shared) for t,row in SCHEDULE.items() for c,col in EXCEL_COLS.items()}
        daily.append(dict(name=name,date=d.date().isoformat(),counts=counts))
    return daily


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
    from .monthly_workbook import generate_monthly
    return generate_monthly(template,output,year,month,records,issues,revision,mode,coverage_ack,source_report)
