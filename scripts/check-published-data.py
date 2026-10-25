"""Read-only audit of the actual published local BKG snapshot against fixed source totals."""
import json
import sqlite3
from pathlib import Path
from sqlalchemy import create_engine,text

engine=create_engine('postgresql+psycopg://atlas_runtime@127.0.0.1:55439/atlas_dev')
with engine.connect() as c:
    dataset=c.execute(text('SELECT d.* FROM dataset d JOIN publication p ON p.dataset_id=d.id WHERE p.id=1')).mappings().one()
    identifier=dataset['id'];params={'d':identifier}
    def grouped(table,column):
        return dict(c.execute(text(f'SELECT {column},count(*) FROM {table} WHERE dataset_id=:d GROUP BY {column} ORDER BY {column}'),params).all())
    places=c.execute(text('SELECT count(*) FROM place_record WHERE dataset_id=:d'),params).scalar_one()
    pop=c.execute(text('SELECT count(*) units,count(value) known_values,sum(value) total FROM population WHERE dataset_id=:d'),params).mappings().one()
    assert places==dataset['report']['accepted']
    result={'dataset':identifier,'fingerprint':dataset['fingerprint'],'geometry_date':dataset['geometry_date'],
        'population_date':dataset['population_date'],'places':places,'areas':grouped('admin_area','level'),
        'kinds':grouped('place_record','kind'),'assignments':grouped('place_record','assignment'),
        'population':{**dict(pop),'total':int(pop['total']) if pop['total'] is not None else None}}
manifest_path=Path('data/manifest-r3.json');manifest=json.loads(manifest_path.read_text())
ew=next(s for s in manifest['sources'] if s['product']=='VG250-EW')
with sqlite3.connect(manifest_path.parent/ew['path']) as c:
    expected=c.execute('SELECT count(*),sum(EWZ) FROM vg250_gem WHERE GF=4').fetchone()
assert (pop['units'],pop['total'])==expected
result['source_population_count_and_total_verified']=True
Path('artifacts/dataset-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
