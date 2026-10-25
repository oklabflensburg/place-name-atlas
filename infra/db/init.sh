#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=runtime_password="$RUNTIME_PASSWORD" --set=import_password="$IMPORT_PASSWORD" <<'SQL'
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SELECT format('CREATE ROLE atlas_runtime LOGIN PASSWORD %L', :'runtime_password') \gexec
SELECT format('CREATE ROLE atlas_import LOGIN PASSWORD %L', :'import_password') \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO atlas_runtime, atlas_import;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO atlas_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, MAINTAIN ON TABLES TO atlas_import;
SQL
