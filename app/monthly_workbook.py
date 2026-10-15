"""Fall 2026 monthly entry layout; edit OOXML without a destructive round trip."""
import io
import re
import zipfile
from datetime import date, datetime, time
from pathlib import Path
from lxml import etree as E

from openpyxl.utils.datetime import from_excel, to_excel, CALENDAR_MAC_1904
from openpyxl.formula.translate import Translator

from .layout import COLUMNS, EXCEL_COLS, SCHEDULE, MONTH_ROWS, dates, month_cell
from .storage import atomic_write
from .workbook import S, R, P, CT, parts, sheets, parse, xml, report_sheet

DEFAULT_TEMPLATE = Path(__file__).parent/'assets/monthly-template.xlsx'


def cells(root):
    return {c.get('r'):c for c in root.findall('.//{'+S+'}sheetData/{'+S+'}row/{'+S+'}c')}


class SheetWriter:
    def __init__(self,root):
        self.data=root.find('{'+S+'}sheetData')
        self.rows={int(row.get('r')):row for row in self.data}
        self.cells=cells(root)

    def set(self,coord,value,formula=False):
        c=self.cells.get(coord)
        if c is None:
            rownum=int(''.join(filter(str.isdigit,coord)))
            row=self.rows.get(rownum)
            if row is None:
                row=E.SubElement(self.data,'{'+S+'}row',r=str(rownum));self.rows[rownum]=row
            c=E.SubElement(row,'{'+S+'}c',r=coord);self.cells[coord]=c
        for child in list(c):c.remove(child)
        c.attrib.pop('t',None)
        if value is not None:E.SubElement(c,'{'+S+'}f' if formula else '{'+S+'}v').text=str(value)


def strings(p):
    return [''.join(si.itertext()) for si in parse(p['xl/sharedStrings.xml'])] if 'xl/sharedStrings.xml' in p else []


def value(c, shared):
    if c is None:return None
    if c.get('t')=='inlineStr':return ''.join(c.find('{'+S+'}is').itertext())
    v=c.find('{'+S+'}v')
    if v is None or v.text is None:return None
    if c.get('t')=='s':return shared[int(v.text)]
    if c.get('t') in ('str','e','b'):return v.text
    n=float(v.text)
    return int(n) if n.is_integer() else n


def is_monthly(p):
    _,_,ss=sheets(p)
    if 'BLANK' not in ss:return False
    cs=cells(parse(p[ss['BLANK'][1]])); shared=strings(p)
    return str(value(cs.get('F3'),shared)).strip().upper()=='INTERNAL:'


def entry_name(year,month):
    return 'DATA ENTRY - '+date(year,month,1).strftime('%b %Y').upper()


def read_monthly(p,year=None,month=None):
    wb,_,ss=sheets(p); shared=strings(p)
    blank=cells(parse(p[ss['BLANK'][1]]))
    shared_formulas={f.get('si'):(coord,f.text) for coord,c in blank.items() if (f:=c.find('{'+S+'}f')) is not None and f.get('t')=='shared' and f.text}
    for col,label in [('C','TIME:'),('D','PUBLIC:'),('E','EXTERNAL:'),('F','INTERNAL:'),('G','DRY:')]:
        if str(value(blank.get(col+'3'),shared)).strip().upper()!=label:
            raise ValueError(f'Unexpected monthly column {col}: expected {label}')
    for block in range(31):
        for t,row in MONTH_ROWS.items():
            coord=f'C{block*70+row}'
            c=blank.get(coord)
            if c is None:raise ValueError(f'Monthly time cell missing: {coord}')
            # Excel stores later times as shared formulas, sometimes without caches.
            formula=c.find('{'+S+'}f')
            if formula is None:
                v=value(c,shared)
                if not isinstance(v,(int,float)) or round(v*1440)!=int(t[:2])*60+int(t[3:]):
                    raise ValueError(f'Monthly time mapping changed at {coord}')
            else:
                text=formula.text
                if not text and formula.get('t')=='shared':
                    origin,text=shared_formulas.get(formula.get('si'),(None,None))
                    if text:text=Translator('='+text,origin=origin).translate_formula(coord)[1:]
                expected=f'C{block*70+row-1}+TIME(0,15,0)'
                if row==4 or re.sub(r'\s+','',text or '').upper()!=expected:
                    raise ValueError(f'Monthly time mapping changed at {coord}')
            for col in EXCEL_COLS.values():
                count=blank.get(f'{col}{block*70+row}')
                if value(count,shared) is not None or (count is not None and count.find('{'+S+'}f') is not None):
                    raise ValueError('BLANK count inputs are not blank')
    result=[]
    props=wb.find('{'+S+'}workbookPr')
    epoch={'epoch':CALENDAR_MAC_1904} if props is not None and props.get('date1904') in ('1','true') else {}
    for name,(_,path) in ss.items():
        if not name.startswith('DATA ENTRY - '):continue
        if year is not None and name!=entry_name(year,month):continue
        cs=cells(parse(p[path])); start=value(cs.get('G2'),shared)
        if start is None:continue
        if not isinstance(start,(int,float)):raise ValueError(f'{name}!G2 must contain a date')
        first=from_excel(start,**epoch).date()
        if year is not None and (first.year,first.month)!=(year,month):raise ValueError('Continuation requires dates in selected month')
        if first.day!=1:raise ValueError(f'{name}!G2 must be the first of the month')
        for day in dates(first.year,first.month):
            counts={t+'|'+col:value(cs.get(month_cell(day.isoformat(),t,col)),shared) for t in SCHEDULE for col in COLUMNS}
            if any(v is not None and (type(v) is not int or not 0<=v<=1_000_000_000) for v in counts.values()):
                raise ValueError(f'{name}: existing counts must be nonnegative whole numbers or blank')
            result.append(dict(name=name,date=day.isoformat(),counts=counts))
    return result


