import copy
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import event, text

from atlas.importer import import_bundle, publish, stable_id

FIXTURE = Path("tests/fixtures/synthetic.json")


def write_bundle(tmp_path, bundle):
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(bundle, ensure_ascii=False))
    return path


def business_snapshot(db, identifier):
    with db.connect() as connection:
        return {
            "areas": connection.execute(text("""SELECT identity_id,source_id,code,ars,level,parent_code,name,normalized_name,ibz,
                ST_AsEWKT(geom) FROM admin_area WHERE dataset_id=:d ORDER BY identity_id"""), {"d": identifier}).all(),
            "population": connection.execute(text("""SELECT a.code,p.value,p.quality FROM population p JOIN admin_area a ON a.id=p.area_id
                WHERE p.dataset_id=:d ORDER BY a.code"""), {"d": identifier}).all(),
            "places": connection.execute(text("""SELECT place_id,source_id,name,kind,ST_AsEWKT(geom),assignment,candidates,
                (SELECT code FROM admin_area WHERE id=p.municipality_id) FROM place_record p WHERE dataset_id=:d ORDER BY source_id"""),
                {"d": identifier}).all(),
            "names": connection.execute(text("""SELECT p.source_id,n.original,n.normalized,n.reversed,n.primary_name
                FROM place_name n JOIN place_record p ON p.id=n.record_id WHERE p.dataset_id=:d ORDER BY p.source_id,n.original"""),
                {"d": identifier}).all(),
        }


@pytest.mark.parametrize("order", ["reverse", "arrays_first", "metadata_last"])
def test_field_order_preserves_all_business_results(db, tmp_path, order):
    baseline = import_bundle(FIXTURE, db)
    expected = business_snapshot(db, "synthetic-v1")
    bundle = json.loads(FIXTURE.read_text())
    bundle["dataset"]["id"] = "reordered"
    keys = list(bundle)
    if order == "reverse":
        keys.reverse()
    elif order == "arrays_first":
        keys.sort(key=lambda key: key not in ("places", "population", "areas"))
    else:
        keys.sort(key=lambda key: key == "dataset")
    path = write_bundle(tmp_path, {key: bundle[key] for key in keys})
    assert import_bundle(path, db) == baseline
    assert business_snapshot(db, "reordered") == expected
    with db.connect() as c:
        assert c.execute(text("SELECT fingerprint FROM dataset WHERE id='reordered'")).scalar() == hashlib.sha256(path.read_bytes()).hexdigest()
        assert c.execute(text("SELECT count(*) FROM publication")).scalar() == 0


def test_non_contiguous_parts_keep_first_source_and_same_union(db, tmp_path):
    import_bundle(FIXTURE, db)
    expected = business_snapshot(db, "synthetic-v1")
    bundle = json.loads(FIXTURE.read_text())
    bundle["dataset"]["id"] = "interleaved"
    # Place the second GF part after all other identities, preserving first part.
    areas = bundle["areas"]
    first = next(a for a in areas if a["level"] == "municipality" and a["code"] == "01001001")
    parts = [a for a in areas if a["level"] == first["level"] and a["code"] == first["code"]]
    assert len(parts) == 2
    areas.remove(parts[1])
    parts[1]["source_id"] = "later-part-must-not-become-identity-source"
    parts[1]["parent_code"] = "other-parent"
    areas.append(parts[1])
    import_bundle(write_bundle(tmp_path, bundle), db)
    assert business_snapshot(db, "interleaved") == expected


@pytest.mark.parametrize("attribute", ["name", "ars", "ibz", "ibz_type"])
def test_non_contiguous_inconsistent_parts_fail(db, tmp_path, attribute):
    bundle = json.loads(FIXTURE.read_text())
    part = copy.deepcopy(next(a for a in bundle["areas"] if a["level"] == "municipality"))
    if attribute == "ibz_type":
        part["ibz"] = int(part["ibz"])
    else:
        part[attribute] += "changed"
    bundle["areas"].append(part)
    with pytest.raises(ValueError, match="Widersprüchliche Verwaltungseinheit"):
        import_bundle(write_bundle(tmp_path, bundle), db)
    with db.connect() as c:
        for table in ("admin_area", "admin_identity", "population", "place_identity", "place_record", "place_name"):
            assert c.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0


