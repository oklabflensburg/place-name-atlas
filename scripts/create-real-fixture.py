"""Derive a small, explicitly simplified Flensburg fixture from the checked BKG sources."""
import getpass
import json
import os
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from atlas.bkg import prepare

manifest=json.loads(Path('data/manifest.json').read_text())
manifest.update(id='bkg-2024-flensburg-fixture-v1',label='BKG · Prüfausschnitt Flensburg · 2024',scope='Realer Prüfausschnitt Flensburg',municipalities=['01001000'])
path=Path('data/manifest-flensburg.json');path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
destination=Path('data/flensburg-source.json')
if not destination.exists():prepare(path,destination)
bundle=json.loads(destination.read_text())
admin=os.getenv('TEST_ADMIN_URL',f'postgresql://{getpass.getuser()}@127.0.0.1:55439/postgres')
with psycopg.connect(make_conninfo(**{**conninfo_to_dict(admin),'dbname':'atlas_dev'})) as c:
    for area in bundle['areas']:
        tolerance=.01 if area['level']=='state' else .00005
        geometry=c.execute("SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s),15)",(json.dumps(area['geometry']),tolerance)).fetchone()[0]
        area['geometry']=json.loads(geometry)
bundle['fixture_modifications']={'selection':'GN250 AGS=01001000; VG25 parent state/district and municipality; VG250-EW AGS=01001000',
    'simplification':'ST_SimplifyPreserveTopology in EPSG:4326: state 0.01°, district/municipality 0.00005°; production uses unsimplified geometry',
    'expected_names':sorted(p['name'] for p in bundle['places'] if p['object_class']=='AX_Ortslage' and not p['virtual']),
    'expected_municipality_population':next(p['value'] for p in bundle['population'] if p['gf']==4)}
target=Path('tests/fixtures/bkg-2024-flensburg.json');target.write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'fixture':str(target),'bytes':target.stat().st_size,'names':bundle['fixture_modifications']['expected_names']}))
