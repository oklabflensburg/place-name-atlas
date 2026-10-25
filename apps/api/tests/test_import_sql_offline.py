"""Production area/population SQL in a disposable, socket-free PostGIS backend."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.geteuid() == 0 or not Path("/usr/lib/postgresql/18/bin/initdb").exists()
                    or not Path("/usr/share/postgresql/18/extension/postgis.control").exists(),
                    reason="PostgreSQL 18/PostGIS und ein Benutzer ohne Root-Rechte erforderlich")
def test_production_area_population_sql_without_sockets(tmp_path):
    output = tmp_path / "sql-check.json"
    subprocess.run([sys.executable, "scripts/check-import-sql-offline.py", "--output", str(output)],
                   check=True, capture_output=True, text=True, timeout=90)
    result = json.loads(output.read_text())
    assert len(result["cases"]) == 11
    assert all(case["passed"] for case in result["cases"])
    assert result["cases"][0]["actual"] == {"areas": 4, "total_population": 1234, "missing": 1}
    assert result["cases"][1]["actual"] == {"areas": 3, "total_population": 96326, "missing": 0}
