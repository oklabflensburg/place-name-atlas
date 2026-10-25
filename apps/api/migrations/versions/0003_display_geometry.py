"""Store projected display boundaries once instead of rebuilding them per request."""
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    op.execute("""ALTER TABLE admin_area ADD COLUMN display_geom geometry(MultiPolygon,3035)
        GENERATED ALWAYS AS (ST_SimplifyPreserveTopology(ST_Transform(geom,3035),150)) STORED NOT NULL""")


def downgrade():
    op.execute("ALTER TABLE admin_area DROP COLUMN display_geom")
