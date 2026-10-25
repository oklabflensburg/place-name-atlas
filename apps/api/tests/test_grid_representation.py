"""The circle wire format must not reuse an immutable polygon response."""
from types import SimpleNamespace
import json
from fastapi import Response
from atlas import main
from atlas.schemas import Filter,GridGeometry


def test_geometry_has_a_separate_representation_version_and_revalidates(monkeypatch):
    geometry=GridGeometry(dataset='published',grid=main.grid.GRID,
        viewbox=(3980000,-3040000,80000,80000),bounds=(8,50,9,51),outline='',
        cells=[dict(id='200_150',cx=4010000,cy=-3010000)])
    dataset=SimpleNamespace(id='published')
    monkeypatch.setattr(main.service,'dataset_for',lambda s,f:dataset)
    monkeypatch.setattr(main.grid,'geometry',lambda s,f,d:geometry)
    response=main.grid_geometry(None,Filter(dataset='published'),Response(),representation='circle-centers-v1')
    assert json.loads(response.body)['representation']=='circle-centers-v1'
    assert response.headers['cache-control']=='private, max-age=0, must-revalidate'
    assert response.headers['x-grid-representation']=='circle-centers-v1'
    operation=main.app.openapi()['paths']['/api/v1/grid/geometry']['get']
    assert any(p['name']=='representation' and p['schema']['const']=='circle-centers-v1' for p in operation['parameters'])