@pytest.mark.parametrize("damage", ["truncated", "trailing", "second_json"])
def test_corrupt_json_keeps_publication_and_all_business_rows(db, tmp_path, damage):
    import_bundle(FIXTURE, db)
    publish("synthetic-v1", db)
    expected = business_snapshot(db, "synthetic-v1")
    bundle = json.loads(FIXTURE.read_text())
    bundle["dataset"]["id"] = "broken-json"
    path = write_bundle(tmp_path, bundle)
    raw = path.read_bytes()
    path.write_bytes(raw[:-1] if damage == "truncated" else raw + (b"garbage" if damage == "trailing" else b"{}"))
    with pytest.raises(ValueError):
        import_bundle(path, db)
    assert business_snapshot(db, "synthetic-v1") == expected
    with db.connect() as c:
        assert c.execute(text("SELECT dataset_id FROM publication")).scalar() == "synthetic-v1"
        assert c.execute(text("SELECT count(*) FROM dataset")).scalar() == 1
        assert c.execute(text("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND pid=pg_backend_pid()")).scalar() == 0
    # Also exercises pooled connection cleanup after failed parsing.
    assert import_bundle(FIXTURE, db)["accepted"] == 19


def test_checksum_mismatch_cannot_overwrite_report_or_publication(db, tmp_path):
    report = import_bundle(FIXTURE, db)
    publish("synthetic-v1", db)
    assert import_bundle(FIXTURE, db) == report
    path = tmp_path / "changed.json"
    path.write_bytes(FIXTURE.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="anderer Prüfsumme"):
        import_bundle(path, db)
    with db.connect() as c:
        assert c.execute(text("SELECT report FROM dataset WHERE id='synthetic-v1'")).scalar() == report
        assert c.execute(text("SELECT dataset_id FROM publication")).scalar() == "synthetic-v1"


def test_late_failure_rolls_back_batches_and_analyze_precedes_assignment(db, tmp_path):
    import_bundle(FIXTURE, db)
    publish("synthetic-v1", db)
    bundle = json.loads(FIXTURE.read_text())
    bundle["dataset"]["id"] = "late-failure"
    first = bundle["places"][0]
    bundle["places"] = [{**first, "source_id": f"new-{i}"} for i in range(250)]
    bundle["places"].append({**first, "source_id": "invalid-last", "geometry": {"type": "Point", "coordinates": [999, 54]}})
    statements = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
        if "INSERT INTO place_record" in statement and len([x for x in statements if "INSERT INTO place_record" in x]) == 150:
            with db.connect() as other:
                assert other.execute(text("SELECT count(*) FROM place_record WHERE dataset_id='late-failure'")).scalar() == 0

    event.listen(db, "before_cursor_execute", observe)
    try:
        with pytest.raises(ValueError, match="Koordinaten"):
            import_bundle(write_bundle(tmp_path, bundle), db)
    finally:
        event.remove(db, "before_cursor_execute", observe)
    assert statements.index("ANALYZE admin_area") < next(i for i, sql in enumerate(statements) if "ST_Covers" in sql)
    with db.connect() as c:
        assert c.execute(text("SELECT dataset_id FROM publication")).scalar() == "synthetic-v1"
        assert c.execute(text("SELECT count(*) FROM place_record WHERE dataset_id='late-failure'")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM place_identity WHERE id=:id"), {"id": stable_id("new-0")}).scalar() == 0
        assert c.execute(text("SELECT status FROM dataset WHERE id='late-failure'")).scalar() == "failed"


@pytest.mark.parametrize("value", [123.0, -1, "123"])
def test_streamed_invalid_population_is_still_rejected(db, tmp_path, value):
    bundle = json.loads(FIXTURE.read_text())
    bundle["population"][0]["value"] = value
    with pytest.raises(ValueError, match="Einwohnerzahl"):
        import_bundle(write_bundle(tmp_path, bundle), db)
