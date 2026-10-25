from alembic import context
from sqlalchemy import create_engine
from atlas.config import settings
from atlas.models import SQLModel

target_metadata = SQLModel.metadata
url = settings().migration_database_url or settings().database_url
if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url).connect() as connection:
        context.configure(connection=connection,target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
