"""Offline, transactional importer shared by CLI and tests. Never runs via HTTP."""
import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import text
from sqlmodel import Session, create_engine
from atlas.bundle import progress
from atlas.import_staging import TABLES, stage_bundle, rows, create_work_tables, import_areas, import_population, remember
from atlas.config import settings
from atlas.models import Dataset, SourceVersion
from atlas.schemas import normalize

IMPORTER_VERSION = "0.2.0"


def import_engine():
    return create_engine(settings().import_database_url or settings().database_url)


def stable_id(source_id: str):
    return str(uuid5(NAMESPACE_URL,"https://ortsnamenatlas.local/gn250/"+source_id))


def execute(s,sql,params=None):
    return s.execute(text(sql),params or {})


def import_bundle(path: Path, engine=None):
    engine = engine or import_engine()
    # The session lock covers checksum verification, diagnostic commits and the
    # single business transaction. publish's xact lock uses the same key.
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(hashtext('atlas-import'))"))
        connection.commit()
        try:
            with Session(connection) as session:
                return _import_bundle(path, session)
        finally:
            connection.rollback()
            # Temporary tables must not survive a pooled connection checkout.
            for table in TABLES:
                connection.execute(text(f"DROP TABLE IF EXISTS pg_temp.{table}"))
            connection.execute(text("SELECT pg_advisory_unlock(hashtext('atlas-import'))"))
            connection.commit()


