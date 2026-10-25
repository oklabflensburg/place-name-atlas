"""Production PostGIS integration; never replace DB execution with fabricated values."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from sqlmodel import Session
from atlas import grid,service
from atlas.importer import import_bundle,publish
from atlas.schemas import Filter,Group,Pattern
from atlas.main import app


def selection():
    return Filter(dataset='synthetic-v1',groups=[Group(id=f'g{i}',title=v,patterns=[Pattern(value=v)])
        for i,v in enumerate(['ach','ingen','zell','heim','hausen','dorf','bach','itz','ow','by'])])


def test_batched_grid_counts_dedup_overlap_filters_and_names(db):
    import_bundle(Path('tests/fixtures/synthetic.json'),db);publish('synthetic-v1',db)
    client=TestClient(app);f=selection()
    def get(path,**kwargs):
        r=client.get(path,params={'q':f.model_dump_json(),**kwargs});assert r.status_code==200,r.text
        return r.json()
    v=get('/api/v1/grid/values');g=get('/api/v1/grid/geometry')
    assert v['grid']==g['grid']==grid.GRID
    assert g['crs']=='EPSG:3035' and g['cell_size']==20000 and g['origin']==[0,0]
    assert all(c['cx']==(int(c['id'].split('_')[0])+.5)*20000 and c['cy']==-(int(c['id'].split('_')[1])+.5)*20000 for c in g['cells'])
    assert v['denominator']==19
    assert v['totals'][0]==4 and v['totals'][6]==2
    assert sum(c['denominator'] for c in v['cells'])==19
    assert all(0<=n<=c['denominator'] for c in v['cells'] for n in c['counts'])
    assert set(c['id'] for c in v['cells'])<=set(c['id'] for c in g['cells'])
    assert any(c['id'] not in {v['id'] for v in v['cells']} for c in g['cells']) # no data
    target=next(c for c in v['cells'] if c['counts'][6])
    names=get(f"/api/v1/grid/cells/{target['id']}/places",group='g6',limit=1)
    assert names['count']==target['counts'][6] and names['denominator']==target['denominator']
    assert names['share']==names['count']/names['denominator']
    assert len(names['items'])==1
    f.kinds=['district'];f.regions=['state:01']
    filtered=get('/api/v1/grid/values')
    assert filtered['denominator']==7 and filtered['totals'][6]==1
    assert get('/api/v1/grid/geometry')['cells']==g['cells'] # fixed cells despite kind filter
    f.groups[6].patterns[0].value='no-such-ending'
    zero=get('/api/v1/grid/values');assert zero['denominator']==7 and zero['totals'][6]==0
    assert all(c['counts'][6]==0 for c in zero['cells'])


def test_variant_matches_count_once_and_ing_is_separate(db):
    import_bundle(Path('tests/fixtures/synthetic.json'),db);publish('synthetic-v1',db)
    f=selection();f.groups[0].patterns[0].value='ing'
    with Session(db) as s:
        d=service.dataset_for(s,f);v=grid.values(s,f,d)
        assert v.totals[:2]==[1,1]
        f.groups[0].patterns.append(Pattern(value='ingen'))
        assert grid.values(s,f,d).totals[:2]==[2,1]
        f.groups[0].patterns=[Pattern(value='by')]
        f.groups[0].patterns[0].value='by'
        v=grid.values(s,f,d)
        assert v.totals[0]==v.totals[9]==2 # Großby has matching variants; still once


def test_grid_rejects_bad_requests_and_unavailable_dataset(db):
    import_bundle(Path('tests/fixtures/synthetic.json'),db);publish('synthetic-v1',db)
    c=TestClient(app);f=selection()
    assert c.get('/api/v1/grid/cells/wrong/places',params={'q':f.model_dump_json(),'group':'g0'}).status_code==422
    f.dataset='unavailable'
    r=c.get('/api/v1/grid/values',params={'q':f.model_dump_json()})
    assert r.status_code==410 and r.headers['cache-control']=='no-store'


def test_exact_ten_of_forty_and_variant_deduplication(db,tmp_path):
    import copy
    b=json.loads(Path('tests/fixtures/synthetic.json').read_text())
    template=next(p for p in b['places'] if p['object_class']=='AX_Ortslage' and not p.get('virtual'))
    b['dataset']['id']='ratio-40';b['places']=[]
    for i in range(40):
        p=copy.deepcopy(template);p['source_id']=f'ratio-{i}';p['name']=f'Ort{i}'+('heim' if i<10 else 'dorf')
        p['alternatives']=[f'Variante{i}heim',f'Alias{i}heim'] if i<10 else []
        b['places'].append(p)
    path=tmp_path/'ratio.json';path.write_text(json.dumps(b))
    import_bundle(path,db);publish('ratio-40',db)
    f=selection();f.dataset='ratio-40'
    with Session(db) as s:
        v=grid.values(s,f,service.dataset_for(s,f))
        assert len(v.cells)==1 and v.cells[0].denominator==40
        assert v.cells[0].counts[3]==10
        page=grid.cell_places(s,f,service.dataset_for(s,f),v.cells[0].id,'g3',100,0)
        assert page.share==.25 and page.count==10 and len(page.items)==10
        assert len({p.id for p in page.items})==10
