"""Initial immutable schema; SQL is frozen beside this revision."""
from pathlib import Path
from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    sql = Path(__file__).with_suffix(".sql").read_text()
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    for table in ["place_name","place_record","population","admin_area","admin_identity",
                  "place_identity","publication","dataset","source_version"]:
        op.execute(f"DROP TABLE {table}")
