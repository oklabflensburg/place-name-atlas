import csv
import hashlib
import io
import json
import logging
import time
from typing import Annotated, Literal
from uuid import uuid4
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session
from atlas import service, grid
from atlas.config import settings
from atlas.db import session
from atlas.presets import PRESETS
from atlas.timing import timings
from atlas.schemas import (DatasetOut, ErrorOut, Filter, PlaceOut, PlacePage, PresetOut,
                           RegionOut, StatisticsOut, GridGeometry, GridValues, CellPlaces, GridBase, GridCounts)

app = FastAPI(title="Ortsnamenatlas", version="0.1.0", responses={
    422:{"model":ErrorOut},410:{"model":ErrorOut},503:{"model":ErrorOut}})
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("atlas.requests")
DB = Annotated[Session, Depends(session)]


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = str(uuid4())
    start = time.monotonic()
    measured = {}
    token = timings.set(measured)
    response = await call_next(request)
    total = (time.monotonic()-start)*1000
    response.headers['Server-Timing'] = ', '.join(f'{key};dur={value:.3f}' for key,value in {
        'db':measured.get('db',0),'serialize':measured.get('serialize',0),
        'processing':max(0,total-measured.get('db',0)-measured.get('serialize',0)),'app':total}.items())
    timings.reset(token)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers["X-Content-Type-Options"] = "nosniff"
    log.info(json.dumps({"request_id":request.state.request_id,"path":request.url.path,
                         "status":response.status_code,"duration_ms":round((time.monotonic()-start)*1000,2)}))
    return response


def error(request, status, code, message):
    return JSONResponse(status_code=status, content={"code":code,"message":message,
        "request_id":getattr(request.state,"request_id","")},headers={"Cache-Control":"no-store",
        "X-Request-ID":getattr(request.state,"request_id",""),"X-Content-Type-Options":"nosniff"})


@app.exception_handler(Exception)
async def unexpected_error(request,exc):
    log.error(json.dumps({"request_id":getattr(request.state,"request_id",""),"error_type":type(exc).__name__}))
    return error(request,500,"internal_error","Die Anfrage konnte nicht verarbeitet werden.")


@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    response=error(request,exc.status_code,{410:"dataset_unavailable",413:"result_too_large",404:"not_found"}.get(exc.status_code,"request_failed"),str(exc.detail))
    for key,value in (exc.headers or {}).items():response.headers[key]=value
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return error(request,422,"invalid_request","Ungültige Anfrage. Bitte Eingaben und Filter prüfen.")


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    log.error(json.dumps({"request_id":getattr(request.state,"request_id",""),"error_type":type(exc).__name__}))
    return error(request,503,"database_unavailable","Datenbankanfrage vorübergehend nicht möglich oder Zeitlimit erreicht.")


def filter_query(q: Annotated[str | None, Query(max_length=12000, description="JSON Filter v1; schema is Filter")] = None) -> Filter:
    try:
        return Filter.model_validate_json(q) if q else Filter()
    except ValidationError:
        raise HTTPException(422,"Ungültiger Filtervertrag")


F = Annotated[Filter, Depends(filter_query)]


@app.get("/health/live", operation_id="live")
def live() -> dict[str,str]:
    return {"status":"live"}


@app.get("/health/instance", operation_id="instance")
def instance() -> dict[str,str]:
    import os
    if not os.getenv('ATLAS_LOCAL_ID'):
        raise HTTPException(404, 'Keine verwaltete lokale Instanz')
    return {'service':'api','project':os.environ['ATLAS_LOCAL_ID'],
            'build':os.getenv('ATLAS_LOCAL_BUILD',''),'pid':str(os.getpid())}


@app.get("/health/ready", operation_id="ready")
def ready(s: DB) -> dict[str,str]:
    s.execute(text("SELECT PostGIS_Version()"))
    s.execute(text("SELECT grid_x,grid_y FROM place_record LIMIT 0"))
    s.execute(text("SELECT display_geom FROM admin_area LIMIT 0"))
    service.dataset_for(s,Filter())
    return {"status":"ready"}


@app.get("/api/v1/filter-schema", operation_id="filter_schema")
def filter_schema() -> dict:
    return Filter.model_json_schema()


