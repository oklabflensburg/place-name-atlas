import getpass
import json
import os
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
admin=os.getenv('TEST_ADMIN_URL',f'postgresql://{getpass.getuser()}@127.0.0.1:55439/postgres')
with psycopg.connect(admin) as c:
    rows=c.execute("SELECT datname,state,wait_event_type,wait_event,clock_timestamp()-query_start AS query_age,left(query,100) FROM pg_stat_activity WHERE datname IN ('atlas_dev','postgres') AND pid<>pg_backend_pid()").fetchall()
    print(json.dumps(rows,default=str))
with psycopg.connect(make_conninfo(**{**conninfo_to_dict(admin),'dbname':'atlas_dev'})) as c:
    rows=c.execute("SELECT relname,n_tup_ins,pg_relation_size(relid) FROM pg_stat_user_tables WHERE relname IN ('place_record','admin_area')").fetchall()
    print(json.dumps({'physical_progress_not_published_counts':rows},default=str))
    plan=c.execute("EXPLAIN SELECT id,code FROM admin_area WHERE dataset_id='bkg-2024-r2' AND level='municipality' AND ST_Covers(geom,ST_SetSRID(ST_MakePoint(9.43,54.78),4326))").fetchall()
    print(json.dumps({'assignment_plan':[p[0] for p in plan]},default=str))
