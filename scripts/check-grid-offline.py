"""Execute production grid SQL with real PostGIS without opening a network socket.

Uses a new disposable cluster in /tmp and postgres --single. It does not connect to,
copy, stop or alter any running database. This is SQL verification, not an HTTP or
browser test. The regular pytest integration suite remains the deployment check.
"""
import csv
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import time
from collections import Counter,defaultdict
from pathlib import Path
from types import SimpleNamespace
from psycopg.adapt import Transformer
from atlas import grid
from atlas.importer import stable_id
from atlas.schemas import Filter,Group,Pattern,normalize

BIN=Path(os.environ.get('POSTGRES_BIN','/usr/lib/postgresql/18/bin'))
ROOT=Path(__file__).resolve().parents[1]


def quote(v):
    return Transformer().as_literal(v).decode()


class Offline:
    def __init__(self):
        self.temp=tempfile.TemporaryDirectory(prefix='atlas-grid-check-',dir='/tmp')
        self.path=Path(self.temp.name)/'db'
        subprocess.run([str(BIN/'initdb'),'-D',str(self.path),'-A','trust','--no-locale','-E','UTF8'],check=True,capture_output=True)

    def run(self,sql,params=None):
        if params is not None:
            sql=re.sub(r'(?<!:):([a-zA-Z_]\w*)',lambda m:quote(params[m[1]]),sql)
            sql=f'SELECT row_to_json(q) FROM ({sql}) q'
        result=subprocess.run([str(BIN/'postgres'),'--single','-D',str(self.path),'postgres'],
                              input=sql.replace('\n',' ')+';\n',text=True,capture_output=True)
        if result.returncode or re.search(r'\b(ERROR|FATAL):',result.stderr):
            raise RuntimeError(result.stderr[-6000:])
        return [json.loads(m[1]) for m in re.finditer(r'row_to_json = "(.*)"\t\(typeid',result.stdout)]

    def setup(self,bundle):
        self.run('DROP SCHEMA public CASCADE; CREATE SCHEMA public;'+(ROOT/'apps/api/migrations/versions/0001_initial.sql').read_text())
        for name in ['0002_comparison_grid.py','0003_display_geometry.py']:
            migration=ROOT/'apps/api/migrations/versions'/name
            spec=importlib.util.spec_from_file_location('grid_migration',migration);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            mod.op=SimpleNamespace(execute=self.run);mod.upgrade()
        src=[]
        for s in bundle['sources']:
            s={k:v for k,v in s.items() if k not in ('archive','path')}
            s.update(status='validated',importer_version='offline-sql-check')
            src.append(s)
        self.run('INSERT INTO source_version SELECT * FROM jsonb_populate_recordset(NULL::source_version,'+quote(json.dumps(src))+')')
        d={**bundle['dataset'],'status':'published','fingerprint':hashlib.sha256(json.dumps(bundle['dataset'],sort_keys=True).encode()).hexdigest(),
           'report':{},'created_at':'2026-10-21'}
        self.run('INSERT INTO dataset SELECT * FROM jsonb_populate_record(NULL::dataset,'+quote(json.dumps(d))+')')
        selected=[p for p in bundle['places'] if p['object_class']=='AX_Ortslage' and not p.get('virtual') and p.get('name','').strip()]
        sql=[]
        for p in selected:
            pid=stable_id(p['source_id']);record_id=f"{d['id']}:{pid}"
            fid=int.from_bytes(hashlib.sha256(p['source_id'].encode()).digest()[:6],'big')
            sql.append('INSERT INTO place_identity VALUES('+','.join(map(quote,[pid,p['source_id'],fid]))+')')
            sql.append('INSERT INTO place_record(id,dataset_id,place_id,source_id,name,kind,geom,assignment,candidates) VALUES('
                +','.join(map(quote,[record_id,d['id'],pid,p['source_id'],p['name'],'district' if p.get('district') else 'settlement']))
                +',ST_SetSRID(ST_GeomFromGeoJSON('+quote(json.dumps(p['geometry']))+"),4326),'unassigned','[]')")
            for i,n in enumerate(dict.fromkeys([p['name'],*[n for n in p.get('alternatives',[]) if n and n.strip()]])):
                sql.append('INSERT INTO place_name VALUES('+','.join(map(quote,[record_id+':'+str(i),record_id,n,normalize(n),normalize(n)[::-1],i==0]))+')')
        # Only the state geometries are needed for the overview checks.
        for a in bundle['areas']:
            if a['level']!='state':continue
            ident=f"state:{a['code']}";aid=f"{d['id']}:{ident}"
            sql.append('INSERT INTO admin_identity VALUES('+','.join(map(quote,[ident,'state',a['code']]))+') ON CONFLICT DO NOTHING')
            sql.append('INSERT INTO admin_area(id,dataset_id,identity_id,source_id,code,ars,level,name,normalized_name,ibz,geom) VALUES('
                +','.join(map(quote,[aid,d['id'],ident,a['source_id'],a['code'],a['ars'],'state',a['name'],normalize(a['name']),a['ibz']]))
                +',ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON('+quote(json.dumps(a['geometry']))+'),4326))) '
                +'ON CONFLICT(id) DO UPDATE SET geom=ST_Multi(ST_UnaryUnion(ST_Collect(admin_area.geom,excluded.geom)))')
        # Chunk file-based SQL to avoid a very large parser statement.
        for start in range(0,len(sql),4000):self.run(';'.join(sql[start:start+4000]))
        self.run('ANALYZE place_record; ANALYZE place_name; ANALYZE admin_area')
        return SimpleNamespace(**d),selected


