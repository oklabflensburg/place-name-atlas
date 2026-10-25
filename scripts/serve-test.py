"""Isolated test server for browser tests. Starts with a synthetic published fixture."""
import getpass
import os
import subprocess
from pathlib import Path
import psycopg
from sqlalchemy import create_engine
from sqlalchemy import text

admin=os.getenv("TEST_ADMIN_URL",f"postgresql://{getpass.getuser()}@127.0.0.1:55439/postgres")
from psycopg.conninfo import conninfo_to_dict
connection=conninfo_to_dict(admin)
with psycopg.connect(admin,autocommit=True) as c:
    if not c.execute("SELECT 1 FROM pg_database WHERE datname='atlas_test_web'").fetchone():
        c.execute("CREATE DATABASE atlas_test_web")
from sqlalchemy import URL
url=URL.create("postgresql+psycopg",username=connection.get("user"),password=connection.get("password"),
    host=connection.get("host"),port=int(connection.get("port","5432")),database="atlas_test_web").render_as_string(hide_password=False)
os.environ["DATABASE_URL"]=url
os.environ["MIGRATION_DATABASE_URL"]=url
subprocess.run([".venv/bin/alembic","upgrade","head"],check=True)
from atlas.importer import import_bundle,publish
engine=create_engine(url)
with engine.begin() as c:
    c.execute(text("TRUNCATE source_version,dataset,publication,place_identity,admin_identity,admin_area,population,place_record,place_name CASCADE"))
import_bundle(Path("tests/fixtures/synthetic.json"),engine)
publish("synthetic-v1",engine)
import uvicorn
import json
config=json.loads(Path(os.environ.get("ATLAS_LOCAL_CONFIG","infra/test-local.json")).read_text())
uvicorn.run("atlas.main:app",host=config["host"],port=config["apiPort"],proxy_headers=False,access_log=False,h11_max_incomplete_event_size=65536)
