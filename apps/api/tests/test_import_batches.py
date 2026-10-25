import json
from pathlib import Path

import pytest

from atlas.import_staging import BATCH_BYTES, BATCH_ROWS, stage_bundle


class BatchObserver:
    def __init__(self):
        self.batches = []

    def execute(self, statement, parameters=None):
        if parameters is not None:
            # Retain only counts, never the objects used for the memory test.
            self.batches.append((len(parameters), sum(len(p["payload"].encode("utf-8")) for p in parameters)))

    def commit(self):
        pytest.fail("Temporäre Batches dürfen keine fachlichen Zwischen-Commits auslösen")


def test_batches_bound_both_row_count_and_serialized_bytes(tmp_path):
    template = json.loads(Path("tests/fixtures/synthetic.json").read_text())
    path = tmp_path / "batch.json"
    with path.open("w") as output:
        output.write('{"places":[')
        for index in range(250):
            if index:
                output.write(",")
            # Small rows exercise count limit, large Unicode rows byte limit,
            # and one oversize feature must be flushed on its own.
            size = 10 if index < 150 else BATCH_BYTES if index == 175 else 50000
            json.dump({"source_id": str(index), "name": "ä" * size}, output, ensure_ascii=False)
        output.write("]")
        for key, value in template.items():
            if key != "places":
                output.write("," + json.dumps(key) + ":")
                json.dump(value, output)
        output.write("}")
    observer = BatchObserver()
    _, counts, _ = stage_bundle(observer, path)
    assert counts["places"] == 250
    assert len(observer.batches) > 5
    assert all(rows <= BATCH_ROWS for rows, size in observer.batches)
    assert all(size <= BATCH_BYTES or rows == 1 for rows, size in observer.batches)
    assert any(rows == BATCH_ROWS for rows, size in observer.batches)
    assert any(size > BATCH_BYTES and rows == 1 for rows, size in observer.batches)
