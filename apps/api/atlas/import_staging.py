"""Connection-local, disk-backed staging; no business rows or intermediate commits."""
import json

from sqlalchemy import text

from atlas.bundle import read_bundle

BATCH_ROWS = 100
BATCH_BYTES = 1024 * 1024
TABLES = ("atlas_import_rows", "atlas_import_areas", "atlas_import_population", "atlas_import_seen", "atlas_import_suspects")


def execute(session, sql, params=None):
    return session.execute(text(sql), params or {})


def stage_bundle(session, path):
    execute(session, """CREATE TEMP TABLE atlas_import_rows (
        seq bigint GENERATED ALWAYS AS IDENTITY, kind text NOT NULL, payload text NOT NULL
    ) ON COMMIT PRESERVE ROWS""")
    batch = []
    size = 0

    def flush():
        nonlocal size
        if batch:
            session.execute(text("INSERT INTO atlas_import_rows(kind,payload) VALUES(:kind,:payload)"), batch)
            batch.clear()
            size = 0

    def consume(kind, row):
        nonlocal size
        payload = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        # A single large feature may exceed the byte budget; never combine it
        # with an already full batch. Memory is bounded by batch + largest object.
        row_size = len(payload.encode("utf-8"))
        if size + row_size > BATCH_BYTES:
            flush()
        batch.append({"kind": kind, "payload": payload})
        size += row_size
        if len(batch) >= BATCH_ROWS or size >= BATCH_BYTES:
            flush()

    metadata, counts, fingerprint = read_bundle(path, consume)
    flush()
    execute(session, "CREATE INDEX ON atlas_import_rows(kind,seq)")
    execute(session, "ANALYZE atlas_import_rows")
    return metadata, counts, fingerprint


def rows(session, kind):
    # Stream one row at a time, including large geometries. A normal psycopg
    # cursor would buffer the ENTIRE result before Python iteration starts.
    result = session.execute(text("SELECT payload FROM atlas_import_rows WHERE kind=:kind ORDER BY seq"),
                             {"kind": kind}, execution_options={"yield_per": 1})
    try:
        for payload in result.scalars():
            yield json.loads(payload)
    finally:
        result.close()


def create_work_tables(session):
    execute(session, """CREATE TEMP TABLE atlas_import_areas (
        seq bigint GENERATED ALWAYS AS IDENTITY, level text, code text, name text,
        ars text, ibz text, parent_code text, source_id text, attributes jsonb, geom geometry
    ) ON COMMIT DROP""")
    execute(session, "CREATE INDEX ON atlas_import_areas(level,code,seq)")
    execute(session, """CREATE TEMP TABLE atlas_import_population (
        code text, candidate boolean, value text
    ) ON COMMIT DROP""")
    execute(session, "CREATE INDEX ON atlas_import_population(code,candidate)")
    execute(session, "CREATE TEMP TABLE atlas_import_seen (source_id text PRIMARY KEY) ON COMMIT DROP")
    execute(session, """CREATE TEMP TABLE atlas_import_suspects (
        name text, lon double precision, lat double precision, PRIMARY KEY(name,lon,lat)
    ) ON COMMIT DROP""")


def remember(session, table, columns, values):
    # Table/column names are constants internal to the importer.
    return execute(session, f"INSERT INTO {table}({','.join(columns)}) VALUES "
                   f"({','.join(':'+c for c in columns)}) ON CONFLICT DO NOTHING RETURNING 1",
                   dict(zip(columns, values))).scalar() is not None