@app.get("/api/v1/datasets",response_model=list[DatasetOut],operation_id="datasets")
def datasets(s: DB):
    return service.datasets(s)


@app.get("/api/v1/presets",response_model=list[PresetOut],operation_id="presets")
def presets():
    return PRESETS


@app.get("/api/v1/regions",response_model=list[RegionOut],operation_id="regions")
def regions(s: DB, f: F, scope: Literal['all','overview'] = 'all'):
    return service.regions(s,service.dataset_for(s,f).id,scope)


@app.get("/api/v1/boundaries",operation_id="boundaries")
def boundaries(s: DB,f: F) -> dict:
    d=service.dataset_for(s,f)
    features=service.rows(s,"""SELECT identity_id id,name,ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom,0.01)) geometry
        FROM admin_area WHERE dataset_id=:dataset AND level='state' ORDER BY code""",{"dataset":d.id})
    return {"type":"FeatureCollection","features":[{"type":"Feature","id":r["id"],
        "properties":{"name":r["name"]},"geometry":json.loads(r["geometry"])} for r in features]}


@app.get("/api/v1/places",response_model=PlacePage,operation_id="places")
def places(s: DB, f: F, limit: Annotated[int, Query(ge=1,le=100)] = 30,
           offset: Annotated[int,Query(ge=0,le=1000000)] = 0):
    d = service.dataset_for(s,f)
    return PlacePage(dataset=d.id,total=service.count(s,f,d),limit=limit,offset=offset,
                     items=service.place_rows(s,f,d,limit,offset))


def grid_headers(response, f, d):
    response.headers['Cache-Control'] = 'private, max-age=86400, immutable' if f.dataset else 'no-store'
    response.headers['X-Dataset-ID'] = d.id
    response.headers['X-Grid-ID'] = grid.GRID


@app.get('/api/v1/grid/geometry',response_model=GridGeometry,operation_id='grid_geometry')
def grid_geometry(s: DB,f: F,response: Response,
                  representation: Literal['circle-centers-v1'] = 'circle-centers-v1'):
    d=service.dataset_for(s,f)
    result=grid.geometry(s,f,d)
    response=grid_json(result,f,d)
    grid_headers(response,f,d)
    # The published dataset is immutable, the display representation is not.
    # Revalidate geometry after deployments. The representation query also
    # bypasses legacy immutable responses containing paths instead of centers.
    response.headers['Cache-Control'] = 'private, max-age=0, must-revalidate'
    response.headers['X-Grid-Representation'] = representation
    return response


@app.get('/api/v1/grid/values',response_model=GridValues,operation_id='grid_values')
def grid_values(s: DB,f: F,response: Response):
    d=service.dataset_for(s,f)
    result=grid.values(s,f,d)
    return grid_json(result,f,d)


def grid_json(result,f,d):
    start=time.perf_counter()
    content=result.model_dump_json()
    measured=timings.get()
    if measured is not None:
        measured['serialize']=(time.perf_counter()-start)*1000
    response=Response(content,media_type='application/json')
    grid_headers(response,f,d)
    return response


@app.get('/api/v1/grid/base',response_model=GridBase,operation_id='grid_base')
def grid_base(s: DB,f: F):
    d=service.dataset_for(s,f)
    return grid_json(grid.base(s,f,d),f,d)


@app.get('/api/v1/grid/counts',response_model=GridCounts,operation_id='grid_counts')
def grid_counts(s: DB,f: F):
    d=service.dataset_for(s,f)
    return grid_json(grid.counts(s,f,d),f,d)


@app.get('/api/v1/grid/cells/{cell}/places',response_model=CellPlaces,operation_id='cell_places')
def cell_places(cell: str,group: str,s: DB,f: F,
                limit: Annotated[int,Query(ge=1,le=100)]=8,
                offset: Annotated[int,Query(ge=0,le=1000000)]=0):
    d=service.dataset_for(s,f)
    return grid.cell_places(s,f,d,cell,group,limit,offset)


