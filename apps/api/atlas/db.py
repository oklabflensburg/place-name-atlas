from functools import lru_cache
from sqlalchemy import text
from sqlmodel import Session, create_engine
from atlas.config import settings
from atlas.timing import instrument


@lru_cache
def engine():
    result = create_engine(settings().database_url, pool_pre_ping=True, pool_size=8, max_overflow=4,
                         connect_args={"options": f"-c statement_timeout={settings().query_timeout_ms}"})
    instrument(result)
    return result


def session():
    with Session(engine()) as s:
        # All endpoint queries observe one publication and one immutable snapshot.
        s.exec(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        yield s
