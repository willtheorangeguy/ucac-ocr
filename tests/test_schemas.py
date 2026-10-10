import pytest
from app.schemas import Reading, Extraction
from conftest import reading, result


def test_zero_blank_and_addition():
    assert Reading.model_validate(reading()).value==0
    r=Reading(raw_text='30 + 2 + 1',kind='sum',terms=[30,2,1],ambiguous=False,reason=None)
    assert r.value==33
    assert Reading(raw_text=None,kind='blank',terms=None,ambiguous=False,reason=None).value is None


@pytest.mark.parametrize('text,terms',[('30 - 2',[30,2]),('1 * 2',[1,2]),('30 + 2',[32]),('__import__("os")',[]),('-1',[-1]),('2.5',[2])])
def test_reject_expressions(text,terms):
    with pytest.raises(ValueError):Reading(raw_text=text,kind='sum',terms=terms,ambiguous=False,reason=None)


def test_alignment_missing_rows_rejected():
    with pytest.raises(ValueError):Extraction.model_validate(result(['05:30'])).check(['05:15','05:30'])


def test_arrow_is_copy_marker_in_detailed_mode():
    r=Reading(raw_text='→',kind='unclear',terms=None,ambiguous=True,reason=None)
    assert r.kind=='carry' and r.terms is None


def test_equivalence_compares_terms_not_explanations():
    from app.schemas import equivalent
    a=reading();b={**a,'reason':'Different clear reading explanation'}
    assert equivalent(a,b)
    assert not equivalent(a,{**b,'kind':'sum','terms':[0,0]})
