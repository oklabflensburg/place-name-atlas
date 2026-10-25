"""Run integration tests in a dedicated local database, never the configured runtime database."""
import getpass
import os
import subprocess
import psycopg

admin=os.getenv("TEST_ADMIN_URL",f"postgresql://{getpass.getuser()}@127.0.0.1:55439/postgres")
with psycopg.connect(admin,autocommit=True) as c:
    if not c.execute("SELECT 1 FROM pg_database WHERE datname='atlas_test'").fetchone():
        c.execute("CREATE DATABASE atlas_test")
from psycopg.conninfo import conninfo_to_dict,make_conninfo
connection=conninfo_to_dict(admin);connection["dbname"]="atlas_test"
from sqlalchemy import URL
url=URL.create("postgresql+psycopg",username=connection.get("user"),password=connection.get("password"),
    host=connection.get("host"),port=int(connection.get("port","5432")),database="atlas_test").render_as_string(hide_password=False)
result=subprocess.run([".venv/bin/python","-m","pytest","-q"],env={**os.environ,"TEST_DATABASE_URL":url,"PYTHONPATH":"apps/api"})
raise SystemExit(result.returncode)