def _import_bundle(path, s):
    execute(s, "SET LOCAL work_mem='8MB'")
    execute(s, "SET LOCAL max_parallel_workers_per_gather=0")
    bundle, counts, fingerprint = stage_bundle(s, path)
    d = bundle["dataset"]
    report = {"source_objects":counts["places"],"accepted":0,"excluded":0,"exclusion_reasons":{},
        "invalid_names":0,"invalid_geometries":0,"duplicate_suspects":0,
        "unassigned":0,"ambiguous_assignment":0,"source_spatial_disagreement":0,
        "missing_population":0,"ambiguous_population":0,"population_unmatched":0,"errors":[],
        "normalization":"nfc-casefold-ucd15.1-v1","importer_version":IMPORTER_VERSION}
    report["administrative_source_rows"]=bundle.get("administrative_source_rows",counts["areas"])
    report["administrative_exclusions"]=bundle.get("administrative_exclusions",[])
    report["invalid_geometry_details"]=[]
    old = s.get(Dataset,d["id"])
    if old:
        if old.fingerprint != fingerprint:
            raise ValueError("Kennung existiert bereits mit anderer Prüfsumme; neue Datenkennung verwenden")
        if old.status in ("validated","published"):
            progress("validation", status="idempotent", dataset=d["id"])
            return old.report
        raise ValueError("Import ist fehlgeschlagen oder unvollständig; Bericht prüfen und neue Importkennung verwenden")
    for src in bundle["sources"]:
        existing = s.get(SourceVersion,src["id"])
        if existing and any(getattr(existing,k)!=v for k,v in src.items() if k != "status"):
            raise ValueError("Quellenkennung mit widersprüchlichen Metadaten")
        if not existing:
            s.add(SourceVersion(**src,importer_version=IMPORTER_VERSION))
    s.flush()
    s.add(Dataset(**d,fingerprint=fingerprint,report=report))
    s.commit()
    try:
        execute(s,"SELECT pg_advisory_xact_lock(hashtext('atlas-import'))")
        if d["geometry_date"] != bundle["population_geometry_date"]:
            raise ValueError("Unvereinbare Gebietsstände: VG25 und VG250-EW")
        if d["population_date"] != bundle["population_date"]:
            raise ValueError("Widersprüchlicher Einwohnerstichtag")
        for key,product,expected_date in [("gn_source","GN250",None),("vg_source","VG25",d["geometry_date"]),
                                          ("ew_source","VG250-EW",d["population_date"])]:
            source=s.get(SourceVersion,d[key])
            if not source or source.product!=product or (expected_date and source.data_date!=expected_date):
                raise ValueError("Produkt oder Quellenstichtag widerspricht dem Datenmanifest")
        execute(s, "SET LOCAL work_mem='8MB'")
        execute(s, "SET LOCAL max_parallel_workers_per_gather=0")
        create_work_tables(s)
        import_areas(s, d, report)
        # New, uncommitted rows are invisible to autovacuum. Statistics are
        # essential BEFORE spatial municipality assignment.
        execute(s, 'ANALYZE admin_area')
        import_population(s, d, report)
        progress("settlements", status="started", source_objects=report["source_objects"])
        for place_index,p in enumerate(rows(s, "places"),1):
            if place_index%5000==0:
                progress("settlements", processed=place_index, accepted=report["accepted"], source_objects=report["source_objects"])
            reason=None
            if p["object_class"]!="AX_Ortslage":
                reason="not_settlement"
            elif p.get("virtual",False):
                reason="virtual_without_settlement"
            elif not p.get("name") or not p["name"].strip():
                reason="invalid_name"
                report["invalid_names"]+=1
            if reason:
                report["excluded"]+=1
                report["exclusion_reasons"][reason]=report["exclusion_reasons"].get(reason,0)+1
                continue
            if not remember(s, "atlas_import_seen", ("source_id",), (p["source_id"],)):
                report["duplicate_suspects"]+=1
                raise ValueError("Mehrfacher NNID; nicht automatisch zusammenführen")
            g=p["geometry"]
            if g.get("type")!="Point" or len(g.get("coordinates",[]))!=2:
                report["invalid_geometries"]+=1
                raise ValueError("Ortsgeometrie muss zweidimensionaler Punkt sein")
            lon,lat=g["coordinates"]
            if not (-180<=lon<=180 and -85<=lat<=85):
                report["invalid_geometries"]+=1
                raise ValueError("Koordinaten außerhalb des gültigen Bereichs")
            suspect=(normalize(p["name"]),round(lon,5),round(lat,5))
            if not remember(s, "atlas_import_suspects", ("name", "lon", "lat"), suspect):
                report["duplicate_suspects"]+=1
            pid=stable_id(p["source_id"])
            fid=int.from_bytes(hashlib.sha256(p["source_id"].encode()).digest()[:6],"big")
            execute(s,"""INSERT INTO place_identity(id,source_id,feature_id) VALUES(:id,:source,:fid)
                ON CONFLICT(id) DO NOTHING""",{"id":pid,"source":p["source_id"],"fid":fid})
            spatial=execute(s,"""SELECT id,code FROM admin_area WHERE dataset_id=:dataset AND level='municipality'
                AND ST_Covers(geom,ST_SetSRID(ST_MakePoint(:lon,:lat),4326)) ORDER BY code""",
                {"dataset":d["id"],"lon":lon,"lat":lat}).mappings().all()
            source_code=p.get("municipality_code")
            if source_code is not None and (not isinstance(source_code,str) or len(source_code)!=8):
                raise ValueError("Ungültiger GN250-AGS")
            documented=execute(s,"SELECT id FROM admin_area WHERE dataset_id=:dataset AND level='municipality' AND code=:code",
                {"dataset":d["id"],"code":source_code}).scalar() if source_code else None
            if documented and source_code in [a["code"] for a in spatial]:
                municipality,assignment=documented,"source_confirmed"
            elif len(spatial)==1:
                municipality,assignment=spatial[0]["id"],"spatial"
                if documented:
                    report["source_spatial_disagreement"]+=1
                    municipality,assignment=None,"source_spatial_conflict"
            elif len(spatial)>1:
                municipality,assignment=None,"ambiguous"
                report["ambiguous_assignment"]+=1
            else:
                municipality,assignment=None,"unassigned"
                report["unassigned"]+=1
            record_id=f"{d['id']}:{pid}"
            execute(s,"""INSERT INTO place_record(id,dataset_id,place_id,source_id,name,kind,geom,municipality_id,assignment,candidates)
                VALUES(:id,:dataset,:pid,:source,:name,:kind,ST_SetSRID(ST_MakePoint(:lon,:lat),4326),:municipality,:assignment,CAST(:candidates AS jsonb))""",
                {"id":record_id,"dataset":d["id"],"pid":pid,"source":p["source_id"],"name":p["name"],
                 "kind":"district" if p.get("district") else "settlement","lon":lon,"lat":lat,
                 "municipality":municipality,"assignment":assignment,"candidates":json.dumps([a["code"] for a in spatial])})
            names=list(dict.fromkeys([p["name"],*[n for n in p.get("alternatives",[]) if n and n.strip()]]))
            for i,n in enumerate(names):
                execute(s,"""INSERT INTO place_name(id,record_id,original,normalized,reversed,primary_name)
                    VALUES(:id,:record,:original,:normalized,:reverse,:primary)""",
                    {"id":f"{record_id}:{i}","record":record_id,"original":n,"normalized":normalize(n),"reverse":normalize(n)[::-1],"primary":i==0})
            report["accepted"]+=1
        progress("validation", status="started", accepted=report["accepted"])
        if not report["accepted"]:
            raise ValueError("Keine gültigen Ortsobjekte")
        previous=execute(s,"SELECT d.report FROM dataset d JOIN publication p ON p.dataset_id=d.id WHERE p.id=1").scalar()
        report["previous_accepted"]=previous.get("accepted") if previous else None
        report["accepted_delta"]=report["accepted"]-previous["accepted"] if previous else None
        report["removed_source_ids"]=execute(s,"""SELECT count(*) FROM place_record p JOIN publication pub ON p.dataset_id=pub.dataset_id
            WHERE NOT EXISTS(SELECT 1 FROM place_record n WHERE n.dataset_id=:d AND n.place_id=p.place_id)""",{"d":d["id"]}).scalar()
        report["new_source_ids"]=execute(s,"""SELECT count(*) FROM place_record n WHERE n.dataset_id=:d AND NOT EXISTS
            (SELECT 1 FROM place_record p JOIN publication pub ON p.dataset_id=pub.dataset_id WHERE p.place_id=n.place_id)""",{"d":d["id"]}).scalar()
        changes=execute(s,"""SELECT count(*) FILTER(WHERE n.name<>p.name) names,
            count(*) FILTER(WHERE NOT ST_Equals(n.geom,p.geom)) positions FROM place_record n
            JOIN place_record p ON p.place_id=n.place_id JOIN publication pub ON pub.dataset_id=p.dataset_id
            WHERE n.dataset_id=:d""",{"d":d["id"]}).mappings().one()
        report["changed_names"]=changes["names"]
        report["changed_positions"]=changes["positions"]
        report["status"]="validated"
        dataset=s.get(Dataset,d["id"])
        dataset.status="validated"
        dataset.report=report
        s.add(dataset)
        s.commit()
    except Exception as exc:
        report["status"]="failed"
        report["errors"].append(str(exc))
        s.rollback()
        dataset=s.get(Dataset,d["id"])
        dataset.status="failed"
        dataset.report=report
        s.add(dataset)
        s.commit()
        raise
    for table in ("place_record", "place_name", "admin_area"):
        execute(s, f"ANALYZE {table}")
    s.commit()
    progress("validation", status="validated", dataset=d["id"], accepted=report["accepted"])
    return report


def publish(identifier: str, engine=None):
    with Session(engine or import_engine()) as s:
        execute(s,"SELECT pg_advisory_xact_lock(hashtext('atlas-import'))")
        d=s.get(Dataset,identifier)
        if not d or d.status not in ("validated","published"):
            raise ValueError("Nur erfolgreich validierte Datenbestände sind freischaltbar")
        if d.report.get("ambiguous_population") or d.report.get("errors"):
            raise ValueError("Qualitätsbericht enthält blockierende Fehler")
        d.status="published"
        s.add(d)
        execute(s,"""INSERT INTO publication(id,dataset_id) VALUES(1,:d)
            ON CONFLICT(id) DO UPDATE SET dataset_id=excluded.dataset_id""",{"d":identifier})
        execute(s,"UPDATE source_version SET status='validated' WHERE id IN (:gn,:vg,:ew)",
                {"gn":d.gn_source,"vg":d.vg_source,"ew":d.ew_source})
        s.commit()
