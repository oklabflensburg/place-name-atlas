import pytest
from pydantic import ValidationError
from atlas.schemas import Filter, Pattern, Group, normalize
from atlas.main import csv_safe
from atlas.service import matches
from atlas.search import compile_filter


def test_unicode():
    import unicodedata
    assert unicodedata.unidata_version=="15.1.0"
    assert normalize("MÜHLENBEK")==normalize("Mu\u0308hlenbek")
    assert normalize("Mühlenbek")!=normalize("Muehlenbek")
    assert normalize("Großby")==normalize("Grossby")


def test_literal_and_parameterized():
    f=Filter(groups=[Group(id="a",title="a",patterns=[Pattern(mode="contains",value="%'_\\")])])
    _,where,_,params=compile_filter(f,"v1")
    assert "%'_" not in where
    assert params["g0_p0"]=="%\\%'\\_\\\\%"


def test_suffix_reversal_does_not_reorder_combining_marks():
    value='q\u0323\u0307'
    f=Filter(groups=[Group(id='a',title='a',patterns=[Pattern(value=value)])])
    _,_,_,params=compile_filter(f,'v1')
    assert params['g0_p0']==normalize(value)[::-1]+'%'


@pytest.mark.parametrize("value",["", "   ","a\x00b","x"*81])
def test_invalid_patterns(value):
    with pytest.raises(ValidationError):
        Pattern(value=value)


@pytest.mark.parametrize("bbox",[(180,1,0,2),(0,-90,1,90),(0,1,float('inf'),2)])
def test_invalid_bbox(bbox):
    with pytest.raises(ValidationError):Filter(bbox=bbox)


def test_match_reason_and_exclusion_across_variants():
    f=Filter(groups=[Group(id="a",title="a",patterns=[Pattern(value="ach")],exclusions=[Pattern(value="bach")])])
    assert not matches("Steinach",["Steinbach"],f)


def test_sted_and_stedt_are_separate_suffixes_with_explicit_alternative_matches():
    f=Filter(groups=[Group(id='g25',title='-sted',patterns=[Pattern(value='sted')])])
    assert not matches('Borgstedt',[],f)
    assert not matches('Borgstedthof',[],f)
    assert [m.model_dump() for m in matches('Borgstedt',['Borgsted'],f)] == [
        dict(group='g25',name='Borgsted',mode='suffix',pattern='sted')]
    _,_,_,params=compile_filter(f,'bkg-2024-r3')
    assert params['g0_p0']=='dets%'
    f.groups[0].patterns=[Pattern(value='stedt')]
    assert [m.name for m in matches('Borgstedt',['Borgsted'],f)] == ['Borgstedt']


@pytest.mark.parametrize("value",["=1+1"," +SUM(A1)","@cmd","-1","\t=cmd","\ttext","\rtext","\ntext"])
def test_csv_formula_protection(value):
    assert csv_safe(value).startswith("'")
