"""Real SQL/API service timings; specify immutable dataset. No claims about public production capacity."""
import argparse
import json
import os
import platform
import statistics
import time
from pathlib import Path
from sqlalchemy import create_engine,text
from sqlmodel import Session
from atlas import service
from atlas.schemas import Filter,Group,Pattern
from atlas.search import compile_filter

parser=argparse.ArgumentParser();parser.add_argument("dataset",nargs='?');parser.add_argument("--url",default=os.getenv("DATABASE_URL"));parser.add_argument('--short-only',action='store_true');args=parser.parse_args()
if not args.url:parser.error("DATABASE_URL oder --url erforderlich")
engine=create_engine(args.url,connect_args={'options':'-c statement_timeout=10000'})
with engine.connect() as c:
    if not args.dataset:args.dataset=c.execute(text('SELECT dataset_id FROM publication WHERE id=1')).scalar_one()
    version=c.execute(text("SELECT version(),PostGIS_Full_Version()")).fetchone()
    count=c.execute(text("SELECT count(*) FROM place_record WHERE dataset_id=:id"),{"id":args.dataset}).scalar()
    database_bytes=c.execute(text('SELECT pg_database_size(current_database())')).scalar_one()
    buffers=c.execute(text('SHOW shared_buffers')).scalar_one()
    assignment_plan=c.execute(text("""EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON)
        SELECT id,code FROM admin_area WHERE dataset_id=:d AND level='municipality'
        AND ST_Covers(geom,ST_SetSRID(ST_MakePoint(9.43,54.78),4326))"""),{'d':args.dataset}).scalar_one()
results=[]
cases=[('contains','a')] if args.short_only else [("suffix","bach"),("suffix","a"),("contains","otter"),("exact","Flensburg"),("prefix","Neu")]
for mode,value in cases:
    f=Filter(dataset=args.dataset,groups=[Group(id="a",title=value,patterns=[Pattern(mode=mode,value=value)])])
    samples=[]
    for i in range(11):
        with Session(engine) as s:
            start=time.perf_counter();d=service.dataset_for(s,f)
            n=service.count(s,f,d);service.place_rows(s,f,d,30,0)
            stat=service.statistics(s,f,d)
            mvt=service.tile(s,f,d,0,0,0)
            samples.append((time.perf_counter()-start)*1000)
    _,where,_,params=compile_filter(f,args.dataset)
    with engine.connect() as c:
        plan=c.execute(text(f"EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT p.id FROM place_record p WHERE {where}"),params).scalar()
    results.append({"mode":mode,"pattern":value,"matches":n,"first_ms":samples[0],"warm_median_ms":statistics.median(samples[1:]),
        "warm_p95_ms":sorted(samples[1:])[-1],"tile_bytes":len(mvt),"plan":plan})
cpu=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),platform.processor())
mem=next(line for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemTotal:'))
record={"dataset":args.dataset,"places":count,"cpu":cpu,"machine":platform.machine(),
    'os':platform.platform(),'host_memory':mem,'database_bytes':database_bytes,'shared_buffers':buffers,
    'cgroup_memory_limit':Path('/sys/fs/cgroup/memory.max').read_text().strip() if Path('/sys/fs/cgroup/memory.max').exists() else None,
    'assignment_plan':assignment_plan,
    "logical_cpus":os.cpu_count(),"postgres":version[0],"postgis":version[1],"cache":"First request recorded separately; subsequent requests warm PostgreSQL/OS caches, no application cache. Caches not forcibly evicted.",
    "method":"Sequential service count + first page + complete regional statistics + world aggregate tile; 11 iterations, p95 nearest-rank of 10 warm samples; no concurrent users.","results":results}
Path("artifacts").mkdir(exist_ok=True)
Path('artifacts/benchmark-short.json' if args.short_only else "artifacts/benchmark.json").write_text(json.dumps(record,indent=2,default=str)+"\n")
print(json.dumps({k:v for k,v in record.items() if k not in ('results','assignment_plan')},default=str))
for r in results:print(json.dumps({k:v for k,v in r.items() if k!='plan'}))
