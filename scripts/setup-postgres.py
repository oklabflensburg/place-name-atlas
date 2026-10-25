"""Set up atlas in the system PostgreSQL on port 5432, keeping credentials in .env."""
import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
ROLES = {
    "MIGRATION_DATABASE_URL": "atlas_owner",
    "DATABASE_URL": "atlas_runtime",
    "IMPORT_DATABASE_URL": "atlas_import",
}


def configuration():
    path = ROOT / ".env"
    if not path.exists():
        content = (ROOT / ".env.example").read_text()
        for name in ("owner", "runtime", "import"):
            content = content.replace(f"local-development-{name}", secrets.token_hex(24))
        with open(path, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as out:
            out.write(content)
    values = dotenv_values(path)
    urls = {}
    for key, role in ROLES.items():
        if not values.get(key):
            raise ValueError(f"{key} fehlt in .env.")
        url = make_url(values[key])
        if (url.drivername != "postgresql+psycopg" or url.host != "127.0.0.1"
                or url.port != 5432 or url.database != "atlas" or url.username != role
                or not url.password or "host" in url.query or "port" in url.query):
            raise ValueError(f"{key} muss in .env auf {role}@127.0.0.1:5432/atlas zeigen, mit Passwort.")
        urls[key] = url
    path.chmod(0o600)
    return urls


def admin_command(program, database):
    return ["sudo", "-u", "postgres", program, "-h", "/var/run/postgresql",
            "-p", "5432", "-d", database]


def admin(statement, database="postgres"):
    result = subprocess.run(
        [*admin_command("psql", database), "-X", "-w", "-v", "ON_ERROR_STOP=1", "-Atq"],
        input=statement + "\n", text=True, stdout=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError("PostgreSQL-Einrichtung fehlgeschlagen. Server auf Port 5432 und sudo-Zugriff prüfen.")
    return result.stdout.strip()


def connect(url):
    return psycopg.connect(
        host=url.host, port=url.port, dbname=url.database,
        user=url.username, password=url.password, connect_timeout=5,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--restore", type=Path, help="Optional: vorhandenen pg_dump in die leere Datenbank übernehmen.")
    mode.add_argument("--prepare-only", action="store_true", help="Nur .env für Port 5432 vorbereiten.")
    args = parser.parse_args()
    if args.restore and not args.restore.is_file():
        parser.error("Die angegebene Sicherung existiert nicht.")
    for program in (() if args.prepare_only else ("sudo", "psql", "pg_restore")):
        if not shutil.which(program):
            parser.error(f"{program} ist nicht installiert.")
    urls = configuration()
    if args.prepare_only:
        print(".env für atlas auf 127.0.0.1:5432 vorbereitet (Dateirechte 0600). Keine Datenbank verändert.")
        return

    # Check ownership before changing anything in the shared system cluster.
    state = json.loads(admin("""SELECT json_build_object(
        'version', current_setting('server_version_num')::int,
        'owner', (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='atlas'),
        'extensions', (SELECT count(*) FROM pg_available_extensions WHERE name IN ('postgis','pg_trgm')),
        'elevated_roles', (SELECT count(*) FROM pg_roles WHERE
            rolname IN ('atlas_owner','atlas_runtime','atlas_import') AND
            (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)),
        'memberships', (SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member
            WHERE r.rolname IN ('atlas_owner','atlas_runtime','atlas_import'))
    );"""))
    if state["version"] < 180000 or state["extensions"] != 2:
        raise ValueError("PostgreSQL 18+ mit installiertem PostGIS und pg_trgm wird benötigt.")
    if state["owner"] not in (None, "atlas_owner") or state["elevated_roles"] or state["memberships"]:
        raise ValueError("Datenbank atlas oder Atlas-Rollen werden bereits anders verwendet; keine Rechte geändert.")

    statements = ["SET password_encryption = 'scram-sha-256';"]
    for key, role in ROLES.items():
        create = sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(urls[key].password),
        ).as_string()
        statements.append(sql.SQL("SELECT {} WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname={}) ").format(
            sql.Literal(create), sql.Literal(role),
        ).as_string() + "\\gexec")
    statements.append("SELECT 'CREATE DATABASE atlas OWNER atlas_owner' "
                      "WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='atlas') \\gexec")
    admin("\n".join(statements))
    # Existing roles keep their passwords. Verify all three before restore/migration.
    for url in urls.values():
        with connect(url):
            pass

    if args.restore:
        tables = admin("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f')
            AND NOT EXISTS (SELECT FROM pg_depend d WHERE d.classid='pg_class'::regclass
                AND d.objid=c.oid AND d.deptype='e');""", "atlas")
        if int(tables):
            raise ValueError("Restore benötigt eine leere Datenbank atlas. Vorhandene Tabellen bleiben erhalten.")
        print("Übernehme Sicherung nach atlas auf Port 5432 …", flush=True)
        with args.restore.open("rb") as backup:
            subprocess.run([*admin_command("pg_restore", "atlas"), "--no-owner", "--no-privileges",
                            "--exit-on-error", "--single-transaction"], stdin=backup, check=True)

    admin("""CREATE EXTENSION IF NOT EXISTS postgis;
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
        REVOKE CREATE ON SCHEMA public FROM PUBLIC;
        GRANT USAGE ON SCHEMA public TO atlas_owner, atlas_runtime, atlas_import;
        -- A restore runs as postgres so it can also restore PostGIS metadata.
        -- Hand application tables back to the migration owner, excluding extension objects.
        SELECT format('ALTER TABLE %I.%I OWNER TO atlas_owner', n.nspname, c.relname)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p')
        AND NOT EXISTS (SELECT FROM pg_depend d WHERE d.classid='pg_class'::regclass
            AND d.objid=c.oid AND d.deptype='e')
        \\gexec
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO atlas_runtime;
        GRANT SELECT, INSERT, UPDATE, MAINTAIN ON ALL TABLES IN SCHEMA public TO atlas_import;
        ALTER DEFAULT PRIVILEGES FOR ROLE atlas_owner IN SCHEMA public
            GRANT SELECT ON TABLES TO atlas_runtime;
        ALTER DEFAULT PRIVILEGES FOR ROLE atlas_owner IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE, MAINTAIN ON TABLES TO atlas_import;
    """, "atlas")
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "apps/api"),
                   **{key: url.render_as_string(hide_password=False) for key, url in urls.items()}}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=ROOT, env=environment, check=True)
    with connect(urls["DATABASE_URL"]) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        connection.execute("SELECT grid_x, grid_y FROM place_record LIMIT 0")
        connection.execute("SELECT display_geom FROM admin_area LIMIT 0")
        if connection.execute("SELECT has_table_privilege(current_user, 'place_record', 'INSERT')").fetchone()[0]:
            raise ValueError("Runtime-Rolle hat unerwartete Schreibrechte.")
        published = connection.execute("SELECT dataset_id FROM publication WHERE id=1").fetchone()
        count = connection.execute("SELECT count(*) FROM place_record WHERE dataset_id=%s",
                                   (published[0] if published else None,)).fetchone()[0]
    print(f"atlas auf 127.0.0.1:5432 bereit, Migration {revision}, {count} veröffentlichte Orte.")
    if not published:
        print("Noch kein Bestand veröffentlicht. Anschließend Daten über die Atlas-CLI importieren und veröffentlichen.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError, psycopg.Error) as error:
        print(f"Einrichtung abgebrochen: {error}", file=sys.stderr)
        sys.exit(1)
