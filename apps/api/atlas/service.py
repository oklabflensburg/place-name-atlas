import json
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, select
from atlas.models import Dataset, Publication, SourceVersion
from atlas.schemas import (DatasetOut, Filter, GroupStatistic, Match, PlaceOut, SourceOut,
                           StatisticsOut, normalize)
from atlas.search import compile_filter, group_sql


def rows(s: Session, sql: str, params=None):
    return s.execute(text(sql), params or {}).mappings().all()


def dataset_for(s: Session, f: Filter) -> Dataset:
    identifier = f.dataset
    if identifier is None:
        current = s.get(Publication, 1)
        if not current:
            raise HTTPException(503, "Noch kein Datenbestand freigeschaltet")
        identifier = current.dataset_id
    d = s.get(Dataset, identifier)
    if d is None or d.status != "published":
        raise HTTPException(410, "Dieser Datenbestand ist nicht verfügbar. Bitte bewusst einen verfügbaren Stand wählen.")
    return d


def datasets(s):
    current = s.get(Publication, 1)
    result = []
    for d in s.exec(select(Dataset).where(Dataset.status == "published").order_by(Dataset.created_at.desc())).all():
        sources = []
        for key in [d.gn_source, d.vg_source, d.ew_source]:
            source = s.get(SourceVersion, key)
            sources.append(SourceOut(**{k: getattr(source, k) for k in SourceOut.model_fields}))
        result.append(DatasetOut(id=d.id, label=d.label, synthetic=d.synthetic, scope=d.scope,
            active=bool(current and current.dataset_id == d.id), geometry_date=d.geometry_date,
            population_date=d.population_date, sources=sources, place_count=d.report.get("accepted", 0)))
    return result


def regions(s, dataset, scope='all'):
    selection = "AND level IN ('state','district')" if scope == 'overview' else ''
    return [dict(r) for r in rows(s, f"""SELECT identity_id AS id,name,level FROM admin_area
        WHERE dataset_id=:dataset {selection}
        ORDER BY CASE level WHEN 'state' THEN 1 WHEN 'district' THEN 2 ELSE 3 END,name,code""",
        {"dataset": dataset})]


def matches(name: str, alternatives: list[str], f: Filter):
    result = []
    def hit(n, p):
        n, v = normalize(n), normalize(p.value)
        return {"suffix": n.endswith, "prefix": n.startswith, "contains": lambda v: v in n,
                "exact": lambda v: n == v}[p.mode](v)
    for g in f.groups:
        names = [name, *alternatives]
        if any(hit(n, e) for n in names for e in g.exclusions):
            continue
        for n in names:
            for p in g.patterns:
                if hit(n, p):
                    result.append(Match(group=g.id, name=n, mode=p.mode, pattern=p.value))
    return result


def place_rows(s, f: Filter, d: Dataset, limit: int, offset: int, identifier=None):
    _, where, _, params = compile_filter(f, d.id)
    if identifier:
        try:
            UUID(identifier)
        except ValueError:
            raise HTTPException(404, "Ort nicht gefunden")
        where += " AND p.place_id=:place_id"
        params["place_id"] = identifier
    params.update(limit=limit, offset=offset)
    records = rows(s, f"""SELECT p.*, ST_X(p.geom) longitude,ST_Y(p.geom) latitude,
        a.name municipality_name, pop.value population,pop.quality population_quality,
        COALESCE((SELECT jsonb_agg(n.original ORDER BY n.original) FROM place_name n
            WHERE n.record_id=p.id AND NOT n.primary_name),'[]'::jsonb) alternatives,
        COALESCE((SELECT jsonb_agg(jsonb_build_object('id',r.identity_id,'name',r.name,'level',r.level)
            ORDER BY r.level,r.code) FROM admin_area r WHERE r.dataset_id=p.dataset_id
            AND r.level IN ('state','district') AND ST_Covers(r.geom,p.geom)), '[]'::jsonb) regions
        FROM place_record p LEFT JOIN admin_area a ON a.id=p.municipality_id
        LEFT JOIN population pop ON pop.area_id=a.id AND pop.dataset_id=p.dataset_id
        WHERE {where} ORDER BY p.name COLLATE "C",p.place_id LIMIT :limit OFFSET :offset""", params)
    items = []
    for r in records:
        why = matches(r["name"], r["alternatives"], f)
        items.append(PlaceOut(id=r["place_id"], name=r["name"], kind=r["kind"], alternatives=r["alternatives"],
            longitude=r["longitude"], latitude=r["latitude"], groups=sorted({m.group for m in why}), matches=why,
            municipality={"name": r["municipality_name"], "population": r["population"],
                "population_date": d.population_date, "population_quality": r["population_quality"] or "missing"}
                if r["municipality_name"] else None,
            assignment=r["assignment"], regions=r["regions"]))
    return items


def count(s, f, d):
    _, where, _, params = compile_filter(f, d.id)
    return rows(s, f"SELECT count(*) n FROM place_record p WHERE {where}", params)[0]["n"]


