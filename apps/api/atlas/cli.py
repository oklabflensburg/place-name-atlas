import argparse
import hashlib
import json
from pathlib import Path
import httpx
from sqlmodel import Session, select
from atlas.importer import import_bundle, import_engine, publish
from atlas.models import Dataset


def main():
    parser=argparse.ArgumentParser(description="Ortsnamenatlas: kontrollierte lokale Datenpipeline")
    commands=parser.add_subparsers(dest="command",required=True)
    download=commands.add_parser("download")
    download.add_argument("url")
    download.add_argument("destination",type=Path)
    download.add_argument("--sha256")
    inspect=commands.add_parser("inspect")
    inspect.add_argument("path",type=Path)
    imp=commands.add_parser("import")
    imp.add_argument("path",type=Path)
    pub=commands.add_parser("publish")
    pub.add_argument("dataset")
    report=commands.add_parser("report")
    report.add_argument("dataset")
    prepare=commands.add_parser("prepare-bkg")
    prepare.add_argument("manifest",type=Path)
    prepare.add_argument("destination",type=Path)
    args=parser.parse_args()
    if args.command=="download":
        if not args.url.startswith("https://"):
            parser.error("Quellen müssen über HTTPS bezogen werden")
        if args.destination.exists():
            parser.error("Zieldatei existiert; zum Schutz vorhandener Dateien nicht überschrieben")
        args.destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=args.destination.with_suffix(args.destination.suffix+".partial")
        digest=hashlib.sha256()
        with httpx.stream("GET",args.url,follow_redirects=True,timeout=120) as response, temporary.open("wb") as out:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                digest.update(chunk);out.write(chunk)
        checksum=digest.hexdigest()
        if args.sha256 and args.sha256!=checksum:
            raise ValueError("Prüfsumme stimmt nicht überein; Datei bleibt .partial")
        temporary.rename(args.destination)
        print(json.dumps({"path":str(args.destination),"url":args.url,"sha256":checksum}))
    elif args.command=="inspect":
        import subprocess
        if args.path.suffix==".gpkg":
            subprocess.run(["ogrinfo","-so",str(args.path)],check=True)
        elif args.path.suffix.lower()==".csv":
            import csv
            with args.path.open(encoding="utf-8-sig") as f:
                reader=csv.DictReader(f,delimiter=";")
                print(json.dumps({"fields":reader.fieldnames,"sample":next(reader)},ensure_ascii=False,indent=2))
        else:
            import zipfile
            with zipfile.ZipFile(args.path) as z:
                print("\n".join(z.namelist()))
    elif args.command=="prepare-bkg":
        from atlas.bkg import prepare
        prepare(args.manifest,args.destination)
    elif args.command=="import":
        print(json.dumps(import_bundle(args.path),ensure_ascii=False,indent=2))
    elif args.command=="publish":
        publish(args.dataset)
        print(json.dumps({"published":args.dataset}))
    elif args.command=="report":
        with Session(import_engine()) as s:
            d=s.get(Dataset,args.dataset)
            if not d:
                parser.error("Datenbestand nicht gefunden")
            print(json.dumps(d.report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
