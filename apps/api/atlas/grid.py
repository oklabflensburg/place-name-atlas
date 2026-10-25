"""One metric geometry and one batched aggregation for all small multiples.

ST_SquareGrid and generated point indices share the EPSG:3035 origin (0,0).
Caches only contain immutable published snapshots, bounded independently per worker.
"""
from collections import OrderedDict
from threading import RLock
from concurrent.futures import Future
from collections import Counter
import hashlib
import json
from fastapi import HTTPException
from atlas.schemas import Filter, GridGeometry, GridValues, CellPlaces, GridBase, GridHit, GridCounts, StrictModel, normalize, NORMALIZATION_VERSION
from atlas.search import compile_filter, pattern_sql, group_sql
from atlas.service import rows, matches

GRID = 'laea-3035-square-20000-origin-0-v1'
SIZE = 20000
_cache = OrderedDict()
_lock = RLock()
_inflight = {}
_counts_lock = RLock()
_CACHE_BYTES = 24 * 1024 * 1024


def cached(key, build):
    with _lock:
        if key in _cache:
            value, size = _cache.pop(key)
            _cache[key] = (value, size)
            return value
        pending = _inflight.get(key)
        owner = pending is None
        if owner:
            pending = _inflight[key] = Future()
    if not owner:
        return pending.result()
    try:
        value = build()
        # Include a conservative allowance for Python strings, dicts and models.
        size = len(value.model_dump_json().encode()) * 6
        with _lock:
            _cache[key] = (value, size)
            while len(_cache)>256 or sum(v[1] for v in _cache.values()) > _CACHE_BYTES:
                _cache.popitem(last=False)
        pending.set_result(value)
        return value
    except BaseException as exc:
        pending.set_exception(exc)
        raise
    finally:
        with _lock:
            _inflight.pop(key, None)


def check_patterns(f):
    if not f.groups or any(any(p.mode != 'suffix' for p in g.patterns) or
                           any(p.mode != 'suffix' for p in g.exclusions) for g in f.groups):
        raise HTTPException(422, 'Die Rasterübersicht benötigt literale Endungen und optionale literale Varianten je Karte.')


def geometry(s, f, d):
    key = ('geometry', d.id, d.fingerprint, GRID, tuple(f.regions), f.bbox)
    def build():
        params = {'dataset': d.id, 'size': SIZE}
        selection = "level='state'"
        if f.regions:
            params['regions'] = f.regions
            selection = 'identity_id=ANY(:regions)'
        clipping = ''
        if f.bbox:
            params.update(dict(zip(('west','south','east','north'),f.bbox)))
            clipping = 'ST_Intersection(g,ST_Transform(ST_MakeEnvelope(:west,:south,:east,:north,4326),3035))'
        # Projection and display simplification are stored at import time.
        # Point-in-region predicates still use the original geom column.
        sql = f"""WITH raw_region AS (
            SELECT display_geom g
            FROM admin_area WHERE dataset_id=:dataset AND {selection}
        ), region AS MATERIALIZED (SELECT {clipping or 'g'} g FROM raw_region),
        area AS (SELECT ST_Collect(g) g FROM region),
        cells AS (SELECT c.i,c.j
            FROM area a CROSS JOIN LATERAL ST_SquareGrid(:size,ST_Envelope(a.g)) c
            WHERE EXISTS (SELECT 1 FROM region r WHERE c.geom && r.g
                AND ST_Intersects(c.geom,r.g) AND ST_Relate(c.geom,r.g,'T********')))
        SELECT jsonb_agg(jsonb_build_object('id',i::text||'_'||j::text,
            'cx',(i+0.5)*:size,'cy',-(j+0.5)*:size) ORDER BY j,i) cells,
            '' outline,
            (SELECT ARRAY[ST_XMin(g)-:size,-ST_YMax(g)-:size,
                ST_XMax(g)-ST_XMin(g)+2*:size,ST_YMax(g)-ST_YMin(g)+2*:size] FROM area) viewbox,
            (SELECT ARRAY[ST_XMin(ST_Transform(g,4326)),ST_YMin(ST_Transform(g,4326)),
                          ST_XMax(ST_Transform(g,4326)),ST_YMax(ST_Transform(g,4326))] FROM area) bounds
        FROM cells"""
        records = rows(s, sql, params)
        if not records or not records[0]['cells']:
            raise HTTPException(422, 'Für diese Region ist keine Verwaltungsgeometrie verfügbar.')
        first = records[0]
        return GridGeometry(dataset=d.id, grid=GRID, viewbox=first['viewbox'], bounds=first['bounds'],
                            outline=first['outline'], cells=first['cells'])
    return cached(key, build)


class Selection(StrictModel):
    records: dict[str,str]
    base: GridBase


def selection_key(f,d):
    return (d.id,d.fingerprint,GRID,NORMALIZATION_VERSION,tuple(f.regions),tuple(sorted(f.kinds)),f.bbox,'all-names-distinct-places-v1')