def selection(dataset):
    return Filter(dataset=dataset,groups=[Group(id=f'g{i}',title=v,patterns=[Pattern(value=v)])
        for i,v in enumerate(['ach','ingen','zell','heim','hausen','dorf','bach','itz','ow','by'])])


def verify(db,bundle,real=False):
    d,selected=db.setup(bundle);f=selection(d.id)
    original=grid.rows;grid.rows=lambda s,sql,params=None:db.run(sql,params or {})
    try:
        begin=time.perf_counter();v=grid.values(None,f,d);cold=round((time.perf_counter()-begin)*1000,1)
        expected=[sum(any(normalize(n).endswith(normalize(g.patterns[0].value)) for n in [p['name'],*p.get('alternatives',[])]) for p in selected) for g in f.groups]
        assert v.denominator==len(selected) and v.totals==expected
        assert sum(c.denominator for c in v.cells)==len(selected)
        assert all(0<=n<=c.denominator for c in v.cells for n in c.counts)
        # Independently count every cell from the source objects, rather than
        # merely checking nationally plausible totals.
        assignment=db.run('SELECT source_id,grid_x::text||\'_\'||grid_y::text cell FROM place_record',{})
        source_cells={r['source_id']:r['cell'] for r in assignment}
        oracle=defaultdict(lambda:[0,[0]*10])
        for p in selected:
            target=oracle[source_cells[p['source_id']]];target[0]+=1
            for i,group in enumerate(f.groups):
                target[1][i]+=any(normalize(n).endswith(normalize(group.patterns[0].value)) for n in [p['name'],*p.get('alternatives',[])])
        assert all([c.denominator,c.counts]==oracle[c.id] for c in v.cells)
        # Half-open membership, including exact cell edges and negative axes.
        edges=db.run('''SELECT floor(ST_X(ST_Transform(ST_Transform(ST_SetSRID(ST_MakePoint(4000000,3000000),3035),4326),3035))/20000)::int x,
            floor(-0.5/20000)::int negative_x''',{})[0]
        assert edges['x']==200 and edges['negative_x']==-1
        begin=time.perf_counter();g=grid.geometry(None,f,d);geometry_ms=round((time.perf_counter()-begin)*1000,1)
        assert set(c.id for c in v.cells)<=set(c.id for c in g.cells)
        assert all(c.cx==(int(c.id.split('_')[0])+.5)*20000 and c.cy==-(int(c.id.split('_')[1])+.5)*20000 for c in g.cells)
        assert g.crs=='EPSG:3035' and g.cell_size==20000 and g.origin==(0,0)
        left,top,width,height=g.viewbox
        assert width>0 and height>0 and g.representation=='circle-centers-v1'
        radius=g.cell_size*.41
        assert all(left<=c.cx-radius and c.cx+radius<=left+width and top<=c.cy-radius and c.cy+radius<=top+height for c in g.cells)
        if real and os.environ.get('ATLAS_GRID_CHECK_EXPORT'):
            Path(os.environ['ATLAS_GRID_CHECK_EXPORT']).write_text(json.dumps(dict(geometry=g.model_dump(),values=v.model_dump())))
        index=next(i for i,n in enumerate(v.totals) if n)
        target=next(c for c in v.cells if c.counts[index])
        p=grid.cell_places(None,f,d,target.id,f'g{index}',1,0)
        assert p.count==target.counts[index] and p.denominator==target.denominator and p.share==p.count/p.denominator
        assert len(p.items)==1
        if d.id=='ratio-40':
            ratio_page=grid.cell_places(None,f,d,target.id,'g3',100,0)
            assert ratio_page.share==.25 and ratio_page.count==10 and len(ratio_page.items)==10
        if p.count>1:
            next_page=grid.cell_places(None,f,d,target.id,f'g{index}',1,1)
            assert next_page.items[0].id!=p.items[0].id
        # Base filters must affect numerator and denominator together.
        f.kinds=['district'];f.regions=['state:01']
        subset=grid.values(None,f,d)
        expected_subset=[p for p in selected if p.get('district') and (not real or p.get('municipality_code','').startswith('01'))]
        assert subset.denominator==len(expected_subset)
        assert subset.totals[6]==sum(any(normalize(n).endswith('bach') for n in [p['name'],*p.get('alternatives',[])]) for p in expected_subset)
        f.groups[6].patterns[0].value='no-such-ending';zero=grid.values(None,f,d)
        assert zero.denominator==subset.denominator and zero.totals[6]==0
        f.regions=[];f.kinds=[];f.groups[0].patterns[0].value='ing'
        ing=grid.values(None,f,d)
        assert ing.totals[0]==sum(any(normalize(n).endswith('ing') for n in [p['name'],*p.get('alternatives',[])]) for p in selected)
        f.groups[0].patterns.append(Pattern(value='ingen'))
        combined=grid.values(None,f,d)
        assert combined.totals[0]==sum(any(normalize(n).endswith(('ing','ingen')) for n in [p['name'],*p.get('alternatives',[])]) for p in selected)
        assert any(c.id not in {v.id for v in v.cells} for c in g.cells)
        for group in f.groups:group.patterns=[Pattern(value='no-such-ending')]
        empty=grid.values(None,f,d)
        assert empty.denominator==len(selected) and empty.totals==[0]*10
        distribution=db.run('SELECT min(n) minimum,percentile_cont(ARRAY[0.25,0.5,0.75]) WITHIN GROUP(ORDER BY n) quartiles,max(n) maximum,count(*) FILTER(WHERE n<10) below_ten FROM (SELECT count(*) n FROM place_record GROUP BY grid_x,grid_y) c',{})[0]
        return dict(dataset=d.id,places=len(selected),totals=v.totals,occupied_cells=len(v.cells),geometry_cells=len(g.cells),
                    cell_distribution=distribution,values_cold_ms=cold,geometry_cold_ms=geometry_ms,
                    geometry_bytes=len(g.model_dump_json().encode()),values_bytes=len(v.model_dump_json().encode()),
                    checks=['production PostGIS SQL','every cell numerator and denominator against Python source oracle','all ten counts against Python source oracle','distinct objects with name variants',
                            'overlapping ach/bach','separate ing/ingen','region and kind denominator','zero versus no data, including all ten maps with zero hits',
                            'cell names and pagination','metric grid, identical circle centers and source coverage','finite metric viewBox encloses every full circle','explicit suffix variants count each place once'])
    finally:grid.rows=original


