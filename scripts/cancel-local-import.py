"""Cancel only this project's still-staging local importer, allowing its rollback handler."""
import getpass,os
import psycopg
admin=os.getenv('TEST_ADMIN_URL',f'postgresql://{getpass.getuser()}@127.0.0.1:55439/postgres')
with psycopg.connect(admin,autocommit=True) as c:
    rows=c.execute("SELECT pid FROM pg_stat_activity WHERE datname='atlas_dev' AND usename='atlas_import' AND state='active'").fetchall()
    if len(rows)!=1:raise RuntimeError('Genau ein aktiver lokaler Import erwartet')
    print({'cancelled_own_import':c.execute('SELECT pg_cancel_backend(%s)',(rows[0][0],)).fetchone()[0]})
