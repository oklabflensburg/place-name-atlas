"""Fail-closed adapter for the inspected BKG 2024-12 CSV/GPKG schemas.

GDAL is a CLI dependency, not a second application service. No automatic schema guessing.
"""
import csv
import hashlib
import json
import sqlite3
import subprocess
import zipfile
import zlib
from collections import Counter
from pathlib import Path


def sha256(path):
    digest=hashlib.sha256()
    with path.open("rb") as f:
        while block:=f.read(1024*1024):digest.update(block)
    return digest.hexdigest()


def features(path,layer=None,where=None,csv_points=False):
    command=["ogr2ogr","-f","GeoJSONSeq","/vsistdout/",str(path)]
    if layer:command.append(layer)
    if csv_points:
        command += ["-oo","SEPARATOR=SEMICOLON","-oo","AUTODETECT_TYPE=NO",
                    "-oo","X_POSSIBLE_NAMES=RECHTS","-oo","Y_POSSIBLE_NAMES=HOCH","-s_srs","EPSG:25832"]
    # GeoJSONSeq defaults to 7 decimals; rounding dense VG25 rings can introduce crossings.
    command += ["-t_srs","EPSG:4326","-lco","COORDINATE_PRECISION=15"]
    if where:command += ["-where",where]
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8")
    for line in process.stdout:
        if line.strip():yield json.loads(line.lstrip("\x1e"))
    errors=process.stderr.read()
    if process.wait()!=0:raise ValueError("GDAL-Konvertierung fehlgeschlagen: "+errors[-2000:])


def gpkg_layer(path,expected,required):
    with sqlite3.connect(f"file:{path}?mode=ro",uri=True) as c:
        layers={row[0].upper():row[0] for row in c.execute("SELECT table_name FROM gpkg_contents")}
        if expected not in layers:raise ValueError(f"Geprüfte Ebene {expected} fehlt: {sorted(layers)}")
        layer=layers[expected]
        fields={r[1].upper() for r in c.execute('PRAGMA table_info("'+layer.replace('"','""')+'")')}
        if not set(required)<=fields:raise ValueError(f"Schemaänderung in {layer}: erforderliche Attribute fehlen")
        crs=c.execute("SELECT srs_id FROM gpkg_geometry_columns WHERE table_name=?",(layer,)).fetchone()
        if not crs or crs[0]!=25832:raise ValueError("Dieser geprüfte Adapter verlangt EPSG:25832")
    return layer


