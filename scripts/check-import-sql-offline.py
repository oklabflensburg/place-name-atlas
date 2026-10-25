"""Run production staging/area/population SQL without sockets in a NEW disposable cluster.

Fixture-only SQL check; does not exercise the SQLAlchemy driver/server cursors,
place import, publication, concurrent locks or full-import memory. No existing
cluster, database or configuration is accessed. No service is started.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import subprocess
import time
import tempfile
import sys
from types import SimpleNamespace
from psycopg.adapt import Transformer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))
from atlas import import_staging as stage

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=ROOT/'artifacts/import-sql-offline.json')
args=parser.parse_args()
(ROOT/'artifacts').mkdir(exist_ok=True)
temporary=tempfile.TemporaryDirectory(prefix='import-sql-check-',dir=ROOT/'artifacts')
DATA=Path(temporary.name)/'db'
subprocess.run(['/usr/lib/postgresql/18/bin/initdb','-D',str(DATA),'-A','trust','--no-locale','-E','UTF8'],check=True,capture_output=True)
MARKER=b'marker = "ATLAS_SQL_DONE"'

def quote(v):
    return Transformer().as_literal(v).decode()

class Result:
    def __init__(self, rows): self.data=rows
    def mappings(self): return self
    def __iter__(self): return iter(self.data)
    def one(self):
        assert len(self.data)==1,self.data
        return self.data[0]
    def scalar(self): return next(iter(self.data[0].values())) if self.data else None
    def scalars(self): return Values([next(iter(r.values())) for r in self.data])
    def close(self): pass

class Values:
    def __init__(self,values):self.values=values
    def __iter__(self):return iter(self.values)
    def all(self):return self.values

class Native:
    def __init__(self):
        self.errors=open(Path(temporary.name)/'postgres.stderr','w+')
        self.process=subprocess.Popen(['/usr/lib/postgresql/18/bin/postgres','--single','-D',str(DATA),'postgres'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.errors)
    def send(self,sql):
        sql=sql.replace('\n',' ').strip().rstrip(';')
        self.process.stdin.write((sql+';\nSELECT \'ATLAS_SQL_DONE\' AS marker;\n').encode())
        self.process.stdin.flush()
        result=b''
        deadline=time.monotonic()+15
        while MARKER not in result:
            if time.monotonic()>deadline:
                self.errors.flush()
                self.errors.seek(0)
                raise RuntimeError(self.errors.read()[-2000:]+' Timeout waiting for SQL result: '+sql[:300])
            ready,_,_=select.select([self.process.stdout],[],[],1)
            if ready:
                part=os.read(self.process.stdout.fileno(),65536)
                if not part: raise RuntimeError('Postgres exited')
                result+=part
        return [json.loads(m[1]) for m in re.finditer(r'row_to_json = "(.*)"\t\(typeid',result.decode())]
    def execute(self,statement,params=None,execution_options=None):
        sql=str(statement).strip()
        if isinstance(params,list):
            for p in params:self.execute(statement,p)
            return Result([])
        params=params or {}
        sql=re.sub(r'(?<!:):([a-zA-Z_]\w*)',lambda m:quote(params[m[1]]),sql)
        if sql.upper().startswith('SELECT'):
            sql='SELECT row_to_json(q) FROM ('+sql+') q'
        elif re.search(r'\bRETURNING\b',sql,re.I):
            sql='WITH q AS ('+sql+') SELECT row_to_json(q) FROM q'
        return Result(self.send(sql))
    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=15)
        self.errors.close()

s=Native()
results=[]
try:
    # Only the brand-new disposable cluster is used. No schema reset or existing rows.
    s.send((ROOT/'apps/api/migrations/versions/0001_initial.sql').read_text())
    for name in ('0002_comparison_grid.py','0003_display_geometry.py'):
        spec=importlib.util.spec_from_file_location('migration',ROOT/'apps/api/migrations/versions'/name)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.op=SimpleNamespace(execute=s.execute);module.upgrade()
    synthetic=json.loads((ROOT/'tests/fixtures/synthetic.json').read_text())
    flensburg=json.loads((ROOT/'tests/fixtures/bkg-2024-flensburg.json').read_text())
    cases=[('synthetic',synthetic,None),('bkg-flensburg',flensburg,None)]
    other=copy.deepcopy(synthetic)
    part=next(a for a in reversed(other['areas']) if a['code']=='01001001')
    other['areas'].remove(part);other['areas'].append(part)
    cases.append(('interleaved',other,None))
    reverse={k:v for k,v in reversed(list(synthetic.items()))}
    cases.append(('fields-reversed',reverse,None))
    for field in ('name','ars','ibz','ibz_type'):
        b=copy.deepcopy(synthetic)
        p=copy.deepcopy(next(a for a in b['areas'] if a['level']=='municipality'))
        if field=='ibz_type':p['ibz']=int(p['ibz'])
        else:p[field]+='changed'
        b['areas'].append(p)
        cases.append(('inconsistent-'+field,b,'Widersprüchliche Verwaltungseinheit'))
    for value in (123.0,-1,'123'):
        b=copy.deepcopy(synthetic);b['population'][0]['value']=value
        cases.append(('population-'+repr(value),b,'Einwohnerzahl'))
    for label,bundle,expected_error in cases:
        path=Path(temporary.name)/'bundle.json'
        path.write_text(json.dumps(bundle,ensure_ascii=False))
        s.execute('BEGIN')
        try:
            metadata,counts,checksum=stage.stage_bundle(s,path)
            sources=[dict(status='staged',importer_version='native-sql-check',**src) for src in metadata['sources']]
            s.execute('INSERT INTO source_version SELECT * FROM jsonb_populate_recordset(NULL::source_version,:src::jsonb)',{'src':json.dumps(sources)})
            d=dict(status='staging',fingerprint=checksum,report={},created_at='2026-10-25',**metadata['dataset'])
            s.execute('INSERT INTO dataset SELECT * FROM jsonb_populate_record(NULL::dataset,:d::jsonb)',{'d':json.dumps(d)})
            stage.create_work_tables(s)
            report={'invalid_geometries':0,'invalid_geometry_details':[],'missing_population':0,'ambiguous_population':0}
            try:
                stage.import_areas(s,metadata['dataset'],report)
                s.execute('ANALYZE admin_area')
                stage.import_population(s,metadata['dataset'],report)
            except ValueError as exc:
                if expected_error and expected_error in str(exc):
                    results.append({'case':label,'expected_error':str(exc),'passed':True})
                    continue
                raise
            assert expected_error is None,label
            values=s.execute("SELECT count(*) AS areas,(SELECT sum(value) FROM population) AS total_population,(SELECT count(*) FROM population WHERE quality='missing') AS missing FROM admin_area").mappings().one()
            if label=='bkg-flensburg':
                assert values=={'areas':3,'total_population':96326,'missing':0},values
            else:
                assert values=={'areas':4,'total_population':1234,'missing':1},values
                assert s.execute("SELECT ST_NumGeometries(geom) FROM admin_area WHERE code='01001001'").scalar()==2
            invalid=s.execute('SELECT count(*) FROM admin_area WHERE NOT ST_IsValid(geom)').scalar()
            assert invalid==0
            results.append({'case':label,'passed':True,'actual':values,'report':report})
        finally:
            s.execute('ROLLBACK')
        assert s.execute('SELECT count(*) FROM dataset').scalar()==0
    args.output.write_text(json.dumps({'method':'Production staging/area/population helper SQL against postgres --single in a new disposable PostgreSQL 18.6/PostGIS cluster. No real SQLAlchemy driver/cursors or complete place import. Each scenario rolled back.','cases':results},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results,ensure_ascii=False,indent=2))
finally:
    s.close()
    temporary.cleanup()
