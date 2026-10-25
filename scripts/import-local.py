"""Local development import with real runtime/import/migration privilege separation."""
import getpass
import json
import os
import subprocess
import time
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import URL,create_engine

admin=os.getenv("TEST_ADMIN_URL",f"postgresql://{getpass.getuser()}@127.0.0.1:55439/postgres")
connection=conninfo_to_dict(admin)
with psycopg.connect(admin,autocommit=True) as c:
    if not c.execute("SELECT 1 FROM pg_database WHERE datname='atlas_dev'").fetchone():c.execute("CREATE DATABASE atlas_dev")
    for role in ['atlas_runtime','atlas_import']:
        if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(role,)).fetchone():
            from psycopg import sql
            c.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))

def url(user):
    return URL.create("postgresql+psycopg",username=user,password=connection.get("password") if user==connection.get("user") else None,
        host=connection.get("host"),port=int(connection.get("port","5432")),database="atlas_dev").render_as_string(hide_password=False)

owner=url(connection.get('user',getpass.getuser()))
with create_engine(owner).begin() as c:
    from sqlalchemy import text
    for statement in ["REVOKE CREATE ON SCHEMA public FROM PUBLIC", "GRANT USAGE ON SCHEMA public TO atlas_runtime,atlas_import",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO atlas_runtime",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT,INSERT,UPDATE,MAINTAIN ON TABLES TO atlas_import"]:
        c.execute(text(statement))
subprocess.run(['.venv/bin/alembic','upgrade','head'],check=True,env={**os.environ,'MIGRATION_DATABASE_URL':owner})
os.environ['DATABASE_URL']=url('atlas_runtime')
from atlas.importer import import_bundle,publish
path=Path('data/bkg-2024-r3.json')
start=time.monotonic();engine=create_engine(url('atlas_import'))
report=import_bundle(path,engine);identifier=json.loads(path.read_text())['dataset']['id']
publish(identifier,engine)
assert import_bundle(path,engine)==report
record={**report,'duration_seconds':round(time.monotonic()-start,3)}
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/bkg-import-report.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(record,ensure_ascii=False))
from fastapi.testclient import TestClient
from atlas.main import app
client=TestClient(app)
assert client.get('/health/ready').status_code==200
q=json.dumps({'dataset':identifier,'groups':[{'id':'a','title':'otter','patterns':[{'mode':'contains','value':'otter'}]}]})
listed=client.get('/api/v1/places',params={'q':q}).json()
stats=client.get('/api/v1/statistics',params={'q':q}).json()
exported=client.get('/api/v1/export',params={'q':q,'format':'geojson'}).json()
assert listed['total']==stats['total']==len(exported['features'])
print(json.dumps({'real_smoke':True,'dataset':identifier,'otter_count':listed['total']}))
