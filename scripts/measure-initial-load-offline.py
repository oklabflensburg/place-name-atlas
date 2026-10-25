"""Compare stored display boundaries with the previous on-demand expression.

Uses real VG25 state boundaries in a disposable postgres --single cluster. Each
sample includes process startup, SQL and decoding, with an empty application
cache and uncontrolled OS caches. These are not HTTP or browser timings.
"""
import argparse
import importlib.util
import json
import sqlite3
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

from atlas import grid
from atlas.bkg import features
from atlas.schemas import Filter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('data/vg25/daten/DE_VG25.gpkg'))
    parser.add_argument('--report', type=Path, default=Path('artifacts/initial-load-geometry.json'))
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error('Der lokale VG25-Bestand fehlt.')
    spec = importlib.util.spec_from_file_location('offline', Path(__file__).with_name('check-grid-offline.py'))
    offline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(offline)
    db = offline.Offline()
    original_rows = grid.rows
    dataset = SimpleNamespace(id='bkg-2024-r3', fingerprint='geometry-measurement')
    try:
        db.run('''CREATE EXTENSION postgis;
            CREATE TABLE admin_area (dataset_id text, identity_id text PRIMARY KEY, code text,
                level text, geom geometry(MultiPolygon,4326));
            CREATE INDEX admin_geom ON admin_area USING gist(geom);
            CREATE INDEX admin_dataset_code ON admin_area(dataset_id,level,code)''')
        statements = []
        for feature in features(args.source, 'vg25_lan', where='BSG = 1'):
            props = {k.upper(): v for k, v in feature['properties'].items()}
            values = [dataset.id, 'state:'+props['AGS'], props['AGS'], 'state']
            statements.append('INSERT INTO admin_area VALUES('+','.join(map(offline.quote, values))+
                ',ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON('+offline.quote(json.dumps(feature['geometry']))+
                '),4326))) ON CONFLICT(identity_id) DO UPDATE SET geom=ST_Multi(ST_UnaryUnion(ST_Collect(admin_area.geom,excluded.geom)))')
        db.run(';'.join(statements)+'; ANALYZE admin_area')
        spec = importlib.util.spec_from_file_location('migration', Path(__file__).resolve().parents[1]/
            'apps/api/migrations/versions/0003_display_geometry.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.op = SimpleNamespace(execute=db.run)
        migration.upgrade()
        report = {'method': __doc__, 'cases': {}}
        cases = [('germany', {}), ('schleswig-holstein', {'regions': ['state:01']}),
            ('two-states', {'regions': ['state:01', 'state:02']}),
            ('bbox', {'bbox': (8.5, 53.5, 10.5, 55.0)}),
            ('state-and-bbox', {'regions': ['state:01'], 'bbox': (9.0, 54.0, 10.5, 55.0)})]
        for case, changes in cases:
            selection = Filter(dataset=dataset.id, **changes)
            results = {}; samples = {'before': [], 'after': []}
            for _ in range(5):
                for label in samples:
                    def execute(s, sql, params):
                        if label == 'before':
                            sql = sql.replace('SELECT display_geom g',
                                'SELECT ST_SimplifyPreserveTopology(ST_Transform(geom,3035),150) g')
                        return db.run(sql, params)
                    grid.rows = execute
                    grid._cache.clear()
                    start = time.perf_counter()
                    result = grid.geometry(None, selection, dataset)
                    samples[label].append((time.perf_counter()-start)*1000)
                    results[label] = result.model_dump()
                    assert results[label] == results['before'], case+' changed geometry'
            record = {label: {'ms': values, 'median_ms': statistics.median(values)} for label, values in samples.items()}
            record.update(cells=len(result.cells), bytes=len(result.model_dump_json().encode()), identical_response=True)
            report['cases'][case] = record
            print(json.dumps({case: record}), flush=True)
        # A generated column also follows source changes and needs no refresh.
        db.run("UPDATE admin_area SET geom=ST_Translate(geom,0.001,0) WHERE identity_id='state:02'")
        updated = db.run('''SELECT ST_Equals(display_geom,
            ST_SimplifyPreserveTopology(ST_Transform(geom,3035),150)) valid
            FROM admin_area WHERE identity_id='state:02' ''', {})[0]
        assert updated['valid'], updated
        report['generated_column_tracks_updates'] = True
        with sqlite3.connect(f'file:{args.source}?mode=ro', uri=True) as connection:
            labels = {level: connection.execute(f'SELECT count(DISTINCT AGS) FROM vg25_{layer} WHERE BSG=1').fetchone()[0]
                for level, layer in [('state', 'lan'), ('district', 'krs'), ('municipality', 'gem')]}
        report['region_choices'] = {'all': sum(labels.values()), 'overview': labels['state']+labels['district'], 'levels': labels}
        migration.downgrade()
        migration.upgrade()
        report['migration_round_trip'] = True
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    finally:
        grid.rows = original_rows
        grid._cache.clear()
        db.temp.cleanup()


if __name__ == '__main__':
    main()
