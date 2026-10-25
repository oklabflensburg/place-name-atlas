import copy
import csv
import io
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session
from atlas.importer import import_bundle,publish
from atlas.main import app
from atlas.schemas import Filter,Group,Pattern
from atlas import service

FIXTURE=Path("tests/fixtures/synthetic.json")


def setup(db):
    report=import_bundle(FIXTURE,db);publish("synthetic-v1",db)
    return report


def query(pattern,mode="suffix",exclusions=None,dataset="synthetic-v1"):
    return Filter(dataset=dataset,groups=[Group(id="a",title="A",patterns=[Pattern(value=pattern,mode=mode)],
        exclusions=[Pattern(value=x,mode=mode) for x in exclusions or []])])


def names(db,f):
    with Session(db) as s:
        d=service.dataset_for(s,f)
        return [p.name for p in service.place_rows(s,f,d,100,0)]


def test_idempotency_and_report(db):
    r=setup(db)
    assert r["accepted"]==19
    assert r["excluded"]==3
    assert r["ambiguous_assignment"]==1
    assert r["missing_population"]==1
    assert import_bundle(FIXTURE,db)==r
    with db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM place_record")).scalar()==19
        assert c.execute(text("SELECT code FROM admin_area WHERE level='state'")).scalar()=="01"
        assert c.execute(text("SELECT count(*) FROM admin_area WHERE level='municipality'")).scalar()==2
        assert c.execute(text("SELECT sum(value) FROM population")).scalar()==1234
        assert c.execute(text("SELECT ST_NumGeometries(geom) FROM admin_area WHERE code='01001001'")).scalar()==2


@pytest.mark.parametrize("change",["geometry","dates","population","duplicate"])
def test_failed_import_preserves_active(db,tmp_path,change):
    setup(db)
    b=json.loads(FIXTURE.read_text());b["dataset"]["id"]="broken"
    if change=="geometry":b["places"][0]["geometry"]={"type":"Point","coordinates":[999,54]}
    elif change=="dates":b["population_geometry_date"]="2025-12-31"
    elif change=="duplicate":b["places"].append(b["places"][0])
    else:b["population"][0]["value"]=-1
    path=tmp_path/"broken.json";path.write_text(json.dumps(b))
    with pytest.raises(ValueError):import_bundle(path,db)
    with pytest.raises(ValueError):publish("broken",db)
    with db.connect() as c:
        assert c.execute(text("SELECT dataset_id FROM publication")).scalar()=="synthetic-v1"
        assert c.execute(text("SELECT count(*) FROM place_record WHERE dataset_id='broken'")).scalar()==0
        assert c.execute(text("SELECT report->>'status' FROM dataset WHERE id='broken'")).scalar()=="failed"


def test_ambiguous_population_prevents_publication(db,tmp_path):
    b=json.loads(FIXTURE.read_text());b["dataset"]["id"]="ambiguous-ew"
    b["population"].append(b["population"][0])
    path=tmp_path/"bundle.json";path.write_text(json.dumps(b))
    r=import_bundle(path,db)
    assert r["ambiguous_population"]==1
    with pytest.raises(ValueError):publish("ambiguous-ew",db)


def test_all_search_modes_and_unicode(db):
    setup(db)
    assert names(db,query("ing"))==["Testing"]
    assert names(db,query("ingen"))==["Testingen"]
    assert names(db,query("%","contains"))==["Dorf%heim"]
    assert names(db,query("_","contains"))==["Dorf_heim"]
    assert names(db,query("mühlen","prefix"))==["Mühlenbek"]
    assert names(db,query("groSSby","exact"))==["Grossby","Großby"]
    assert names(db,query("hausen"))==["Testhausen"]
    assert names(db,query("hausen (Nord)"))==["Testhausen (Nord)"]
    assert names(db,query("otter","contains"))==["OTTERDORF"]


def test_overlap_exclusion_and_population_meaning(db):
    setup(db)
    f=query("ach")
    f.groups.append(Group(id="b",title="B",patterns=[Pattern(value="bach")]))
    with Session(db) as s:
        d=service.dataset_for(s,f);stats=service.statistics(s,f,d)
        assert stats.denominator==19
        assert stats.total==4
        assert [g.count for g in stats.groups]==[4,2]
        assert stats.overlap==2
        assert stats.groups[0].municipality_population==1234
    assert names(db,query("ach",exclusions=["bach"]))==["Grenzach","Steinach"]
    with Session(db) as s:
        f=query("ingen");stats=service.statistics(s,f,service.dataset_for(s,f))
        assert stats.groups[0].municipality_population is None
        assert stats.groups[0].missing_population==1


