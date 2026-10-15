from datetime import date
import calendar

COLUMNS = ('public', 'group', 'dry', 'external')
# Keep the stored "group" key compatible with existing jobs: it means Internal.
EXCEL_COLS = dict(public='D', external='E', group='F', dry='G')
LEGACY_EXCEL_COLS = dict(public='C', group='D', dry='E')
SCHEDULE = {f'{m//60:02}:{m%60:02}': 10 + i*2 for i,m in enumerate(range(315,766,15))}
SCHEDULE.update({f'{m//60:02}:{m%60:02}': 78 + i*2 for i,m in enumerate(range(780,1306,15))})
MORNING = list(SCHEDULE)[:31]
AFTERNOON = list(SCHEDULE)[31:]
MONTH_ROWS = {t: 4+i for i,t in enumerate(SCHEDULE)}


def month_cell(day, time, column):
    return EXCEL_COLS[column]+str((date.fromisoformat(day).day-1)*70+MONTH_ROWS[time])


def dates(year, month):
    return [date(year,month,d) for d in range(1,calendar.monthrange(year,month)[1]+1)]


def key(day, time, column):
    return f'{day}|{time}|{column}'
