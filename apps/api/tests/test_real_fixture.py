"""Expected values derived from the fixed, attributed BKG excerpt, not guessed."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import text
from atlas.importer import import_bundle,publish
from atlas.main import app

FIXTURE=Path('tests/fixtures/bkg-2024-flensburg.json')


def test_real_flensburg_end_to_end(db):
    bundle=json.loads(FIXTURE.read_text())
    identifier=bundle['dataset']['id']
    report=import_bundle(FIXTURE,db)
    assert report['source_objects']==12
    assert report['accepted']==9
    assert report['excluded']==3
    assert report['missing_population']==report['ambiguous_population']==0
    assert import_bundle(FIXTURE,db)==report
    publish(identifier,db)
    client=TestClient(app)
    q=json.dumps({'dataset':identifier})
    listed=client.get('/api/v1/places',params={'q':q}).json()
    expected=bundle['fixture_modifications']['expected_names']
    assert listed['total']==9
    assert sorted(p['name'] for p in listed['items'])==expected
    with db.connect() as c:
        assert c.execute(text("SELECT sum(value) FROM population")).scalar()==96326
        assert c.execute(text("SELECT count(*) FROM admin_area")).scalar()==3
        assert c.execute(text("SELECT code FROM admin_area WHERE level='municipality'")).scalar()=='01001000'
    q=json.dumps({'dataset':identifier,'groups':[{'id':'a','title':'Flensborg',
        'patterns':[{'mode':'exact','value':'Flensborg'}]}]})
    flensburg=client.get('/api/v1/places',params={'q':q}).json()
    stat=client.get('/api/v1/statistics',params={'q':q}).json()
    export=client.get('/api/v1/export',params={'q':q,'format':'geojson'}).json()
    assert flensburg['total']==stat['total']==len(export['features'])==1
    place=flensburg['items'][0]
    assert place['name']=='Flensburg'
    assert place['municipality']['population']==96326
    detail=client.get('/api/v1/places/'+place['id'],params={'q':q})
    assert detail.status_code==200
    assert detail.json()['matches'][0]['name']=='Flensborg'
    assert client.get('/api/v1/tiles/0/0/0.mvt',params={'q':q}).content
    # Administrative own-name population does not match the settlement's alternative name.
    assert stat['groups'][0]['matched_municipalities']==0
