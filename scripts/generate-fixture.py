"""Deliberately synthetic edge cases, CC0; no claims about real places."""
import hashlib
import json
from pathlib import Path

out=Path(__file__).resolve().parents[1]/"tests/fixtures/synthetic.json"
date="2024-12-31"
sources=[]
for product in ["GN250","VG25","VG250-EW"]:
    sources.append(dict(id=f"synthetic-{product}",product=product,version="synthetic-v1",data_date=date,
        retrieved_at="2026-10-21",url="https://example.invalid/synthetic-fixture",sha256=hashlib.sha256(product.encode()).hexdigest(),
        license="CC0-1.0 (synthetic test data)",attribution="Synthetische Testdaten · Ortsnamenatlas",original_crs="EPSG:4326"))
def polygon(x1,y1,x2,y2):
    return {"type":"Polygon","coordinates":[[[x1,y1],[x2,y1],[x2,y2],[x1,y2],[x1,y1]]]}
areas=[]
for level,code,name,box in [("state","01","Testland Nord",(9,53,11,55)),("district","01001","Testkreis",(9,53,11,55)),
    ("municipality","01001001","Testbach",(9,53,10,55)),("municipality","01001002","Testingen",(10,53,11,55))]:
    areas.append(dict(level=level,code=code,name=name,ars=code.ljust(12,"0"),source_id=f"synthetic:{code}",ibz="60",geometry=polygon(*box),parent_code="01" if level=="district" else "01001" if level=="municipality" else None))
# A disconnected additional surface for the same administrative identity.
areas.append({**areas[2],"geometry":polygon(11.1,53,11.2,53.1)})
names=["Testbach","Steinach","Testingen","Testing","OTTERDORF","Mühlenbek","Muehlenbeek","Großby","Grossby","Dorf_heim","Dorf%heim","Testhausen (Nord)","Testhausen","Testhusen","Testhuusen","Testbüll","Testbüttel","=FORMULA()"]
places=[]
for i,name in enumerate(names):
    places.append(dict(source_id=f"SYNTH-{i:03d}",object_class="AX_Ortslage",name=name,
        alternatives=["Otterbach","OTTERBACH"] if i==4 else [],district=i%3==0,virtual=False,
        geometry={"type":"Point","coordinates":[9.2+(i%7)*.1,53.3+(i//7)*.2]},municipality_code="01001001"))
places.extend([
    dict(source_id="SYNTH-boundary",object_class="AX_Ortslage",name="Grenzach",geometry={"type":"Point","coordinates":[10,54]},alternatives=[],district=True),
    dict(source_id="SYNTH-water",object_class="Gewaesser",name="Otterbach",geometry={"type":"Point","coordinates":[9.5,54]}),
    dict(source_id="SYNTH-virtual",object_class="AX_Ortslage",name="Virtualhausen",virtual=True,geometry={"type":"Point","coordinates":[9.5,54]}),
    dict(source_id="SYNTH-empty",object_class="AX_Ortslage",name="",geometry={"type":"Point","coordinates":[9.5,54]})])
population=[dict(level="municipality",code="01001001",gf=4,value=1234),dict(level="municipality",code="01001001",gf=2,value=1234),dict(level="municipality",code="01001002",gf=4,value=None)]
bundle=dict(dataset=dict(id="synthetic-v1",label="Testdaten · synthetisch",synthetic=True,scope="Synthetische Sonderfälle",
    geometry_date=date,population_date=date,gn_source="synthetic-GN250",vg_source="synthetic-VG25",ew_source="synthetic-VG250-EW"),
    sources=sources,areas=areas,places=places,population=population,population_date=date,population_geometry_date=date)
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+"\n")
