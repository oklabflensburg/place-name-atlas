import importlib.util
import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import subprocess
import sys

import pytest


@pytest.fixture
def deployment(tmp_path):
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("render_systemd", root / "scripts/render-systemd.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    project = tmp_path / "project directory"
    (project / ".venv/bin").mkdir(parents=True)
    (project / ".venv/bin/python").symlink_to(sys.executable)
    (project / "infra").mkdir()
    (project / "infra/local.json").write_text(json.dumps({"host": "127.0.0.1", "apiPort": 8765, "webPort": 3456, "nginxPort": 8181}))
    (project / ".env").write_text("DATABASE_URL=postgresql+psycopg://test-user:test-secret@127.0.0.1:5432/atlas\n")
    (project / "scripts").mkdir()
    (project / "scripts/serve-real.py").write_text("# Test entrypoint; never executed.\n")
    (project / "apps/web/.output/server").mkdir(parents=True)
    (project / "apps/web/.output/server/index.mjs").write_text("// Test entrypoint; never executed.\n")
    user = pwd.getpwuid(os.getuid()).pw_name if os.getuid() else "nobody"
    node = module.node_executable("node")
    return module, project, user, node


def test_units_use_existing_configuration_without_copying_credentials(deployment):
    module, project, user, node = deployment
    env_before = (project / ".env").read_bytes()
    config_before = (project / "infra/local.json").read_bytes()
    files = module.render(project, user, node)
    api, web = files["place-name-atlas-api.service"], files["place-name-atlas-web.service"]
    assert f'ExecStart=/usr/bin/env "PYTHONPATH={project}/apps/api"' in api
    assert f'"{project}/.venv/bin/python" "{project}/scripts/serve-real.py"' in api
    assert '"PORT=3456"' in web and '"NITRO_PORT=3456"' in web
    assert f'"{node}" --max-http-header-size=65536 "{project}/apps/web/.output/server/index.mjs"' in web
    assert "UnsetEnvironment=DATABASE_URL IMPORT_DATABASE_URL MIGRATION_DATABASE_URL" in web
    assert "proxy_pass http://127.0.0.1:8765;" in files["nginx-locations.conf"]
    assert "proxy_pass http://127.0.0.1:3456;" in files["nginx-locations.conf"]
    assert "test-secret" not in "".join(files.values())
    assert "uv sync" not in api + web and "publish" not in api + web
    assert (project / ".env").read_bytes() == env_before
    assert (project / "infra/local.json").read_bytes() == config_before


def test_start_commands_keep_bindings_and_python_path_independent_of_shell(deployment):
    module, project, user, node = deployment
    files = module.render(project, user, node)
    # Minimal executable probes exercise the generated commands without starting
    # an application or opening sockets. systemd's native parser is checked below.
    (project / "scripts/serve-real.py").write_text(
        'import json,os\nprint(json.dumps({k:os.getenv(k) for k in ["PYTHONPATH","DATABASE_URL"]}))\n')
    (project / "apps/web/.output/server/index.mjs").write_text(
        'console.log(JSON.stringify(Object.fromEntries(["HOST","PORT","NITRO_HOST","NITRO_PORT","NODE_ENV"].map(k=>[k,process.env[k]]))))\n')
    env = {**os.environ, "HOST": "0.0.0.0", "PORT": "9999", "NITRO_PORT": "9998",
           "PYTHONPATH": "/missing/module/path", "DATABASE_URL": "existing-runtime-connection"}
    results = {}
    for name in ("api", "web"):
        command = next(line.split("=", 1)[1] for line in files[f"place-name-atlas-{name}.service"].splitlines() if line.startswith("ExecStart="))
        result = subprocess.run(shlex.split(command), cwd=project, env=env, check=True, capture_output=True, text=True)
        results[name] = json.loads(result.stdout)
    assert results["api"] == {"PYTHONPATH": str(project / "apps/api"), "DATABASE_URL": "existing-runtime-connection"}
    assert results["web"] == {"HOST": "127.0.0.1", "PORT": "3456", "NITRO_HOST": "127.0.0.1", "NITRO_PORT": "3456", "NODE_ENV": "production"}


@pytest.mark.parametrize("change", [{"host": "0.0.0.0"}, {"apiPort": 3456}, {"webPort": True}])
def test_invalid_port_configuration_is_rejected_without_modification(deployment, change):
    module, project, user, node = deployment
    path = project / "infra/local.json"
    config = json.loads(path.read_text())
    path.write_text(json.dumps({**config, **change}))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="verschiedene gültige Ports"):
        module.render(project, user, node)
    assert path.read_bytes() == before


def test_systemd_checks_generated_units(deployment, tmp_path):
    if not shutil.which("systemd-analyze"):
        pytest.skip("systemd-analyze fehlt")
    module, project, user, node = deployment
    paths = []
    for name, content in module.render(project, user, node).items():
        if name.endswith(".service"):
            path = tmp_path / name
            path.write_text(content)
            paths.append(str(path))
    result = subprocess.run(["systemd-analyze", "verify", "--man=no", *paths], capture_output=True, text=True)
    errors = result.stderr.strip().splitlines()
    if result.returncode and errors and all("Operation not permitted" in line and "socket" in line and "SO_PASS" in line for line in errors):
        pytest.skip("Ausführungsrichtlinie blockiert die internen Prüfsockets von systemd-analyze")
    assert result.returncode == 0, result.stderr


def test_nginx_checks_generated_locations(deployment, tmp_path):
    nginx = shutil.which("nginx")
    if not nginx:
        pytest.skip("nginx fehlt")
    module, project, user, node = deployment
    locations = tmp_path / "locations.conf"
    locations.write_text(module.render(project, user, node)["nginx-locations.conf"])
    config = tmp_path / "nginx.conf"
    config.write_text(f'pid "{tmp_path}/nginx.pid";\nerror_log stderr;\nevents {{}}\n'
                      f'http {{ access_log off; server {{ listen unix:{tmp_path}/test.sock; include "{locations}"; }} }}\n')
    result = subprocess.run([nginx, "-t", "-p", str(tmp_path) + "/", "-c", str(config)], capture_output=True, text=True)
    blocked_socket = any(operation in result.stderr for operation in ("socket() unix:", "setsockopt(SO_REUSEADDR) unix:"))
    if result.returncode and "syntax is ok" in result.stderr and blocked_socket and "failed (1: Operation not permitted)" in result.stderr:
        pytest.skip("nginx-Syntax geprüft; Ausführungsrichtlinie blockiert den abschließenden Prüfsocket")
    assert result.returncode == 0, result.stderr
