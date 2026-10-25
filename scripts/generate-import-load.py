"""Generate a realistic-sized synthetic bundle without collecting a dataset in RAM."""
import argparse
import json
import math
from pathlib import Path


def generate(destination, municipalities=6000, vertices=1200, places=172403):
    base = json.loads(Path("tests/fixtures/synthetic.json").read_text())
    dataset = {**base["dataset"], "id": f"load-{municipalities}-{vertices}-{places}",
               "label": "Synthetischer Importlasttest", "synthetic": True}

    def centre(index):
        return 8 + (index % 100) * .02, 50 + (index // 100) * .02

    def areas():
        yield from (a for a in base["areas"] if a["level"] != "municipality")
        # Parts of the same municipality are separated by thousands of rows.
        for part in range(2):
            for index in range(1, municipalities + 1):
                lon, lat = centre(index)
                lon += part * .009
                ring = [[round(lon + .004 * math.cos(2 * math.pi * i / vertices), 15),
                         round(lat + .004 * math.sin(2 * math.pi * i / vertices), 15)] for i in range(vertices)]
                ring.append(ring[0])
                code = f"01{index:06d}"
                yield dict(source_id=f"area-{index}-{part}", code=code, ars=code + "0000", level="municipality",
                           parent_code=code[:5], name=f"Gemeinde {index}", ibz="60",
                           geometry={"type": "Polygon", "coordinates": [ring]})

    def population():
        for index in range(1, municipalities + 1):
            for gf in (4, 2):
                yield dict(level="municipality", code=f"01{index:06d}", gf=gf, value=index)

    def settlements():
        for index in range(places):
            municipality = index % municipalities + 1
            lon, lat = centre(municipality)
            yield dict(source_id=f"load-place-{index}", name=f"Testort {index}", alternatives=[f"Testörte {index}"],
                       object_class="AX_Ortslage" if index % 4 == 0 else "AX_Gemeinde", district=index % 8 == 0,
                       virtual=False, municipality_code=f"01{municipality:06d}",
                       geometry={"type": "Point", "coordinates": [lon, lat]})

    # Arrays deliberately precede the metadata. Only one feature/ring is live.
    with destination.open("x", encoding="utf-8") as output:
        output.write("{")
        for position, (key, values) in enumerate((("places", settlements()), ("areas", areas()), ("population", population()))):
            if position:
                output.write(",")
            output.write(json.dumps(key) + ":[")
            for index, value in enumerate(values):
                if index:
                    output.write(",")
                json.dump(value, output, ensure_ascii=False, separators=(",", ":"))
            output.write("]")
        for key, value in {"dataset": dataset, "sources": base["sources"], "population_date": base["population_date"],
                           "population_geometry_date": base["population_geometry_date"]}.items():
            output.write("," + json.dumps(key) + ":")
            json.dump(value, output, ensure_ascii=False, separators=(",", ":"))
        output.write("}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--municipalities", type=int, default=6000)
    parser.add_argument("--vertices", type=int, default=1200)
    parser.add_argument("--places", type=int, default=172403)
    args = parser.parse_args()
    if args.municipalities < 1 or args.municipalities > 999999 or args.vertices < 4 or args.places < 1:
        parser.error("Positive Orts-/Gemeindezahlen (Gemeinden höchstens 999999), mindestens 4 Ringpunkte erforderlich")
    generate(args.destination, args.municipalities, args.vertices, args.places)
    print(json.dumps({"path": str(args.destination), "bytes": args.destination.stat().st_size}))