def prepare(manifest_path:Path,destination:Path):
    manifest=json.loads(manifest_path.read_text())
    if destination.exists():raise ValueError("Vorhandenes Importbundle wird nicht überschrieben")
    products={s["product"]:s for s in manifest["sources"]}
    if set(products)!={"GN250","VG25","VG250-EW"}:raise ValueError("Genau GN250, VG25 und VG250-EW sind erforderlich")
    paths={}
    for product,source in products.items():
        archive=manifest_path.parent/source["archive"]
        if sha256(archive)!=source["sha256"]:raise ValueError("Archiv-Prüfsumme stimmt nicht: "+product)
        paths[product]=manifest_path.parent/source["path"]
        if not paths[product].is_file():raise ValueError("Entpackte Quelldatei fehlt: "+product)
        with zipfile.ZipFile(archive) as z:
            entries=[i for i in z.infolist() if Path(i.filename).name==paths[product].name]
            if len(entries)!=1:raise ValueError("Quelldatei ist im Archiv nicht eindeutig enthalten")
            crc=0
            with paths[product].open('rb') as f:
                while chunk:=f.read(1024*1024):crc=zlib.crc32(chunk,crc)
            if paths[product].stat().st_size!=entries[0].file_size or crc!=entries[0].CRC:
                raise ValueError("Entpackte Datei widerspricht dem geprüften Originalarchiv")
        if source["original_crs"]!="EPSG:25832":raise ValueError("Nicht geprüftes Quell-CRS")
    vgdate=products["VG25"]["data_date"]
    ewdate=products["VG250-EW"]["data_date"]
    if vgdate!=manifest["population_geometry_date"]:raise ValueError("Unvereinbare VG25-/VG250-EW-Gebietsstände")
    subset=manifest.get("municipalities",[])
    if any(not isinstance(code,str) or len(code)!=8 or not code.isdigit() for code in subset):
        raise ValueError("Ungültiger AGS im Ausschnitt")
    if subset and not manifest.get("scope"):raise ValueError("Ein Ausschnitt braucht eine sichtbare Gebietsbezeichnung")
    # Exactly the NAME/NAME2 fields; ZUSATZ is never stripped from NAME.
    with paths["GN250"].open(encoding="utf-8-sig") as f:
        fields=csv.DictReader(f,delimiter=";").fieldnames
    if not set(["NNID","NAME","NAME2","OBA","GEMTEIL","VIRTUELL","AGS","RECHTS","HOCH"])<=set(fields or []):
        raise ValueError("GN250-CSV-Schema hat sich geändert")
    where="AGS IN ("+",".join("'"+c+"'" for c in subset)+")" if subset else None
    places=[]
    for feature in features(paths["GN250"],where=where,csv_points=True):
        p={k.upper():v for k,v in feature["properties"].items()}
        if p["GEMTEIL"] not in ("Ja","Nein",None,"") or p["VIRTUELL"] not in ("Ja","Nein",None,""):
            raise ValueError("Unbekannte GN250-Ja/Nein-Klassifikation")
        places.append(dict(source_id=p["NNID"],name=p["NAME"],alternatives=[p["NAME2"]] if p["NAME2"] else [],
            object_class=p["OBA"],district=p["GEMTEIL"]=="Ja",virtual=p["VIRTUELL"]=="Ja",
            municipality_code=p["AGS"] or None,geometry=feature["geometry"]))
    areas=[]
    administrative_exclusions=[]
    administrative_source_rows=0
    for layer,level,length in [("VG25_LAN","state",2),("VG25_KRS","district",5),("VG25_GEM","municipality",8)]:
        real_layer=gpkg_layer(paths["VG25"],layer,["OBJID","AGS","ARS","GEN","IBZ","GF","BSG"])
        selected={c[:length] for c in subset}
        area_where="AGS IN ("+",".join("'"+c+"'" for c in sorted(selected))+")" if selected else None
        for feature in features(paths["VG25"],real_layer,where=area_where):
            p={k.upper():v for k,v in feature["properties"].items()}
            code=p["AGS"]
            if not isinstance(code,str):raise ValueError("VG25-AGS ist kein Text")
            if selected and code not in selected:continue
            administrative_source_rows+=1
            if p["BSG"]!=1:
                reason={2:"joint_sovereignty_not_municipality",9:"bodensee_without_administrative_structure"}.get(p["BSG"])
                if not reason:raise ValueError("Unbekannte VG25-BSG-Klassifikation")
                administrative_exclusions.append(dict(level=level,code=code,name=p["GEN"],reason=reason))
                continue
            areas.append(dict(source_id=p["OBJID"],code=code,ars=p["ARS"],
                level=level,parent_code=code[:5] if level=="municipality" else code[:2] if level=="district" else None,
                name=p["GEN"],ibz=str(p["IBZ"]),geometry=feature["geometry"]))
    ew_layer=gpkg_layer(paths["VG250-EW"],"VG250_GEM",["AGS","GF","EWZ"])
    population=[]
    # GPKG attributes are read without interpreting SQLite integers as geographic keys.
    with sqlite3.connect(f"file:{paths['VG250-EW']}?mode=ro",uri=True) as c:
        for code,gf,value in c.execute('SELECT AGS,GF,EWZ FROM "'+ew_layer+'"'):
            if not isinstance(code,str):raise ValueError("VG250-EW-AGS ist kein Text")
            if subset and code not in subset:continue
            population.append(dict(level="municipality",code=code,gf=int(gf),value=None if value is None or value<0 else int(value)))
    sources=[{k:v for k,v in s.items() if k not in ("path","archive")} for s in manifest["sources"]]
    bundle={"dataset":dict(id=manifest["id"],label=manifest["label"],synthetic=False,
        scope=manifest.get("scope","Deutschland"),geometry_date=vgdate,population_date=ewdate,
        gn_source=products["GN250"]["id"],vg_source=products["VG25"]["id"],ew_source=products["VG250-EW"]["id"]),
        "sources":sources,"places":places,"areas":areas,"population":population,"population_date":ewdate,
        "population_geometry_date":manifest["population_geometry_date"],
        "administrative_source_rows":administrative_source_rows,"administrative_exclusions":administrative_exclusions}
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(bundle,ensure_ascii=False,separators=(",",":"))+"\n")
    print(json.dumps({"prepared":str(destination),"sha256":sha256(destination),"objects":len(places),"area_rows":len(areas)}))