def generate_monthly(template,output,year,month,records,issues,revision,mode,coverage_ack,source_report):
    from .workbook import validate_template
    if mode not in ('new-month','continuation'):raise ValueError('Choose new-month or continuation')
    incoming=parts(template); modern=is_monthly(incoming)
    existing=validate_template(template,year,month)
    if mode=='continuation' and any(not x['date'].startswith(f'{year:04}-{month:02}-') for x in existing):
        raise ValueError('Continuation cannot span another month')
    p=incoming if modern else parts(DEFAULT_TEMPLATE)
    wb,rel,ss=sheets(p); container=wb.find('{'+S+'}sheets'); types=parse(p['[Content_Types].xml'])
    blankpath=ss['BLANK'][1]; name=entry_name(year,month)
    keep_existing=modern and mode=='continuation' and name in ss
    root=parse(p[ss[name][1] if keep_existing else blankpath])
    writer=SheetWriter(root)
    nextid=max(int(s.get('sheetId')) for s,_ in ss.values())+1

    def add_sheet(name,clone_rels=False):
        nonlocal nextid
        path=f'xl/worksheets/import{nextid}.xml'; rid=f'import{nextid}'
        sheet=E.Element('{'+S+'}sheet',name=name,sheetId=str(nextid));sheet.set('{'+R+'}id',rid);container.append(sheet)
        E.SubElement(rel,'{'+P+'}Relationship',Id=rid,Type=R+'/worksheet',Target=path[3:])
        E.SubElement(types,'{'+CT+'}Override',PartName='/'+path,ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
        if clone_rels:
            source='xl/worksheets/_rels/'+Path(blankpath).name+'.rels'
            if source in p:p['xl/worksheets/_rels/'+Path(path).name+'.rels']=p[source]
        nextid+=1
        return path

    target=ss[name][1] if name in ss else add_sheet(name,True)
    if not keep_existing and name in ss:
        source='xl/worksheets/_rels/'+Path(blankpath).name+'.rels'
        if source in p:p['xl/worksheets/_rels/'+Path(target).name+'.rels']=p[source]
    # Write all date/time cells explicitly; no reliance on cached/shared formulas.
    daylist=dates(year,month)
    day_keys={d.isoformat() for d in daylist}
    props=wb.find('{'+S+'}workbookPr')
    epoch={'epoch':CALENDAR_MAC_1904} if props is not None and props.get('date1904') in ('1','true') else {}
    date_cells=[coord for coord in cells(root) if coord.startswith('B') and (int(coord[1:])-4)%70 in (0,20,40,60)]
    for index in range(31):
        offset=index*70
        day=daylist[index] if index<len(daylist) else None
        writer.set(f'G{offset+2}',to_excel(datetime.combine(day,time()),**epoch) if day else None)
        for t,row in MONTH_ROWS.items():
            writer.set(f'C{offset+row}',(int(t[:2])*60+int(t[3:]))/1440)
            if day is None:
                for col in EXCEL_COLS.values():writer.set(f'{col}{offset+row}',None)
        for coord in date_cells:
            if offset+4<=int(coord[1:])<=offset+70:writer.set(coord,f'G{offset+2}' if day else None,formula=True)
    if not modern and mode=='continuation':
        for day in existing:
            for tc,v in day['counts'].items():
                t,c=tc.split('|');writer.set(month_cell(day['date'],t,c),v)
    accepted=[]
    for record in records:
        if record['date'] not in day_keys or record['time'] not in SCHEDULE or record['column_name'] not in COLUMNS:
            raise ValueError('Record outside layout/month')
        v=record['value'] if record['status']=='accepted' else None
        writer.set(month_cell(record['date'],record['time'],record['column_name']),v)
        if record['status']=='accepted':accepted.append(record)
    p[target]=xml(root)
    # A new-month copy must not show stale formula caches from its old data.
    for sheet,(_,path) in ss.items():
        if sheet in ('BLANK','PAPER') or sheet.startswith('DATA ENTRY - '):continue
        tree=parse(p[path])
        for formula in tree.findall('.//{'+S+'}f'):
            parent=formula.getparent(); cached=parent.find('{'+S+'}v')
            if cached is not None:parent.remove(cached)
        p[path]=xml(tree)
    covered={r['date']+'|'+r['time']+'|'+r['column_name'] for r in records}
    sourced={r['date'] for r in accepted if r.get('provenance')}
    missing=[d.isoformat() for d in daylist if d.isoformat() not in sourced]
    slots={d.isoformat():sum(d.isoformat()+'|'+t+'|'+c not in covered for t in SCHEDULE for c in COLUMNS) for d in daylist}
    draft=bool(issues or (any(slots.values()) and not coverage_ack))
    means={}
    lines=[['POOL IMPORT REPORT','NEEDS REVIEW' if draft else 'FINAL'],['Revision',revision],['Layout','Monthly blocks: Public, External, Internal, Dry'],['Mapping','Old User Group + Coaches -> Internal; absent External stays blank'],['Recalculation','Open in Excel; formula caches are not calculated by Python']]
    for d in missing:lines.append(['Missing day',d,'No source; acknowledged' if coverage_ack else 'Needs coverage acknowledgement'])
    for d,n in slots.items():
        if n:lines.append(['Unobserved cells',d,n])
    for issue in issues:lines.append(['Unresolved',issue.get('kind',''),issue.get('cell_key') or issue.get('source_id') or '',issue.get('detail','')])
    for src in source_report or []:lines.append(['Source',src['filename'],src['state'],src.get('assigned_date') or src.get('observed_date') or 'date unassigned',src['hash']])
    for t in SCHEDULE:
        for c in COLUMNS:
            nums=[r['value'] for r in accepted if r['time']==t and r['column_name']==c and r['value'] is not None]
            if nums:means[t+'|'+c]=sum(nums)/len(nums);lines.append(['Expected average',t,c,means[t+'|'+c]])
    reportpath=ss['IMPORT REPORT'][1] if 'IMPORT REPORT' in ss else add_sheet('IMPORT REPORT')
    p[reportpath]=report_sheet(lines)
    calc=wb.find('{'+S+'}calcPr')
    if calc is None:calc=E.SubElement(wb,'{'+S+'}calcPr')
    calc.set('fullCalcOnLoad','1');calc.set('forceFullCalc','1');calc.set('calcMode','auto')
    for r in list(rel):
        if r.get('Type','').endswith('/calcChain'):rel.remove(r)
    p.pop('xl/calcChain.xml',None)
    for x in list(types):
        if x.get('PartName')=='/xl/calcChain.xml':types.remove(x)
    views=wb.find('{'+S+'}bookViews')
    if views is None:
        views=E.Element('{'+S+'}bookViews');wb.insert(list(wb).index(container),views)
        E.SubElement(views,'{'+S+'}workbookView')
    for view in views:view.set('activeTab',str(next(i for i,s in enumerate(container) if s.get('name')==name)))
    p['xl/workbook.xml']=xml(wb);p['xl/_rels/workbook.xml.rels']=xml(rel);p['[Content_Types].xml']=xml(types)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for path,data in p.items():z.writestr(path,data)
    atomic_write(output,out.getvalue())
    # Verify the serialized output, rather than the in-memory cell values.
    written=cells(parse(parts(output)[target]))
    shared=strings(p)
    for r in records:
        expected=r['value'] if r['status']=='accepted' else None
        if value(written.get(month_cell(r['date'],r['time'],r['column_name'])),shared)!=expected:raise ValueError('Export value mismatch')
    return dict(draft=draft,missing_days=missing,missing_slots=slots,expected_averages=means,recalculated=False,layout='monthly',entry_sheet=name)
