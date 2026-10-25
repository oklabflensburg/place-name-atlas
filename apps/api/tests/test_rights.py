import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def test_read_only_runtime_role_cannot_mutate(db):
    role="atlas_test_reader_"+uuid.uuid4().hex[:10]
    with db.begin() as c:
        c.execute(text(f"CREATE ROLE {role}"))
        c.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        c.execute(text(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}"))
    try:
        with db.connect() as c:
            c.execute(text(f"SET ROLE {role}"))
            assert c.execute(text("SELECT count(*) FROM dataset")).scalar()==0
            with pytest.raises(DBAPIError):
                c.execute(text("DELETE FROM dataset"))
            c.rollback()
            c.execute(text("RESET ROLE"));c.commit()
    finally:
        with db.begin() as c:
            c.execute(text(f"DROP OWNED BY {role}"))
            c.execute(text(f"DROP ROLE {role}"))