@app.get("/api/v1/places/{id}",response_model=PlaceOut,operation_id="place")
def place(id: str, s: DB, f: F):
    d=service.dataset_for(s,f)
    items=service.place_rows(s,f,d,1,0,id)
    if not items:
        raise HTTPException(404,"Ort in dieser Auswahl nicht gefunden")
    return items[0]


@app.get("/api/v1/statistics",response_model=StatisticsOut,operation_id="statistics")
def statistics(s: DB,f: F):
    return service.statistics(s,f,service.dataset_for(s,f))


@app.get("/api/v1/tiles/{z}/{x}/{y}.mvt", operation_id="tile",response_class=Response,
         responses={200:{"content":{"application/vnd.mapbox-vector-tile":{}}}})
def tile(z: int,x: int,y: int,s: DB,f: F,request: Request):
    if not 0 <= z <= 14 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise HTTPException(422,"Ungültige Kachelkoordinaten")
    d=service.dataset_for(s,f)
    content=service.tile(s,f,d,z,x,y)
    if len(content)>settings().tile_limit_bytes:
        raise HTTPException(413,"Kachel zu groß. Bitte Filter eingrenzen.")
    etag='"'+hashlib.sha256(content+d.id.encode()+f.model_dump_json().encode()).hexdigest()+'"'
    headers={"ETag":etag,"X-Dataset-ID":d.id,"X-Representation":"aggregated" if z<9 else "individual",
             "Cache-Control":"public, max-age=86400, immutable" if f.dataset else "no-store"}
    if request.headers.get("if-none-match")==etag:
        return Response(status_code=304,headers=headers)
    return Response(content,media_type="application/vnd.mapbox-vector-tile",headers=headers)


def csv_safe(value):
    value=str(value) if value is not None else ""
    dangerous=value.startswith(("\t","\r","\n")) or value.lstrip().startswith(("=","+","-","@"))
    return "'"+value if dangerous else value


@app.get("/api/v1/export",operation_id="export",response_class=Response,
    responses={200:{"content":{"text/csv":{},"application/geo+json":{}}}})
def export(s: DB,f: F,format: Literal["csv","geojson"]="csv"):
    d=service.dataset_for(s,f)
    if service.count(s,f,d)>settings().export_limit:
        raise HTTPException(413,f"Exportgrenze: {settings().export_limit} Orte. Bitte Filter eingrenzen.")
    places=service.place_rows(s,f,d,settings().export_limit,0)
    sources=[{"product":x.product,"version":x.version,"data_date":x.data_date,"url":x.url,"license":x.license,"attribution":x.attribution}
             for x in [s.get(service.SourceVersion,k) for k in [d.gn_source,d.vg_source,d.ew_source]]]
    if format=="geojson":
        result={"type":"FeatureCollection","dataset":d.id,"sources":sources,"features":[
            {"type":"Feature","id":p.id,"geometry":{"type":"Point","coordinates":[p.longitude,p.latitude]},
             "properties":{"name":p.name,"kind":p.kind,"groups":p.groups,"dataset":d.id}} for p in places]}
        return Response(json.dumps(result,ensure_ascii=False),media_type="application/geo+json",
            headers={"Content-Disposition":'attachment; filename="ortsnamen.geojson"'})
    out=io.StringIO(newline="")
    writer=csv.writer(out)
    writer.writerow(["place_id","name","kind","longitude","latitude","groups","dataset","sources"])
    for p in places:
        writer.writerow([csv_safe(v) for v in [p.id,p.name,p.kind,p.longitude,p.latitude,
            "|".join(p.groups),d.id,json.dumps(sources,ensure_ascii=False)]])
    return Response("\ufeff"+out.getvalue(),media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":'attachment; filename="ortsnamen.csv"'})


# q is intentionally JSON to keep the same contract in tile URLs and export links.
# Embed the precise schema for client generators as well as /filter-schema.
original_openapi=app.openapi
def openapi():
    schema=original_openapi()
    definitions=Filter.model_json_schema(ref_template="#/components/schemas/{model}")
    schema.setdefault("components",{}).setdefault("schemas",{}).update(definitions.pop("$defs",{}))
    schema["components"]["schemas"]["Filter"]=definitions
    return schema
app.openapi=openapi
