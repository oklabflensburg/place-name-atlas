import hashlib
import json
from pathlib import Path

import pytest

from atlas.bundle import inspect_bundle, read_bundle

FIXTURE = Path("tests/fixtures/synthetic.json")


@pytest.mark.parametrize("fixture", [FIXTURE, Path("tests/fixtures/bkg-2024-flensburg.json")])
@pytest.mark.parametrize("reverse", [False, True])
def test_stream_matches_json_loads(fixture, reverse, tmp_path):
    expected = json.loads(fixture.read_text())
    bundle = dict(reversed(list(expected.items()))) if reverse else expected
    path = tmp_path / "filename-is-not-the-id.json"
    path.write_text(json.dumps(bundle, ensure_ascii=False))
    received = {key: [] for key in ("areas", "population", "places")}
    metadata, counts, checksum = read_bundle(path, lambda key, row: received[key].append(row))
    for key, rows in received.items():
        assert rows == expected[key]
        assert counts[key] == len(rows)
    assert metadata["dataset"] == expected["dataset"]
    assert checksum == hashlib.sha256(path.read_bytes()).hexdigest()
    assert inspect_bundle(path)["dataset"]["id"] == expected["dataset"]["id"]
    point = received["places"][0]["geometry"]["coordinates"]
    assert all(isinstance(x, (int, float)) for x in point)
    assert isinstance(received["population"][0]["value"], int)


def test_fractional_population_is_not_coerced_to_integer(tmp_path):
    bundle = json.loads(FIXTURE.read_text())
    bundle["population"][0]["value"] = 123.0
    path = tmp_path / "fraction.json"
    path.write_text(json.dumps(bundle))
    population = []
    read_bundle(path, lambda key, row: population.append(row) if key == "population" else None)
    assert type(population[0]["value"]) is float


@pytest.mark.parametrize("damage", ["truncated", "trailing", "second_document", "invalid_utf8", "bad_number", "duplicate_field"])
def test_invalid_json_fails_even_after_metadata_and_rows(damage, tmp_path):
    raw = FIXTURE.read_bytes()
    if damage == "truncated":
        raw = raw.rstrip()[:-1]
    elif damage == "trailing":
        raw += b"garbage"
    elif damage == "second_document":
        raw += b"{}"
    elif damage == "invalid_utf8":
        raw = raw.replace(b'"places"', b'"\xffplaces"')
    elif damage == "bad_number":
        raw = raw.rstrip()[:-1] + b',"ignored":01}'
    else:
        raw = raw.rstrip()[:-1] + b',"places":[]}'
    path = tmp_path / "broken.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        inspect_bundle(path)


def test_file_is_opened_once_and_cannot_mix_replaced_metadata(tmp_path):
    path = tmp_path / "bundle.json"
    raw = FIXTURE.read_bytes()
    path.write_bytes(raw)
    changed = False

    def replace_path(key, row):
        nonlocal changed
        if not changed:
            other = tmp_path / "replacement.json"
            other.write_text('{"dataset":{"id":"different"}}')
            other.replace(path)
            changed = True

    # Depending on the filesystem, replacing the directory entry may also change
    # the opened inode's ctime. Both rejecting the change and finishing the
    # original opened content are safe; mixing content is never allowed.
    try:
        metadata, _, checksum = read_bundle(path, replace_path)
    except ValueError as exc:
        assert "verändert" in str(exc)
    else:
        assert metadata["dataset"]["id"] == "synthetic-v1"
        assert checksum == hashlib.sha256(raw).hexdigest()


def test_in_place_modification_is_rejected(tmp_path):
    path = tmp_path / "bundle.json"
    path.write_bytes(FIXTURE.read_bytes())
    changed = False

    def change(key, row):
        nonlocal changed
        if not changed:
            with path.open("ab") as stream:
                stream.write(b" ")
            changed = True

    with pytest.raises(ValueError, match="verändert"):
        read_bundle(path, change)


def test_cli_inspect_json(capsys, monkeypatch):
    from atlas.cli import main

    monkeypatch.setattr("sys.argv", ["atlas", "inspect", str(FIXTURE)])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["dataset"]["id"] == "synthetic-v1"
    assert result["file_checked"] is True
