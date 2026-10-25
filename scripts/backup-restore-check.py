"""Actually exercise pg_dump/pg_restore in a disposable local database."""
import getpass
import json
import os
import subprocess
import uuid
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict,make_conninfo

admin=os.getenv("TEST_ADMIN_URL",f"postgresql://{getpass.getuser()}@127.0.0.1:55439/postgres")
options=conninfo_to_dict(admin)
source=make_conninfo(**{**options,"dbname":os.getenv("RESTORE_SOURCE_DATABASE","atlas_test_web")})
destination="atlas_restore_"+uuid.uuid4().hex[:12]
target=make_conninfo(**{**options,"dbname":destination})
path=Path("artifacts/restore-check.dump");path.parent.mkdir(exist_ok=True)
env={**os.environ,"PGPASSWORD":options.get("password",""),"PGHOST":options.get("host",""),
     "PGPORT":options.get("port","5432"),"PGUSER":options.get("user",getpass.getuser())}
subprocess.run(["pg_dump","--dbname",os.getenv("RESTORE_SOURCE_DATABASE","atlas_test_web"),"--format=custom","--no-owner","--file",str(path)],check=True,env=env)
with psycopg.connect(admin,autocommit=True) as c:c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(destination)))
try:
    subprocess.run(["pg_restore","--dbname",destination,"--no-owner","--exit-on-error",str(path)],check=True,env=env)
    check="""SELECT (SELECT count(*) FROM place_record),(SELECT count(*) FROM admin_area),
        (SELECT sum(value) FROM population),(SELECT dataset_id FROM publication WHERE id=1),
        (SELECT count(*) FROM place_record WHERE NOT ST_IsValid(geom))"""
    with psycopg.connect(source) as a,psycopg.connect(target) as b:
        before=a.execute(check).fetchone();after=b.execute(check).fetchone()
        assert before==after,(before,after)
    result={"restored":True,"places":after[0],"areas":after[1],"population_sum":int(after[2]) if after[2] is not None else None,
            "active_dataset":after[3],"invalid_geometries":after[4],"dump_bytes":path.stat().st_size}
    Path("artifacts/restore-check.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
finally:
    with psycopg.connect(admin,autocommit=True) as c:c.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(destination)))