def selection(s,f,d):
    key=selection_key(f,d)
    def build():
        base,_,_,params=compile_filter(f.model_copy(update={'groups':[]}),d.id)
        record=rows(s,f"""SELECT coalesce(jsonb_object_agg(p.id,p.grid_x::text||'_'||p.grid_y::text),'{{}}'::jsonb) records
            FROM place_record p WHERE {base}""",params)[0]
        records=record['records']
        cells=Counter(records.values())
        return Selection(records=records,base=GridBase(
            dataset=d.id,grid=GRID,base_key=hashlib.sha256(json.dumps(key).encode()).hexdigest(),
            denominator=len(records),cells=[dict(id=k,denominator=v) for k,v in sorted(cells.items(),key=lambda c:tuple(map(int,c[0].split('_')[::-1])))]))
    return cached(('selection',*key),build)


def base(s,f,d):
    return selection(s,f,d).base


def pattern_key(g):
    return tuple(sorted({(p.mode,normalize(p.value)) for p in g.patterns})),tuple(sorted({(p.mode,normalize(p.value)) for p in g.exclusions}))


def counts(s,f,d):
    check_patterns(f)
    selected=selection(s,f,d)
    keys=[('hits',*selection_key(f,d),pattern_key(g)) for g in f.groups]
    # Serialize only cache misses within this worker. Identical simultaneous
    # batches share work; at most one name aggregation runs per worker.
    with _counts_lock:
        with _lock:
            missing=list(dict.fromkeys(k for k in keys if k not in _cache))
            local_results={k:_cache[k][0] for k in keys if k in _cache}
            for k in local_results:
                _cache.move_to_end(k)
        if missing:
            params={'dataset':d.id}
            queries=[]
            for i,key in enumerate(missing):
                g=f.groups[keys.index(key)]
                predicates=[pattern_sql(p,'n.normalized',f'm{i}_{j}',params) for j,p in enumerate(g.patterns)]
                exclusion=''
                if g.exclusions:
                    # Use the shared search compiler for literal exclusions.
                    excluded=g.model_copy(update={'patterns':g.exclusions,'exclusions':[]})
                    exclusion=' AND NOT '+group_sql(excluded,i,params)
                queries.append(f"""SELECT DISTINCT {i} group_index,p.id
                    FROM place_name n JOIN place_record p ON p.id=n.record_id
                    WHERE p.dataset_id=:dataset AND ({' OR '.join(predicates)}){exclusion}""")
            matches=rows(s,' UNION ALL '.join(queries),params)
            hits=[Counter() for _ in missing]
            for record in matches:
                cell=selected.records.get(record['id'])
                if cell is not None:
                    hits[record['group_index']][cell]+=1
            for key,hit in zip(missing,hits):
                result=GridHit(group='cached',total=sum(hit.values()),cells=[dict(id=k,count=v) for k,v in sorted(hit.items())])
                cached(key,lambda result=result:result)
                local_results[key]=result
        results=[local_results[key] for key in keys]
        return GridCounts(dataset=d.id,grid=GRID,base_key=selected.base.base_key,
            groups=[r.model_copy(update={'group':g.id}) for r,g in zip(results,f.groups)])


def values(s,f,d):
    """Compatibility endpoint; the overview uses base + sparse counts separately."""
    b=base(s,f,d);c=counts(s,f,d)
    lookup=[{cell.id:cell.count for cell in g.cells} for g in c.groups]
    return GridValues(dataset=d.id,grid=GRID,groups=[g.id for g in f.groups],
        denominator=b.denominator,totals=[g.total for g in c.groups],
        cells=[dict(id=cell.id,denominator=cell.denominator,counts=[m.get(cell.id,0) for m in lookup]) for cell in b.cells])


def cell_places(s, f, d, cell, group, limit, offset):
    import re
    check_patterns(f)
    if not re.fullmatch(r'-?\d{1,4}_-?\d{1,4}',cell):
        raise HTTPException(422,'Ungültige Rasterzelle')
    index = next((i for i,g in enumerate(f.groups) if g.id == group), None)
    if index is None:
        raise HTTPException(422,'Unbekannte Endungskarte')
    base, _, groups, params = compile_filter(f,d.id)
    params.update(x=int(cell.split('_')[0]),y=int(cell.split('_')[1]),limit=limit,offset=offset)
    base += ' AND p.grid_x=:x AND p.grid_y=:y'
    stat = rows(s,f'SELECT count(*) denominator,count(*) FILTER (WHERE {groups[index]}) count FROM place_record p WHERE {base}',params)[0]
    records = rows(s,f"""SELECT p.place_id id,p.name,
        ARRAY(SELECT original FROM place_name n WHERE n.record_id=p.id ORDER BY primary_name DESC,original) names
        FROM place_record p WHERE {base} AND {groups[index]}
        ORDER BY p.name COLLATE "C",p.place_id LIMIT :limit OFFSET :offset""",params)
    single=f.model_copy(update={'groups':[f.groups[index]]})
    items=[dict(id=r['id'],name=r['name'],matching_names=list(dict.fromkeys(m.name for m in matches(r['name'],r['names'],single)))) for r in records]
    return CellPlaces(dataset=d.id,cell=cell,group=group,count=stat['count'],denominator=stat['denominator'],
                      share=stat['count']/stat['denominator'] if stat['denominator'] else None,
                      limit=limit,offset=offset,items=items)
