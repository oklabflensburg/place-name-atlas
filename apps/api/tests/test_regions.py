from sqlalchemy import text
from sqlmodel import Session, create_engine

from atlas import main, service
from atlas.schemas import Filter


def test_overview_regions_omit_municipalities_and_keep_full_listing_available():
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE admin_area (dataset_id text, identity_id text, name text, level text, code text)'))
        connection.execute(text('INSERT INTO admin_area VALUES (:dataset, :id, :name, :level, :code)'), [
            dict(dataset='published', id='municipality:01', name='A Gemeinde', level='municipality', code='01001'),
            dict(dataset='published', id='district:02', name='B Kreis', level='district', code='02'),
            dict(dataset='published', id='state:01', name='Z Land', level='state', code='01'),
            dict(dataset='published', id='district:01', name='A Kreis', level='district', code='01'),
            dict(dataset='other-version', id='state:02', name='Anderer Stand', level='state', code='02'),
        ])
    with Session(engine) as session:
        full = service.regions(session, 'published')
        overview = service.regions(session, 'published', 'overview')
        assert [r['id'] for r in full] == ['state:01', 'district:01', 'district:02', 'municipality:01']
        assert overview == full[:3]
        assert service.regions(session, 'missing', 'overview') == []
    engine.dispose()


def test_regions_scope_contract_and_forwarding(monkeypatch):
    calls = []
    monkeypatch.setattr(main.service, 'dataset_for', lambda s, f: type('Dataset', (), {'id': 'published'})())
    monkeypatch.setattr(main.service, 'regions', lambda s, d, scope: calls.append((d, scope)) or [])
    main.regions(None, Filter())
    main.regions(None, Filter(), scope='overview')
    assert calls == [('published', 'all'), ('published', 'overview')]
    operation = main.app.openapi()['paths']['/api/v1/regions']['get']
    scope = next(p['schema'] for p in operation['parameters'] if p['name'] == 'scope')
    assert scope['enum'] == ['all', 'overview'] and scope['default'] == 'all'
