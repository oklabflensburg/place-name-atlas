"""Real subprocess RSS checks. Large inputs are written one feature at a time."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]


def generate(path, municipalities):
    subprocess.run([sys.executable, str(ROOT / "scripts/generate-import-load.py"), str(path),
                    "--municipalities", str(municipalities), "--vertices", "600", "--places", "20000"],
                   cwd=ROOT, check=True, capture_output=True, text=True)


def measure(path, output, *extra):
    subprocess.run([sys.executable, str(ROOT / "scripts/measure-import-memory.py"), str(path),
                    "--output", str(output), *extra], cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(output.read_text())


@pytest.mark.skipif(sys.platform != "linux", reason="Linux RSS in KiB erforderlich")
def test_streaming_rss_does_not_scale_with_total_geometry(tmp_path):
    small = tmp_path / "small.json"
    large = tmp_path / "large.json"
    generate(small, 20)
    generate(large, 1600)
    assert large.stat().st_size > 64 * 1024 * 1024
    before = measure(small, tmp_path / "small-rss.json")
    after = measure(large, tmp_path / "large-rss.json")
    assert after["inspection"]["rows"] == {"places": 20000, "areas": 3202, "population": 3200}
    assert after["python_peak_rss_kib"] < 256 * 1024
    assert after["python_peak_rss_kib"] - before["python_peak_rss_kib"] < 32 * 1024
    assert after["import_completed"] is False  # A parser check cannot claim a real import.


@pytest.mark.skipif(os.getenv("ATLAS_IMPORT_LOAD_TEST") != "1", reason="Opt-in Lasttest nur in isolierter PostgreSQL-Instanz")
def test_full_import_rss_in_isolated_postgres(db, tmp_path):
    directory = os.environ.get("ATLAS_TEST_POSTGRES_DATA")
    if not directory:
        pytest.fail("ATLAS_TEST_POSTGRES_DATA der isolierten Instanz erforderlich")
    path = tmp_path / "load.json"
    generate(path, 1600)
    result = measure(path, tmp_path / "import-rss.json", "--mode", "import", "--postgres-data", directory)
    assert result["import_completed"] is True
    assert result["report"]["accepted"] == 5000
    assert result["report"]["excluded"] == 15000
    assert result["python_peak_rss_kib"] < 512 * 1024
    assert result["postgres_peak"] is not None