def test_api_list_stat_export_tile_consistency(db):
    setup(db)
    client=TestClient(app)
    q=query("otter","contains").model_dump_json()
    params={"q":q}
    listed=client.get("/api/v1/places",params=params).json()
    stats=client.get("/api/v1/statistics",params=params).json()
    exported=client.get("/api/v1/export",params={**params,"format":"geojson"}).json()
    assert listed["total"]==stats["total"]==len(exported["features"])==1
    assert exported["features"][0]["id"]==listed["items"][0]["id"]
    assert exported["features"][0]["geometry"]["coordinates"]==[listed["items"][0]["longitude"],listed["items"][0]["latitude"]]
    assert client.get("/api/v1/tiles/0/0/0.mvt",params=params).content
    tile=client.get("/api/v1/tiles/0/0/0.mvt",params=params)
    assert tile.headers["x-representation"]=="aggregated"
    assert tile.headers["x-dataset-id"]=="synthetic-v1"
    assert client.get("/api/v1/tiles/0/0/0.mvt",params=params,headers={"If-None-Match":tile.headers["etag"]}).status_code==304
    assert client.get("/api/v1/tiles/0/1/0.mvt",params=params).status_code==422
    assert client.get("/api/v1/places",params={"q":'{"dataset":"gone"}'}).status_code==410
    assert client.get("/api/v1/places",params={"q":"not-json"}).status_code==422
    assert client.get("/api/v1/places/not-a-uuid",params=params).status_code==404
    missing=client.get('/api/v1/unknown-route')
    assert missing.status_code==404
    assert missing.json()['code']=='not_found'
    assert missing.json()['request_id']==missing.headers['x-request-id']
    assert client.get("/health/ready").status_code==200
    assert client.get("/api/v1/places",params={**params,"offset":100}).json()["items"]==[]
    formula=query("FORMULA","contains").model_dump_json()
    response=client.get("/api/v1/export",params={"q":formula,"format":"csv"})
    records=list(csv.DictReader(io.StringIO(response.text.lstrip('\ufeff'))))
    assert records[0]["name"]=="'=FORMULA()"


def test_region_and_kind_denominator(db):
    setup(db)
    f=query("bach");f.regions=["state:01"];f.kinds=["district"]
    with Session(db) as s:
        stats=service.statistics(s,f,service.dataset_for(s,f))
        assert stats.denominator==7
        assert stats.total==1
        assert stats.groups[0].municipality_population==1234


def test_stable_public_ids_between_versions(db,tmp_path):
    setup(db)
    before=names(db,query("Testbach","exact"))
    b=json.loads(FIXTURE.read_text());b["dataset"]["id"]="second-v1"
    path=tmp_path/"second.json";path.write_text(json.dumps(b));import_bundle(path,db);publish("second-v1",db)
    with db.connect() as c:
        assert c.execute(text("SELECT count(DISTINCT place_id) FROM place_record WHERE name='Testbach'")).scalar()==1
    assert names(db,query("Testbach","exact"))==before


def test_limits_and_cache_errors(db,monkeypatch):
    from atlas.config import settings
    setup(db)
    client=TestClient(app)
    monkeypatch.setattr(settings(),"export_limit",1)
    response=client.get('/api/v1/export',params={'q':'{"dataset":"synthetic-v1"}'})
    assert response.status_code==413
    assert response.headers['cache-control']=='no-store'
    monkeypatch.setattr(settings(),"tile_limit_bytes",1)
    response=client.get('/api/v1/tiles/0/0/0.mvt',params={'q':'{"dataset":"synthetic-v1"}'})
    assert response.status_code==413
    assert response.headers['cache-control']=='no-store'


def test_empty_municipality_selection_is_not_missing_data(db):
    setup(db)
    with Session(db) as s:
        f=query('nevermatches');stat=service.statistics(s,f,service.dataset_for(s,f))
        assert stat.groups[0].matched_municipalities==0
        assert stat.groups[0].missing_population==0
        assert stat.groups[0].municipality_population==0


def test_combining_marks_suffix_in_postgis(db,tmp_path):
    b=json.loads(FIXTURE.read_text())
    b['places'][0]['name']='Ortq\u0323\u0307'
    path=tmp_path/'unicode.json';path.write_text(json.dumps(b))
    import_bundle(path,db);publish('synthetic-v1',db)
    assert names(db,query('q\u0307\u0323'))==['Ortq\u0323\u0307']
