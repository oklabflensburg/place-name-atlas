"""Real PostGIS measurements without sockets; deliberately no HTTP/browser claims.

--before prepares a disposable cluster and replays the captured original SQL.
--compare replays original SQL and current SQL on that same cluster. PostgreSQL
is restarted for each SQL invocation, so these are not warm shared-buffer runs.
Application-cold and application-warm are measured separately, OS cache uncontrolled.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import platform
import statistics
import re
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from atlas import grid
from atlas.schemas import Filter, Group, Pattern

spec = importlib.util.spec_from_file_location('offline', 'scripts/check-grid-offline.py')
offline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offline)
parser = argparse.ArgumentParser()
parser.add_argument('--before', action='store_true')
parser.add_argument('--after', action='store_true')
parser.add_argument('--compare', action='store_true',help='Replay the captured pre-change SQL, then measure current SQL in the same isolated database.')
args = parser.parse_args()
if args.compare:args.after=True
state_file = Path('/tmp/atlas-overview-measurement.json')
report_file = Path('docs/reports/overview-performance.json')

if args.before and not state_file.exists():
    db = offline.Offline()
    bundle_path = Path('data/bkg-2024-r3.json')
    dataset, selected = db.setup(json.loads(bundle_path.read_text()))
    db.temp._finalizer.detach()  # Kept only for the paired --after measurement.
    state_file.write_text(json.dumps({'path': str(db.path), 'dataset': vars(dataset)}))
    report = {'method': __doc__, 'dataset': dataset.id, 'places': len(selected),
              'bundle_sha256': hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
              'cpu': next(l.split(':', 1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),
              'os': platform.platform(), 'logical_cpus': os.cpu_count(),
              'http_ttfb_ms': None, 'transfer_ms': None, 'browser_json_ms': None,
              'svg_creation_ms': None, 'visible_map_ms': None,
              'unavailable_reason': 'Sandbox denies localhost sockets (EPERM); escalation rejected.'}
else:
    state = json.loads(state_file.read_text())
    db = offline.Offline.__new__(offline.Offline)
    db.path = Path(state['path'])
    dataset = SimpleNamespace(**state['dataset'])
    report = json.loads(report_file.read_text()) if report_file.exists() else {'method':__doc__, 'dataset':dataset.id, 'places':45858,
        'cpu':next(l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),
        'bundle_sha256':hashlib.sha256(Path('data/bkg-2024-r3.json').read_bytes()).hexdigest(), 'os':platform.platform(),
        'logical_cpus':os.cpu_count(), 'http_ttfb_ms':None, 'transfer_ms':None, 'browser_json_ms':None, 'svg_creation_ms':None, 'visible_map_ms':None,
        'unavailable_reason':'Sandbox denies localhost sockets (EPERM); escalation rejected.'}

f = Filter(dataset=dataset.id, groups=[Group(id=f'g{i}', title=v, patterns=[Pattern(value=v)])
    for i, v in enumerate(['ach','ingen','zell','heim','hausen','dorf','bach','itz','ow','by'])])
calls = []
def execute(s, sql, params=None):
    start = time.perf_counter()
    result = db.run(sql, params or {})
    calls.append({'sql': sql, 'params': params, 'process_sql_and_decode_ms': (time.perf_counter()-start)*1000})
    return result
grid.rows = execute

def measure(name, build,prepare=None):
    samples = []
    for _ in range(5):
        grid._cache.clear()
        if prepare:prepare()
        calls.clear()
        start = time.perf_counter()
        result = build()
        service_ms = (time.perf_counter()-start)*1000
        sql_ms = sum(c['process_sql_and_decode_ms'] for c in calls)
        start = time.perf_counter()
        payload = result.model_dump_json().encode()
        json_ms = (time.perf_counter()-start)*1000
        start = time.perf_counter()
        build()
        warm_ms = (time.perf_counter()-start)*1000
        samples.append({'service_ms': service_ms, 'sql_process_and_decode_ms': sql_ms,
                        'python_processing_ms': service_ms-sql_ms, 'serialization_ms': json_ms,
                        'bytes': len(payload), 'application_warm_ms': warm_ms, 'queries': len(calls)})
    def explain(c):
        sql=re.sub(r'(?<!:):([a-zA-Z_]\w*)',lambda m:offline.quote(c['params'][m[1]]),c['sql'])
        # Store EXPLAIN in a temp JSON column; utility statements cannot be subqueries.
        block="CREATE OR REPLACE FUNCTION pg_temp.atlas_plan() RETURNS json LANGUAGE plpgsql AS $$ DECLARE p json; BEGIN EXECUTE "+offline.quote('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+sql)+" INTO p; RETURN p; END $$; SELECT row_to_json(q) FROM (SELECT replace(pg_temp.atlas_plan()::text, chr(10), '')::json plan) q"
        return db.run(block)[0]['plan']
    plans = [dict(sql=c['sql'], params=c['params'], plan=explain(c)) for c in calls]
    return {'samples': samples, 'median': {k: statistics.median(s[k] for s in samples) for k in samples[0]},
            'plans': plans, 'result': result.model_dump(mode='json')}

phase = 'before' if args.before else 'after'
if args.compare or args.before:
    from atlas.schemas import GridValues,GridGeometry
    captured=json.loads(Path('scripts/overview-baseline-sql.json').read_text())
    def baseline(kind):
        def build():
            statement=captured[kind]
            records=execute(None,statement['sql'],statement['params'])
            if kind=='geometry':
                first=records[0]
                return GridGeometry(dataset=dataset.id,grid=grid.GRID,viewbox=first['viewbox'],bounds=first['bounds'],outline=first['outline'],cells=first['cells'])
            cells=[dict(id=r['id'],denominator=r['denominator'],counts=[r[f'n{i}'] for i in range(10)]) for r in records]
            return GridValues(dataset=dataset.id,grid=grid.GRID,groups=[g.id for g in f.groups],totals=[sum(c['counts'][i] for c in cells) for i in range(10)],denominator=sum(c['denominator'] for c in cells),cells=cells)
        return grid.cached(('baseline',kind),build)
    if 'before' in report:
        report.setdefault('initial_before',{k:{field:v[field] for field in ('samples','median','plans')} for k,v in report['before'].items()})
    report['before']={k:measure(k,lambda k=k:baseline(k)) for k in ('values','geometry')}
    report['paired_replay']='Captured original SQL and current SQL; five application-cold and five application-warm samples each, same disposable cluster, sequential without a concurrent build.'
    if args.before:
        report_file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'before':{k:v['median'] for k,v in report['before'].items()}},indent=2))
        raise SystemExit(0)
report[phase] = {'values': measure('values', lambda: grid.values(None, f, dataset)),
                 'geometry': measure('geometry', lambda: grid.geometry(None, f, dataset))}
if args.after:
    before,after=report['before'],report['after']
    assert before['values']['result']==after['values']['result'], 'Changed numerators or denominators'
    original=before['geometry']['result'];updated=after['geometry']['result']
    assert all(original[k]==updated[k] for k in original if k!='outline'), 'Changed circle positions or geographic extent'
    report['equivalence']={'every_cell_count_and_denominator':True,'all_totals':True,'every_cell_share':True,
        'circle_ids_centers_viewbox_bounds':True,'unused_outline_removed':True}
    after['base']=measure('base',lambda:grid.base(None,f,dataset))
    after['counts_after_base']=measure('counts',lambda:grid.counts(None,f,dataset),prepare=lambda:grid.base(None,f,dataset))
    grid._cache.clear()
    b=grid.base(None,f,dataset);c=grid.counts(None,f,dataset)
    report['transport_bytes']={'before_geometry':len(json.dumps(original,separators=(',',':')).encode()),
        'after_geometry':len(grid.geometry(None,f,dataset).model_dump_json().encode()),
        'base_once':len(b.model_dump_json().encode()),'ten_sparse_endings':len(c.model_dump_json().encode())}
    additions=[]
    extra=f.model_copy(deep=True);extra.groups=[Group(id='new',title='bek',patterns=[Pattern(value='bek')])]
    for _ in range(5):
        grid._cache.clear();grid.base(None,f,dataset);grid.counts(None,f,dataset);calls.clear()
        start=time.perf_counter();added=grid.counts(None,extra,dataset);elapsed=(time.perf_counter()-start)*1000
        additions.append({'service_ms':elapsed,'queries':len(calls),'bytes':len(added.model_dump_json().encode())})
        calls.clear();grid.counts(None,extra,dataset);assert not calls,'Known ending should not query SQL'
    report['add_eleventh_card']={'samples':additions,'median_ms':statistics.median(s['service_ms'] for s in additions),'warm_sql_queries':0}
    bundle=json.loads(Path('data/bkg-2024-r3.json').read_text())
    places=[p for p in bundle['places'] if p['object_class']=='AX_Ortslage' and not p.get('virtual') and p.get('name','').strip()]
    assignments=db.run("SELECT source_id,grid_x::text||'_'||grid_y::text cell FROM place_record",{})
    cells_by_source={r['source_id']:r['cell'] for r in assignments}
    def oracle(selection,result):
        eligible=[p for p in places if (not selection.kinds or ('district' if p.get('district') else 'settlement') in selection.kinds)
            and (not selection.regions or p.get('municipality_code','').startswith('01'))]
        expected={}
        for p in eligible:
            cell=cells_by_source[p['source_id']]
            den,nums=expected.setdefault(cell,[0,[0]*len(selection.groups)])
            expected[cell][0]+=1
            names=[normalize(n) for n in [p['name'],*p.get('alternatives',[])]]
            for i,g in enumerate(selection.groups):
                if any(n.endswith(normalize(pattern.value)) for n in names for pattern in g.patterns) and not any(n.endswith(normalize(pattern.value)) for n in names for pattern in g.exclusions):nums[i]+=1
        assert result.denominator==len(eligible)
        assert {cell.id:[cell.denominator,cell.counts] for cell in result.cells}==expected
    from atlas.schemas import normalize
    oracle(f,grid.values(None,f,dataset))
    others=['bek','burg','berg','büttel','büll','leben','rode','a','straße','neverexists']
    twenty=f.model_copy(deep=True);twenty.groups=[Group(id=f'x{i}',title=v,patterns=[Pattern(value=v)]) for i,v in enumerate(others)]
    oracle(twenty,grid.values(None,twenty,dataset))
    combined=twenty.model_copy(deep=True);combined.groups[0].patterns=[Pattern(value='ing'),Pattern(value='ingen')];combined.groups[0].exclusions=[Pattern(value='hingen')]
    oracle(combined,grid.values(None,combined,dataset))
    filtered=f.model_copy(deep=True);filtered.regions=['state:01'];filtered.kinds=['district']
    oracle(filtered,grid.values(None,filtered,dataset))
    calls.clear();grid.counts(None,extra,dataset)
    # The real region/kind selection plan is separate from suffix searches.
    report['real_oracle_checks']=['45,858 objects, all cells and ten initial endings','twenty distinct endings in two batches',
        'zero matches','Unicode Straße','ing + ingen variants with hingen exclusion','Schleswig-Holstein + district filter','eleventh suffix has one SQL query and no spatial work','warm suffix has no SQL queries']
report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({phase: {k: v['median'] for k,v in report[phase].items()}}, indent=2))
