from datetime import date
import calendar

COLUMNS = ('public', 'group', 'dry')
EXCEL_COLS = dict(zip(COLUMNS, 'CDE'))
SCHEDULE = {f'{m//60:02}:{m%60:02}': 10 + i*2 for i,m in enumerate(range(315,766,15))}
SCHEDULE.update({f'{m//60:02}:{m%60:02}': 78 + i*2 for i,m in enumerate(range(780,1306,15))})
MORNING = list(SCHEDULE)[:31]
AFTERNOON = list(SCHEDULE)[31:]


def dates(year, month):
    return [date(year,month,d) for d in range(1,calendar.monthrange(year,month)[1]+1)]


def key(day, time, column):
    return f'{day}|{time}|{column}'
