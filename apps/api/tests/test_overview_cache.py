from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from atlas import grid
from atlas.schemas import Filter,Group,Pattern,GridHit


def test_singleflight_and_failed_build_is_retryable():
    entered=Event();release=Event();calls=[]
    key=('test-singleflight',)
    grid._cache.clear()
    def build():
        calls.append(1);entered.set();assert release.wait(2)
        return GridHit(group='g',total=0,cells=[])
    with ThreadPoolExecutor(2) as pool:
        a=pool.submit(grid.cached,key,build);assert entered.wait(2)
        b=pool.submit(grid.cached,key,build);release.set()
        assert a.result() is b.result()
    assert len(calls)==1
    grid._cache.clear()
    def broken():raise RuntimeError('retryable')
    try:grid.cached(key,broken)
    except RuntimeError:pass
    else:raise AssertionError('failure must not become zero hits')
    assert grid.cached(key,lambda:GridHit(group='g',total=1,cells=[])).total==1


def test_selection_and_suffix_cache_reuse_and_full_keys(monkeypatch):
    grid._cache.clear();calls=[]
    d=SimpleNamespace(id='d',fingerprint='one')
    f=Filter(dataset='d',groups=[Group(id='g0',title='ach',patterns=[Pattern(value='ach')])])
    def rows(s,sql,params):
        calls.append((sql,params))
        if 'jsonb_object_agg' in sql:return [{'records':{'a':'1_2','b':'1_2'}}]
        return [{'group_index':0,'id':'a'}]
    monkeypatch.setattr(grid,'rows',rows)
    initial=grid.values(None,f,d)
    assert initial.denominator==2 and initial.totals==[1] and initial.cells[0].counts==[1]
    assert len(calls)==2
    f.groups[0].patterns[0].value='ACH';f.groups[0].id='renamed'
    assert grid.counts(None,f,d).groups[0].group=='renamed'
    assert len(calls)==2
    f.groups[0].patterns[0].value='bek'
    assert grid.values(None,f,d).denominator==2
    assert len(calls)==3  # no new denominator or spatial selection
    assert 'ST_' not in calls[-1][0] and 'grid_x' not in calls[-1][0]
    assert 'count(*) FILTER' not in calls[-1][0]
    f.groups[0].exclusions=[Pattern(value='x')]
    grid.counts(None,f,d);assert len(calls)==4
    f.kinds=['district'];grid.counts(None,f,d);assert len(calls)==6
    d.fingerprint='two';grid.counts(None,f,d);assert len(calls)==8
    f.regions=['state:01'];grid.counts(None,f,d);assert len(calls)==10


def test_lru_is_bounded_even_with_many_arbitrary_endings(monkeypatch):
    grid._cache.clear();monkeypatch.setattr(grid,'_CACHE_BYTES',1200)
    for i in range(50):grid.cached(('ending',i),lambda:GridHit(group='g',total=0,cells=[]))
    assert sum(size for _,size in grid._cache.values())<=1200
    assert len(grid._cache)<50
