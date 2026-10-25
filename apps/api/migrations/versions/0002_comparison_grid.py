"""Fixed equal-area grid membership, also calculated for future imports."""
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.execute("""ALTER TABLE place_record
        ADD COLUMN grid_x integer GENERATED ALWAYS AS
          (floor(ST_X(ST_Transform(geom,3035))/20000)::integer) STORED,
        ADD COLUMN grid_y integer GENERATED ALWAYS AS
          (floor(ST_Y(ST_Transform(geom,3035))/20000)::integer) STORED""")
    op.execute("CREATE INDEX place_grid ON place_record(dataset_id,grid_x,grid_y,kind)")


def downgrade():
    op.execute("DROP INDEX place_grid")
    op.execute("ALTER TABLE place_record DROP COLUMN grid_x, DROP COLUMN grid_y")
