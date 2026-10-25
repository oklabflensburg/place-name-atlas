CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE TABLE source_version (
 id text PRIMARY KEY, product text NOT NULL, version text NOT NULL, data_date text NOT NULL,
 retrieved_at text NOT NULL, url text NOT NULL, sha256 text NOT NULL, license text NOT NULL,
 attribution text NOT NULL, original_crs text NOT NULL, status text NOT NULL, importer_version text NOT NULL
);
CREATE TABLE dataset (
 id text PRIMARY KEY,label text NOT NULL,status text NOT NULL CHECK(status IN ('staging','validated','failed','published')),
 synthetic boolean NOT NULL,scope text NOT NULL,geometry_date text NOT NULL,population_date text NOT NULL,
 gn_source text NOT NULL REFERENCES source_version(id),vg_source text NOT NULL REFERENCES source_version(id),
 ew_source text NOT NULL REFERENCES source_version(id),fingerprint text NOT NULL,report jsonb NOT NULL,created_at text NOT NULL
);
CREATE TABLE publication(id integer PRIMARY KEY CHECK(id=1),dataset_id text NOT NULL REFERENCES dataset(id));
CREATE TABLE place_identity(id text PRIMARY KEY,source_id text UNIQUE NOT NULL,feature_id bigint UNIQUE NOT NULL);
CREATE TABLE admin_identity(id text PRIMARY KEY,level text NOT NULL,code text NOT NULL);
CREATE TABLE admin_area (
 id text PRIMARY KEY,dataset_id text NOT NULL REFERENCES dataset(id),identity_id text NOT NULL REFERENCES admin_identity(id),
 source_id text NOT NULL,code text NOT NULL,ars text NOT NULL,level text NOT NULL,parent_code text,
 name text NOT NULL,normalized_name text NOT NULL,ibz text NOT NULL,geom geometry(MultiPolygon,4326) NOT NULL,
 UNIQUE(dataset_id,identity_id)
);
CREATE INDEX admin_geom ON admin_area USING gist(geom);
CREATE INDEX admin_dataset_code ON admin_area(dataset_id,level,code);
CREATE TABLE population (
 id text PRIMARY KEY,dataset_id text NOT NULL REFERENCES dataset(id),area_id text NOT NULL REFERENCES admin_area(id),
 source_id text NOT NULL REFERENCES source_version(id),reference_date text NOT NULL,
 value bigint CHECK(value IS NULL OR value>=0),quality text NOT NULL,UNIQUE(dataset_id,area_id)
);
CREATE TABLE place_record (
 id text PRIMARY KEY,dataset_id text NOT NULL REFERENCES dataset(id),place_id text NOT NULL REFERENCES place_identity(id),
 source_id text NOT NULL,name text NOT NULL,kind text NOT NULL,geom geometry(Point,4326) NOT NULL,
 municipality_id text REFERENCES admin_area(id),assignment text NOT NULL,candidates jsonb NOT NULL,
 UNIQUE(dataset_id,place_id)
);
CREATE INDEX place_geom ON place_record USING gist(geom);
CREATE INDEX place_dataset ON place_record(dataset_id,kind);
CREATE INDEX place_public ON place_record(dataset_id,place_id);
CREATE TABLE place_name (
 id text PRIMARY KEY,record_id text NOT NULL REFERENCES place_record(id),original text NOT NULL,
 normalized text NOT NULL,reversed text NOT NULL,primary_name boolean NOT NULL
);
CREATE INDEX name_record ON place_name(record_id);
CREATE INDEX name_exact ON place_name(normalized);
CREATE INDEX name_prefix ON place_name(normalized text_pattern_ops);
CREATE INDEX name_suffix ON place_name(reversed text_pattern_ops);
CREATE INDEX name_trigram ON place_name USING gin(normalized gin_trgm_ops);
