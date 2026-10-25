"""Create the selected 2024 manifest from verified local BKG archives and date files."""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
import zipfile

parser=argparse.ArgumentParser();parser.add_argument("directory",type=Path);args=parser.parse_args()
base=args.directory.resolve();target=base/"manifest.json"
if target.exists():parser.error("Vorhandenes Manifest wird nicht überschrieben")
sources=[]
for short,product,url in [
    ("gn","GN250","https://daten.gdz.bkg.bund.de/produkte/sonstige/gn250/2024/gn250.utm32s.csv.zip"),
    ("vg25","VG25","https://daten.gdz.bkg.bund.de/produkte/vg/vg25_ebenen/2024-12/vg25.utm32s.gpkg.zip"),
    ("ew","VG250-EW","https://daten.gdz.bkg.bund.de/produkte/vg/vg250-ew_ebenen_1231/2024/vg250-ew_12-31.utm32s.gpkg.ebenen.zip")]:
    archive=base/(short+".zip")
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip()
        if bad:parser.error("Beschädigtes Archiv: "+str(bad))
        dates=[z.read(name).decode("utf-8-sig").strip() for name in z.namelist() if name.lower().endswith("aktualitaet.txt")]
        if not dates or not all("31.12.2024" in d for d in dates):
            parser.error("Nicht geprüfter Gebietsstand: "+product+" "+repr(dates))
    found=list((base/short).rglob("GN250.csv" if short=="gn" else "*.gpkg"))
    if len(found)!=1:parser.error("Genau eine entpackte Quelldatei erforderlich: "+product)
    digest=hashlib.sha256()
    with archive.open("rb") as f:
        while block:=f.read(1024*1024):digest.update(block)
    license_id="CC-BY-4.0" if product=="VG25" else "dl-de/by-2-0"
    license_label="CC BY 4.0" if product=="VG25" else "dl-de/by-2-0"
    credits={"GN250":"datenquellen_gn250.pdf","VG25":"datenquellen_vg25.pdf","VG250-EW":"datenquellen_vg_nuts.pdf"}[product]
    sources.append(dict(id=f"{short}-2024-{digest.hexdigest()[:12]}",product=product,version="2024-12",
        data_date="2024-12-31",retrieved_at=date.today().isoformat(),url=url,sha256=digest.hexdigest(),
        license=license_id,attribution=f"© BKG ({date.today().year}) {license_label}, Datenquellen: https://sgx.geodatenzentrum.de/web_public/gdz/datenquellen/{credits} · {product}",
        original_crs="EPSG:25832",archive=archive.name,path=str(found[0].relative_to(base))))
manifest=dict(id="bkg-2024",label="BKG · Deutschland · 2024",scope="Deutschland",
              population_geometry_date="2024-12-31",sources=sources)
target.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
print(target)
