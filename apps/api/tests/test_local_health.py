"""Local ownership response, tested without a database or HTTP listener."""
import pytest
from fastapi import HTTPException
from atlas.main import instance


def test_local_identity_requires_manager(monkeypatch):
    monkeypatch.delenv('ATLAS_LOCAL_ID', raising=False)
    with pytest.raises(HTTPException) as error:
        instance()
    assert error.value.status_code == 404
    monkeypatch.setenv('ATLAS_LOCAL_ID', 'this-project')
    monkeypatch.setenv('ATLAS_LOCAL_BUILD', 'this-source')
    response = instance()
    assert response | {'pid': 'ignored'} == {
        'service': 'api', 'project': 'this-project', 'build': 'this-source', 'pid': 'ignored'}