def import_areas(session, dataset, report):
    from atlas.bundle import progress
    from atlas.schemas import normalize

    progress("administrative_geometry", status="started")
    for index, area in enumerate(rows(session, "areas"), 1):
        level, code = area["level"], area["code"]
        if not isinstance(code, str) or not code.isdigit():
            raise ValueError("Amtliche Schlüssel müssen Zeichenketten sein")
        lengths = {"state": 2, "district": 5, "municipality": 8}
        if level not in lengths or len(code) != lengths[level]:
            raise ValueError("Ungültige Verwaltungsebene oder Schlüssellänge")
        validity = execute(session, """INSERT INTO atlas_import_areas(level,code,name,ars,ibz,parent_code,source_id,attributes,geom)
            VALUES(:level,:code,:name,:ars,:ibz,:parent,:source,CAST(:attributes AS jsonb),ST_SetSRID(ST_GeomFromGeoJSON(:g),4326))
            RETURNING ST_IsValid(geom) AND NOT ST_IsEmpty(geom) AND ST_SRID(geom)=4326
                AND GeometryType(geom) IN ('POLYGON','MULTIPOLYGON') AND ST_NDims(geom)=2
                AND ST_XMin(geom)>=-180 AND ST_XMax(geom)<=180 AND ST_YMin(geom)>=-85 AND ST_YMax(geom)<=85 AS valid,
                ST_IsValidReason(geom) reason,GeometryType(geom) kind,ST_NDims(geom) dimensions""",
            {"level": level, "code": code, "name": area["name"], "ars": area["ars"], "ibz": area["ibz"],
             "parent": area.get("parent_code"), "source": area["source_id"],
             "attributes": json.dumps([area["name"], area["ars"], area["ibz"]]), "g": json.dumps(area["geometry"])}).mappings().one()
        if not validity["valid"]:
            report["invalid_geometries"] += 1
            report["invalid_geometry_details"].append({"level": level, "code": code,
                                                       "source_id": area["source_id"], **dict(validity)})
            raise ValueError(f"Ungültige Verwaltungsgeometrie {level}:{code}: {validity['reason']}; keine stille Reparatur")
        if index % 1000 == 0:
            progress("administrative_geometry", source_rows=index)
    execute(session, "ANALYZE atlas_import_areas")
    # No sorting/collecting geometries across the whole country. The index finds
    # the parts for ONE identity; the union stays entirely in PostgreSQL.
    groups = session.execute(text("""SELECT DISTINCT ON (level,code)
        level,code,name,ars,ibz,parent_code,source_id,attributes FROM atlas_import_areas ORDER BY level,code,seq"""),
        execution_options={"yield_per": 100})
    try:
        for index, area in enumerate(groups.mappings(), 1):
            level, code = area["level"], area["code"]
            params = {**area, "dataset": dataset["id"], "identity": f"{level}:{code}",
                      "id": f"{dataset['id']}:{level}:{code}", "norm": normalize(area["name"]),
                      "attributes": json.dumps(area["attributes"])}
            conflict = execute(session, """SELECT EXISTS(SELECT 1 FROM atlas_import_areas
                WHERE level=:level AND code=:code AND attributes IS DISTINCT FROM CAST(:attributes AS jsonb))""", params).scalar()
            if conflict:
                raise ValueError(f"Widersprüchliche Verwaltungseinheit {level}:{code}")
            execute(session, """INSERT INTO admin_identity(id,level,code) VALUES(:identity,:level,:code)
                ON CONFLICT(id) DO NOTHING""", params)
            execute(session, """INSERT INTO admin_area(id,dataset_id,identity_id,source_id,code,ars,level,parent_code,name,normalized_name,ibz,geom)
                SELECT :id,:dataset,:identity,:source_id,:code,:ars,:level,:parent_code,:name,:norm,:ibz,
                    ST_Multi(ST_UnaryUnion(ST_Collect(geom)))
                FROM atlas_import_areas WHERE level=:level AND code=:code""", params)
            if index % 1000 == 0:
                progress("administrative_geometry", processed=index)
    finally:
        groups.close()
    progress("administrative_geometry", status="completed")


def import_population(session, dataset, report):
    from atlas.bundle import progress

    progress("population", status="started")
    batch = []
    for row in rows(session, "population"):
        if not isinstance(row["code"], str):
            raise ValueError("Einwohnerschlüssel muss Zeichenkette sein")
        if row["level"] == "municipality":
            batch.append({"code": row["code"], "candidate": row["gf"] == 4, "value": json.dumps(row["value"])})
            if len(batch) >= BATCH_ROWS:
                session.execute(text("INSERT INTO atlas_import_population VALUES(:code,:candidate,:value)"), batch)
                batch.clear()
    if batch:
        session.execute(text("INSERT INTO atlas_import_population VALUES(:code,:candidate,:value)"), batch)
    execute(session, "ANALYZE atlas_import_population")
    municipalities = session.execute(text("SELECT id,code FROM admin_area WHERE dataset_id=:dataset AND level='municipality'"),
                                     {"dataset": dataset["id"]}, execution_options={"yield_per": 100})
    try:
        for index, area in enumerate(municipalities.mappings(), 1):
            candidates = execute(session, """SELECT value FROM atlas_import_population
                WHERE code=:code AND candidate LIMIT 2""", {"code": area["code"]}).scalars().all()
            value, quality = None, "matched"
            if len(candidates) != 1:
                quality = "ambiguous" if candidates else "missing"
                report["ambiguous_population" if candidates else "missing_population"] += 1
            else:
                value = json.loads(candidates[0])
                if value is None:
                    quality = "missing"
                    report["missing_population"] += 1
                elif not isinstance(value, int) or value < 0:
                    raise ValueError("Ungültige Einwohnerzahl")
            execute(session, """INSERT INTO population(id,dataset_id,area_id,source_id,reference_date,value,quality)
                VALUES(:id,:dataset,:id,:source,:date,:value,:quality)""",
                {"id": area["id"], "dataset": dataset["id"], "source": dataset["ew_source"],
                 "date": dataset["population_date"], "value": value, "quality": quality})
            if index % 1000 == 0:
                progress("population", processed=index)
    finally:
        municipalities.close()
    report["population_unmatched"] = execute(session, """SELECT count(DISTINCT p.code) FROM atlas_import_population p
        WHERE NOT EXISTS(SELECT 1 FROM admin_area a WHERE a.dataset_id=:dataset AND a.level='municipality' AND a.code=p.code)""",
        {"dataset": dataset["id"]}).scalar()
    progress("population", status="completed")
