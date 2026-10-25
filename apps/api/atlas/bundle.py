"""One-pass bundle reader: hash exactly the bytes parsed, through JSON EOF."""
import hashlib
import json
import logging
import os
from collections import Counter
from decimal import Decimal

import ijson
from ijson.common import ObjectBuilder

log = logging.getLogger("atlas.import")
ARRAYS = {"areas", "population", "places"}
METADATA = {"dataset", "sources", "population_date", "population_geometry_date",
            "administrative_source_rows", "administrative_exclusions"}


def progress(phase, **values):
    messages = {"file_check": "Dateiprüfung", "dataset_detected": "Datenkennung erkannt",
                "administrative_geometry": "Verwaltungsflächen", "population": "Einwohner",
                "settlements": "Orte", "validation": "Validierung"}
    log.warning(json.dumps({"phase": phase, "message": messages[phase], **values}, ensure_ascii=False))


class HashReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.size = 0
        self.next_progress = 32 * 1024 * 1024

    def read(self, size):
        block = self.stream.read(size)
        self.digest.update(block)
        self.size += len(block)
        if self.size >= self.next_progress:
            progress("file_check", bytes=self.size)
            self.next_progress = self.size + 32 * 1024 * 1024
        return block


def _value(events, first, build=True):
    """Build at most one array element; skip unknown fields without building them."""
    builder = ObjectBuilder() if build else None
    depth = 0
    event, value = first
    while True:
        # ijson's default keeps integer tokens as int, fractional tokens as Decimal.
        # Match json.loads: fractions become float, integer EWZ stays int. In
        # particular, 123.0 must NOT silently pass the integer population check.
        if isinstance(value, Decimal):
            value = float(value)
        if builder:
            builder.event(event, value)
        if event in ("start_map", "start_array"):
            depth += 1
        elif event in ("end_map", "end_array"):
            depth -= 1
        if depth == 0:
            return builder.value if builder else None
        event, value = next(events)


def read_bundle(path, consume=None):
    """Validate the complete JSON and return only metadata, counts and SHA-256.

    consume(kind, row) may stage rows, but must not publish/commit business data.
    Metadata may follow the arrays. Nothing is trusted until this function returns.
    """
    progress("file_check", path=str(path), status="started")
    metadata = {}
    counts = Counter()
    fields = set()
    try:
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            reader = HashReader(stream)
            events = iter(ijson.basic_parse(reader, buf_size=64 * 1024, use_float=False))
            if next(events) != ("start_map", None):
                raise ValueError("Bundle muss ein JSON-Objekt sein")
            for event, key in events:
                if event == "end_map":
                    break
                if event != "map_key" or key in fields:
                    raise ValueError("Ungültiges oder doppeltes Bundle-Feld")
                fields.add(key)
                first = next(events)
                if key in ARRAYS:
                    if first != ("start_array", None):
                        raise ValueError(f"{key} muss ein JSON-Array sein")
                    progress("file_check", section=key, status="started")
                    for first in events:
                        if first == ("end_array", None):
                            break
                        row = _value(events, first)
                        if not isinstance(row, dict):
                            raise ValueError(f"{key}: Objekt erwartet")
                        if consume:
                            consume(key, row)
                        counts[key] += 1
                        if counts[key] % 5000 == 0:
                            progress("file_check", section=key, processed=counts[key])
                else:
                    value = _value(events, first, build=key in METADATA)
                    if key in METADATA:
                        metadata[key] = value
                    if key == "dataset":
                        if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not value["id"]:
                            raise ValueError("dataset.id fehlt oder ist ungültig")
                        progress("dataset_detected", dataset=value["id"], file_checked=False)
            # Force parser EOF: catches truncated tails, trailing junk/second JSON.
            if next(events, None) is not None:
                raise ValueError("Zusätzlicher Inhalt nach dem Bundle")
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError("Bundledatei wurde während der Prüfung verändert")
    except (ijson.JSONError, StopIteration) as exc:
        raise ValueError("Beschädigtes oder abgeschnittenes JSON-Bundle") from exc
    required = ARRAYS | {"dataset", "sources", "population_date", "population_geometry_date"}
    if missing := required - fields:
        raise ValueError("Bundle-Felder fehlen: " + ", ".join(sorted(missing)))
    if not isinstance(metadata["sources"], list):
        raise ValueError("sources muss ein JSON-Array sein")
    progress("file_check", status="checked", bytes=reader.size, dataset=metadata["dataset"]["id"])
    return metadata, counts, reader.digest.hexdigest()


def inspect_bundle(path):
    metadata, counts, fingerprint = read_bundle(path)
    return {"dataset": metadata["dataset"], "sha256": fingerprint,
            "rows": dict(counts), "file_checked": True}
