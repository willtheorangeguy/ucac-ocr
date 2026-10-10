import re
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .layout import COLUMNS
from .config import settings
from .count_text import numeric_text, OCR_DIGITS, is_carry_mark, likely_blank


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Reading(Strict):
    raw_text: str | None
    kind: Literal['blank','integer','sum','unclear','carry']
    terms: list[int] | None
    ambiguous: bool
    reason: str | None

    @model_validator(mode='after')
    def validate_ink(self):
        if is_carry_mark(self.raw_text,self.reason):
            self.kind='carry';self.terms=None;self.ambiguous=False
            return self
        if settings.rough_counts and likely_blank(self.raw_text,self.kind,self.reason):
            self.kind='blank';self.terms=None;self.ambiguous=False
            return self
        normalized=numeric_text(self.raw_text)
        numeric=normalized is not None
        substituted=numeric and any(c in OCR_DIGITS for c in (self.raw_text or ''))
        if numeric and (settings.rough_counts or substituted):
            # Preserve the visible text; calculate from local normalized terms.
            self.kind='sum' if '+' in normalized else 'integer'
            self.terms=[int(t.strip()) for t in normalized.split('+')]
            if substituted:
                self.ambiguous=False
                marker='Count characters normalized to '+normalized
                if marker not in (self.reason or ''):self.reason=((self.reason+'; ') if self.reason else '')+marker
            if any(t>1_000_000_000 for t in self.terms):raise ValueError('Count exceeds integer limit')
            return self
        if settings.rough_counts:
            if self.raw_text in (None,'') and self.kind=='blank':self.terms=None
            elif not numeric:
                self.kind='unclear';self.terms=None;self.ambiguous=True
                self.reason=self.reason or 'No readable numeric count'
                return self
        if self.kind == 'blank':
            if self.raw_text not in (None,'') or self.terms not in (None,[]):
                raise ValueError('Blank must have no visible text or terms')
        elif self.kind in ('integer','sum'):
            pattern = r'\d+' if self.kind == 'integer' else r'\d+(?:\s*\+\s*\d+)+'
            if not numeric or not re.fullmatch(pattern,normalized,flags=re.ASCII):
                raise ValueError('Only nonnegative integer addition is supported')
            parsed = [int(t.strip()) for t in normalized.split('+')]
            if parsed != self.terms or any(t<0 or t>1_000_000_000 for t in parsed):
                raise ValueError('Terms do not match ink')
        elif self.terms is not None:
            raise ValueError('Unclear ink cannot supply terms')
        return self

    @property
    def value(self):
        return sum(self.terms) if self.kind in ('integer','sum') and (settings.rough_counts or not self.ambiguous) else None


class Row(Strict):
    time: str
    public: Reading
    group: Reading
    dry: Reading


class Extraction(Strict):
    date: str | None
    section: Literal['morning','afternoon','both','unknown']
    ambiguous: bool
    reason: str | None
    rows: list[Row]

    def check(self, expected):
        if [r.time for r in self.rows] != expected:
            raise ValueError('Missing, duplicate, unexpected or shifted rows')
        if self.date is not None:
            date.fromisoformat(self.date)
        return self


class Header(Strict):
    date: str | None
    section: Literal['morning','afternoon','both','unknown']
    ambiguous: bool
    reason: str | None
    rows: list[None] = Field(max_length=0)


class QuickRow(Strict):
    time: str
    public: str | int | None
    group: str | int | None
    dry: str | int | None


class QuickExtraction(Strict):
    rows: list[QuickRow]

    def expand(self):
        def read(raw):
            if isinstance(raw,int):raw=str(raw)
            return Reading(raw_text=raw,kind='blank' if raw is None or raw=='' else 'unclear',
                           terms=None,ambiguous=False,reason=None)
        return Extraction(date=None,section='unknown',ambiguous=False,reason=None,
            rows=[Row(time=r.time,public=read(r.public),group=read(r.group),dry=read(r.dry)) for r in self.rows])


def equivalent(a,b):
    # Explanations and whitespace are audit text, not different count readings.
    return all(a[k]==b[k] for k in ('kind','terms','ambiguous'))
