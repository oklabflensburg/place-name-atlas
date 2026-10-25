import os
import subprocess
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlmodel import create_engine
from atlas.config import settings
from atlas.db import engine as runtime_engine


@pytest.fixture(scope="session")
def database():
    url=os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL fehlt: echte PostGIS-Integration wird nicht vorgetäuscht")
    if not (make_url(url).database or "").startswith("atlas_test"):
        raise RuntimeError("Integrationstests dürfen nur eine atlas_test*-Datenbank zurücksetzen")
    engine=create_engine(url)
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    subprocess.run(["uv","run","--no-sync","alembic","upgrade","head"],check=True,
        env={**os.environ,"MIGRATION_DATABASE_URL":url})
    os.environ["DATABASE_URL"]=url
    settings.cache_clear();runtime_engine.cache_clear()
    yield engine
    engine.dispose()


@pytest.fixture
def db(database):
    with database.begin() as c:
        c.execute(text("TRUNCATE source_version, dataset, publication, place_identity, admin_identity, admin_area, population, place_record, place_name CASCADE"))
    return database
