"""Linux RSS/PSS measurement in a fresh worker, never publishes or resets a database."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))


def postgres_memory(pid):
    pending, seen = [pid], set()
    rss = pss = 0
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            pending.extend(map(int, Path(f"/proc/{current}/task/{current}/children").read_text().split()))
            fields = dict(line.split(":", 1) for line in Path(f"/proc/{current}/smaps_rollup").read_text().splitlines() if ":" in line)
            rss += int(fields["Rss"].split()[0])
            pss += int(fields["Pss"].split()[0])
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            return None  # Never misreport incomplete visibility as zero memory.
    return {"rss_sum_kib": rss, "pss_sum_kib": pss}


def worker(args):
    import ijson
    record = {"mode": args.mode, "file": str(args.path), "file_bytes": args.path.stat().st_size,
              "ijson_version": ijson.__version__, "ijson_backend": ijson.backend_name,
              "python_version": sys.version.split()[0], "import_completed": False}
    started = time.monotonic()
    try:
        if args.mode == "inspect":
            from atlas.bundle import inspect_bundle
            record["inspection"] = inspect_bundle(args.path)
        else:
            from sqlalchemy import create_engine, text
            from sqlalchemy.engine import make_url
            from atlas.importer import import_bundle
            url = os.environ.get("TEST_DATABASE_URL")
            if not url or not (make_url(url).database or "").startswith("atlas_test"):
                raise ValueError("Vollmessung verlangt TEST_DATABASE_URL mit atlas_test*-Datenbank in einer isolierten Instanz")
            engine = create_engine(url)
            try:
                with engine.connect() as connection:
                    directory = connection.execute(text("SHOW data_directory")).scalar()
                    if Path(directory).resolve() != args.postgres_data.resolve():
                        raise ValueError("Testverbindung und isoliertes PostgreSQL-Verzeichnis stimmen nicht überein")
                    if connection.execute(text("SELECT count(*) FROM dataset")).scalar():
                        raise ValueError("Lasttest verlangt eine neue leere Testdatenbank; vorhandene Bestände bleiben erhalten")
                    record["postgres_settings"] = {key: connection.execute(text(f"SHOW {key}")).scalar()
                                                   for key in ("shared_buffers", "work_mem", "temp_buffers", "max_connections")}
                record["report"] = import_bundle(args.path, engine)
                record["import_completed"] = True
            finally:
                engine.dispose()
    except Exception as exc:
        # Do not include DSNs or driver errors, which could contain credentials.
        record["error_type"] = type(exc).__name__
        raise
    finally:
        record["duration_seconds"] = round(time.monotonic() - started, 3)
        record["python_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        args.worker_result.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--mode", choices=("inspect", "import"), default="inspect")
    parser.add_argument("--postgres-data", type=Path, help="Verzeichnis ausschließlich der isolierten Testinstanz")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker-result", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Messung verwendet Linux ru_maxrss (KiB) und /proc PSS")
    if args.mode == "import" and not args.postgres_data:
        parser.error("Lasttests verlangen --postgres-data einer isolierten Instanz")
    if args.worker_result:
        worker(args)
        return
    pid = int((args.postgres_data / "postmaster.pid").read_text().splitlines()[0]) if args.postgres_data else None
    with tempfile.TemporaryDirectory(prefix="atlas-memory-") as temporary:
        result_path = Path(temporary) / "result.json"
        command = [sys.executable, str(Path(__file__).resolve()), str(args.path.resolve()), "--mode", args.mode,
                   "--worker-result", str(result_path)]
        if args.postgres_data:
            command += ["--postgres-data", str(args.postgres_data.resolve())]
        peaks = {"rss_sum_kib": 0, "pss_sum_kib": 0}
        samples, incomplete = 0, False
        process = subprocess.Popen(command, cwd=ROOT)
        while process.poll() is None:
            if pid:
                sample = postgres_memory(pid)
                if sample is None:
                    incomplete = True
                else:
                    samples += 1
                    for key, value in sample.items():
                        peaks[key] = max(peaks[key], value)
            time.sleep(.2)
        result = json.loads(result_path.read_text()) if result_path.exists() else {"error": "Worker ohne Ergebnis beendet"}
        result.update(exit_code=process.returncode, postgres_peak=peaks if samples else None,
                      postgres_sample_interval_seconds=.2, postgres_samples=samples, postgres_visibility_incomplete=incomplete)
        result["postgres_rss_note"] = "RSS-Summe zählt gemeinsam genutzte Seiten mehrfach; PSS ist anteilig, Stichproben können kurze Spitzen verpassen."
        if args.output:
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if process.returncode:
            raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
