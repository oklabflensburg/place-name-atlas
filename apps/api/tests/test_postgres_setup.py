import importlib.util
import json
import stat
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest


@pytest.fixture
def setup(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("postgres_setup", root / "scripts/setup-postgres.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / ".env.example").write_text((root / ".env.example").read_text())
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module.shutil, "which", lambda program: f"/usr/bin/{program}")
    return module


def state(**changes):
    return json.dumps({"version": 180006, "owner": None, "extensions": 2,
                       "elevated_roles": 0, "memberships": 0, **changes})


def test_credentials_are_private_independent_and_preserved(setup):
    urls = setup.configuration()
    assert len({url.password for url in urls.values()}) == 3
    assert all(len(url.password) >= 32 for url in urls.values())
    path = setup.ROOT / ".env"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    before = path.read_bytes()
    assert setup.configuration() == urls
    assert path.read_bytes() == before


def test_existing_configuration_for_another_server_is_preserved(setup, monkeypatch):
    path = setup.ROOT / ".env"
    content = (setup.ROOT / ".env.example").read_text().replace(":5432/atlas", ":55439/atlas_dev")
    path.write_text(content)
    monkeypatch.setattr(sys, "argv", ["setup-postgres.py"])
    monkeypatch.setattr(setup, "admin", lambda *args: pytest.fail("Keine Datenbankänderung bei falschem Ziel"))
    with pytest.raises(ValueError, match="5432/atlas"):
        setup.main()
    assert path.read_text() == content


@pytest.mark.parametrize("changes", [{"owner": "another_project"}, {"elevated_roles": 1},
                                    {"memberships": 1}, {"extensions": 1}])
def test_conflicts_abort_before_database_changes(setup, monkeypatch, changes):
    calls = []

    def admin(statement, database="postgres"):
        calls.append(statement)
        return state(**changes)

    monkeypatch.setattr(setup, "admin", admin)
    monkeypatch.setattr(sys, "argv", ["setup-postgres.py"])
    with pytest.raises(ValueError):
        setup.main()
    assert len(calls) == 1
    assert calls[0].lstrip().startswith("SELECT")


def test_restore_does_not_overwrite_existing_tables(setup, monkeypatch):
    backup = setup.ROOT / "backup.dump"
    backup.write_bytes(b"test archive")
    replies = iter([state(owner="atlas_owner"), "", "1"])
    monkeypatch.setattr(setup, "admin", lambda *args: next(replies))
    monkeypatch.setattr(setup, "connect", lambda url: nullcontext())
    monkeypatch.setattr(setup.subprocess, "run", lambda *args, **kwargs: pytest.fail("Kein Restore über bestehende Tabellen"))
    monkeypatch.setattr(sys, "argv", ["setup-postgres.py", "--restore", str(backup)])
    with pytest.raises(ValueError, match="leere Datenbank"):
        setup.main()


def test_restore_uses_transaction_and_migrates_with_owner_credentials(setup, monkeypatch):
    backup = setup.ROOT / "backup.dump"
    backup.write_bytes(b"test archive")
    replies = iter([state(), "", "0", ""])
    monkeypatch.setattr(setup, "admin", lambda *args: next(replies))

    class Connection:
        rows = iter([("0003",), (False,), ("bkg-2024-r3",), (45858,)])

        def execute(self, *args):
            return self

        def fetchone(self):
            return next(self.rows)

    connections = iter([None, None, None, Connection()])
    monkeypatch.setattr(setup, "connect", lambda url: nullcontext(next(connections)))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "pg_restore" in command:
            assert kwargs["stdin"].read() == b"test archive"
            assert "--single-transaction" in command and "--no-owner" in command
            assert "--clean" not in command
        else:
            assert command[-3:] == ["alembic", "upgrade", "head"]
            assert "atlas_owner:" in kwargs["env"]["MIGRATION_DATABASE_URL"]
            assert "127.0.0.1:5432/atlas" in kwargs["env"]["DATABASE_URL"]

    monkeypatch.setattr(setup.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["setup-postgres.py", "--restore", str(backup)])
    setup.main()
    assert len(calls) == 2