if __name__=='__main__':
    report={'execution':'postgres --single, isolated temporary cluster, no HTTP/browser tests','synthetic':None,'real':None}
    db=Offline()
    try:
        fixture=json.loads((ROOT/'tests/fixtures/synthetic.json').read_text())
        report['synthetic']=verify(db,fixture)
        import copy
        ratio=copy.deepcopy(fixture);ratio['dataset']['id']='ratio-40';ratio['places']=[]
        template=next(p for p in fixture['places'] if p['object_class']=='AX_Ortslage' and not p.get('virtual'))
        for i in range(40):
            p=copy.deepcopy(template);p['source_id']=f'ratio-{i}';p['name']=f'Ort{i}'+('heim' if i<10 else 'dorf')
            p['alternatives']=[f'Variante{i}heim',f'Alias{i}heim'] if i<10 else []
            ratio['places'].append(p)
        # Use the general verifier as well as the exact reference calculation.
        report['ratio_10_of_40']=verify(db,ratio)
        assert report['ratio_10_of_40']['places']==40 and report['ratio_10_of_40']['totals'][3]==10
        single=copy.deepcopy(fixture);single['dataset']['id']='single-place';single['places']=[copy.deepcopy(template)]
        single['places'][0]['name']='Nurheim';single['places'][0]['alternatives']=[]
        report['single_place_extreme']=verify(db,single)
        assert report['single_place_extreme']['totals'][3]==1
        if '--real' in __import__('sys').argv:
            report['real']=verify(db,json.loads((ROOT/'data/bkg-2024-r3.json').read_text()),True)
        path=ROOT/'docs/reports/grid-sql-check.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False))
    finally:db.temp.cleanup()