def statistics(s, f, d, regional=True):
    base, where, gs, params = compile_filter(f, d.id)
    denominator = rows(s, f"SELECT count(*) n FROM place_record p WHERE {base}", params)[0]["n"]
    total = rows(s, f"SELECT count(*) n FROM place_record p WHERE {where}", params)[0]["n"]
    result = []
    for i, g in enumerate(f.groups):
        n = rows(s, f"SELECT count(*) n FROM place_record p WHERE {base} AND {gs[i]}", params)[0]["n"]
        admin_params = {"dataset": d.id}
        admin_group = group_sql(g, i, admin_params, admin=True)
        admin_where = ["a.dataset_id=:dataset", "a.level='municipality'", admin_group]
        if f.regions:
            admin_params["regions"] = f.regions
            admin_where.append("""EXISTS (SELECT 1 FROM admin_area r WHERE r.dataset_id=a.dataset_id
                AND r.identity_id=ANY(:regions) AND (r.identity_id=a.identity_id OR
                (r.level='state' AND left(a.code,2)=r.code) OR
                (r.level='district' AND left(a.code,5)=r.code)))""")
        if f.bbox:
            admin_params.update(dict(zip(("west", "south", "east", "north"), f.bbox)))
            admin_where.append("ST_Intersects(a.geom,ST_MakeEnvelope(:west,:south,:east,:north,4326))")
        p = rows(s, f"""SELECT sum(pop.value) population,count(*) municipalities,
            count(*) FILTER(WHERE pop.value IS NULL) missing FROM admin_area a
            LEFT JOIN population pop ON pop.area_id=a.id AND pop.dataset_id=a.dataset_id
            WHERE {' AND '.join(admin_where)}""", admin_params)[0]
        result.append(GroupStatistic(group=g.id, count=n, denominator=denominator,
            share=n/denominator if denominator else None,
            municipality_population=int(p["population"] or 0) if not p["missing"] else None,
            matched_municipalities=p["municipalities"], missing_population=p["missing"]))
    regional_results = []
    if regional:
        # State overview respects the selected regions through intersection with the same base predicate.
        for region in rows(s,"SELECT identity_id id,name,level FROM admin_area WHERE dataset_id=:d AND level='state' ORDER BY code",{"d":d.id}):
            local_params = dict(params, region=region["id"])
            within = """EXISTS (SELECT 1 FROM admin_area rr WHERE rr.dataset_id=p.dataset_id
                AND rr.identity_id=:region AND ST_Covers(rr.geom,p.geom))"""
            local_base = f"({base}) AND {within}"
            den = rows(s,f"SELECT count(*) n FROM place_record p WHERE {local_base}",local_params)[0]["n"]
            num = rows(s,f"SELECT count(*) n FROM place_record p WHERE ({where}) AND {within}",local_params)[0]["n"]
            if den:
                local_groups=[]
                for i,g in enumerate(f.groups):
                    n=rows(s,f"SELECT count(*) n FROM place_record p WHERE {local_base} AND {gs[i]}",local_params)[0]["n"]
                    # Population is deliberately supplied at overall selection level only.
                    local_groups.append(dict(group=g.id,count=n,denominator=den,share=n/den))
                regional_results.append({"region":dict(region),"total":num,"denominator":den,"groups":local_groups})
    return StatisticsOut(dataset=d.id,total=total,denominator=denominator,
        overlap=sum(g.count for g in result)-total if result else 0,groups=result,regions=regional_results)


def tile(s, f, d, z, x, y):
    _, where, groups, params = compile_filter(f, d.id)
    params.update(z=z,x=x,y=y,cell=40075016.68557849/(2**z*16))
    mask = " + ".join(f"CASE WHEN {sql} THEN {1<<i} ELSE 0 END" for i,sql in enumerate(groups)) or "1"
    if z < 9:
        features = f"""SELECT (hashtextextended(ST_AsText(cell)||':'||mask::text||':'||CAST(:z AS text),0) & 281474976710655)::bigint fid,
            min(public_id) public_id,mask,count(*)::integer count,ST_Centroid(ST_Collect(geom)) geom
            FROM (SELECT ST_SnapToGrid(geom,:cell) cell,public_id,mask,geom FROM points) q GROUP BY cell,mask"""
    else:
        features = "SELECT feature_id fid,public_id,mask,1::integer count,geom FROM points"
    sql = f"""WITH bounds AS (SELECT ST_TileEnvelope(:z,:x,:y) geom),
        points AS (SELECT i.feature_id,p.place_id public_id,ST_Transform(p.geom,3857) geom,({mask}) mask
            FROM place_record p JOIN place_identity i ON i.id=p.place_id,bounds b
            WHERE {where} AND p.geom && ST_Transform(ST_Expand(b.geom,
                (ST_XMax(b.geom)-ST_XMin(b.geom))*64/4096),4326)),
        features AS ({features}), mvt AS (SELECT fid,public_id,mask,count,
            ST_AsMVTGeom(f.geom,b.geom,4096,64,true) geom FROM features f,bounds b)
        SELECT ST_AsMVT(mvt,'places',4096,'geom','fid') tile FROM mvt"""
    return bytes(rows(s,sql,params)[0]["tile"])
