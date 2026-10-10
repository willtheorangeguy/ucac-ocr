import zipfile
import copy
from pathlib import Path
from openpyxl import load_workbook
from app.workbook import generate, validate_template, parts, sheets, parse, S
from app.layout import SCHEDULE

TEMPLATE=Path(__file__).parent/'fixtures/Head Counts.xlsx'


def record(day,t,col,val):
    return dict(date=day,time=t,column_name=col,value=val,status='accepted',provenance='synthetic')


def test_actual_fixture_month_and_fidelity(tmp_path):
    assert validate_template(TEMPLATE)[0]['date']=='2026-09-09'
    records=[record('2026-10-09',t,c,0 if c=='public' else (32 if c=='group' else None)) for t in SCHEDULE for c in ('public','group','dry')]
    out=tmp_path/'October.xlsx'
    report=generate(TEMPLATE,out,2026,10,records,[],1)
    assert report['draft']
    wb=load_workbook(out,read_only=True)
    assert len(wb.sheetnames)==35
    assert wb.sheetnames[2:4]==['October 1','October 2']
    assert wb.sheetnames[-2:]==['Boundary B','IMPORT REPORT']
    assert wb['October 9']['E3'].value.year==2026
    assert wb['October 9']['E3'].value.month==10
    assert wb['MASTER']['C10'].value=='=IFERROR(AVERAGE(\'October 1:Boundary B\'!C10),"")'
    assert wb['Boundary B'].sheet_state=='hidden'
    daily=wb['October 9']
    loaded={c.coordinate:c.value for row in daily.iter_rows() for c in row if hasattr(c,'coordinate')}
    for t,row in SCHEDULE.items():
        assert loaded[f'C{row}']==0
        assert loaded[f'D{row}']==32
        assert loaded.get(f'E{row}') is None
    p=parts(TEMPLATE); q=parts(out)
    for name,data in p.items():
        if '/drawings/' in name or '/media/' in name or '/printerSettings/' in name:
            assert q[name]==data
    exported,_,ss=sheets(q)
    blank=parse(p['xl/worksheets/sheet1.xml']); cloned=parse(q[ss['October 9'][1]])
    changed={'E3'}|{f'{c}{r}' for c in 'CDE' for r in SCHEDULE.values()}
    for c in blank.findall('.//{'+S+'}c'):
        if c.get('r') in changed:
            target=cloned.find('.//{'+S+'}c[@r="'+c.get('r')+'"]');target.getparent().replace(target,copy.deepcopy(c))
    from lxml import etree
    # Entire sheet is identical after restoring only the permitted inputs/date:
    # merges, styles, dimensions, formulas, print setup, margins, and drawing refs.
    assert etree.tostring(cloned,method='c14n')==etree.tostring(blank,method='c14n')
    names=exported.find('{'+S+'}definedNames')
    assert any(n.text=="'October 9'!$B$1:$H$149" for n in names)
    relpath='xl/worksheets/_rels/'+ss['October 9'][1].split('/')[-1]+'.rels'
    assert q[relpath]==p['xl/worksheets/_rels/sheet1.xml.rels']
    wb.close()


def test_leap_year_blanks_zeros_averages(tmp_path):
    out=tmp_path/'February.xlsx'
    report=generate(TEMPLATE,out,2024,2,[record('2024-02-01','05:15','public',0),record('2024-02-02','05:15','public',32),record('2024-02-03','05:15','public',None)],[],2,coverage_ack=True)
    wb=load_workbook(out,read_only=True)
    assert 'February 29' in wb.sheetnames
    assert not report['draft']
    assert report['expected_averages']['05:15|public']==16
    assert wb['February 3']['C10'].value is None
    wb.close()
