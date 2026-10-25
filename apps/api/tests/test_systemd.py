import importlib.util
import errno
import http.client
import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
    (project / "infra/local.json").write_text(json.dumps({"host": "127.0.0.1", "apiPort": 8000, "webPort": 3000, "nginxPort": 8080}))
    (project / "infra/systemd").mkdir()
    (project / "infra/systemd/production.json").write_text(json.dumps({"host": "127.0.0.1", "apiPort": 8765, "webPort": 3456, "domain": "atlas.example.test"}))
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
    production_before = (project / "infra/systemd/production.json").read_bytes()
    files = module.render(project, user, node)
    api, web = files["place-name-atlas-api.service"], files["place-name-atlas-web.service"]
    assert f'"PYTHONPATH={project}/apps/api"' in api
    assert f'ExecStart=/usr/bin/env "ATLAS_LOCAL_CONFIG={project}/infra/systemd/production.json"' in api
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
    assert (project / "infra/systemd/production.json").read_bytes() == production_before


def test_start_commands_keep_bindings_and_python_path_independent_of_shell(deployment):
    module, project, user, node = deployment
    files = module.render(project, user, node)
    # Minimal executable probes exercise the generated commands without starting
    # an application or opening sockets. systemd's native parser is checked below.
    (project / "scripts/serve-real.py").write_text(
        'import json,os\nprint(json.dumps({k:os.getenv(k) for k in ["PYTHONPATH","DATABASE_URL","ATLAS_LOCAL_CONFIG"]}))\n')
    (project / "apps/web/.output/server/index.mjs").write_text(
        'console.log(JSON.stringify(Object.fromEntries(["HOST","PORT","NITRO_HOST","NITRO_PORT","NODE_ENV"].map(k=>[k,process.env[k]]))))\n')
    env = {**os.environ, "HOST": "0.0.0.0", "PORT": "9999", "NITRO_PORT": "9998",
           "PYTHONPATH": "/missing/module/path", "DATABASE_URL": "existing-runtime-connection", "ATLAS_LOCAL_CONFIG": "/wrong/profile.json"}
    results = {}
    for name in ("api", "web"):
        command = next(line.split("=", 1)[1] for line in files[f"place-name-atlas-{name}.service"].splitlines() if line.startswith("ExecStart="))
        result = subprocess.run(shlex.split(command), cwd=project, env=env, check=True, capture_output=True, text=True)
        results[name] = json.loads(result.stdout)
    assert results["api"] == {"PYTHONPATH": str(project / "apps/api"), "DATABASE_URL": "existing-runtime-connection", "ATLAS_LOCAL_CONFIG": str(project / "infra/systemd/production.json")}
    assert results["web"] == {"HOST": "127.0.0.1", "PORT": "3456", "NITRO_HOST": "127.0.0.1", "NITRO_PORT": "3456", "NODE_ENV": "production"}


@pytest.mark.parametrize("change", [{"host": "0.0.0.0"}, {"apiPort": 3456}, {"webPort": True}])
def test_invalid_port_configuration_is_rejected_without_modification(deployment, change):
    module, project, user, node = deployment
    path = project / "infra/systemd/production.json"
    config = json.loads(path.read_text())
    path.write_text(json.dumps({**config, **change}))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="verschiedene gültige Ports"):
        module.render(project, user, node)
    assert path.read_bytes() == before


def test_actual_production_profile_has_own_ports_and_domain(deployment):
    module, project, user, node = deployment
    profile = module.ROOT / "infra/systemd/production.json"
    files = module.render(project, user, node, config_path=profile)
    assert '"PORT=3015"' in files["place-name-atlas-web.service"]
    assert "proxy_pass http://127.0.0.1:8015;" in files["nginx-locations.conf"]
    assert "server_name ortsnamenatlas.oklabflensburg.de;" in files["nginx-site.https.conf"]


def test_backend_launcher_honours_explicit_profile(deployment, monkeypatch):
    from types import SimpleNamespace
    module, project, _, _ = deployment
    calls = []
    monkeypatch.setenv("ATLAS_LOCAL_CONFIG", str(project / "infra/systemd/production.json"))
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=lambda *a, **kw: calls.append((a, kw))))
    spec = importlib.util.spec_from_file_location("serve_real_profile", module.ROOT / "scripts/serve-real.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    assert calls[0][0] == ("atlas.main:app",)
    assert calls[0][1]["host"] == "127.0.0.1" and calls[0][1]["port"] == 8765


@pytest.mark.parametrize("domain", ["bad.example; return 200;", "https://example.test", "example.test/path", "*.example.test", "example.test\n", "127.0.0.1"])
def test_domain_cannot_inject_nginx_directives(deployment, domain):
    module, project, user, node = deployment
    with pytest.raises(ValueError, match="DNS-Hostname"):
        module.render(project, user, node, domain=domain)


def test_existing_certificate_paths_are_explicit_and_not_read(deployment):
    module, project, user, node = deployment
    files = module.render(project, user, node, tls_certificate=Path("/not-readable/wildcard/fullchain.pem"),
                          tls_certificate_key=Path("/not-readable/wildcard/privkey.pem"))
    assert 'ssl_certificate "/not-readable/wildcard/fullchain.pem";' in files["nginx-site.https.conf"]
    with pytest.raises(ValueError, match="gemeinsam"):
        module.render(project, user, node, tls_certificate=Path("/certificate.pem"))
    with pytest.raises(ValueError, match="nginx-Pfade"):
        module.render(project, user, node, nginx_snippet=Path("/etc/$unexpected/nginx.conf"))


def test_renewal_hook_ignores_other_certificates(deployment, tmp_path):
    module, project, user, node = deployment
    hook = tmp_path / "hook.sh"
    hook.write_text(module.render(project, user, node)["certbot-deploy-hook.sh"])
    subprocess.run(["sh", "-n", str(hook)], check=True)
    # The early exit must avoid both nginx validation and systemctl reload.
    result = subprocess.run(["sh", str(hook)], env={**os.environ, "RENEWED_LINEAGE": "/another/certificate"},
                            check=True, capture_output=True, text=True)
    assert not result.stdout and not result.stderr


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
    check_nginx(result)


def check_nginx(result):
    blocked_socket = any(operation in result.stderr for operation in ("socket() unix:", "setsockopt(SO_REUSEADDR) unix:"))
    if result.returncode and "syntax is ok" in result.stderr and blocked_socket and "failed (1: Operation not permitted)" in result.stderr:
        pytest.skip("nginx-Syntax geprüft; Ausführungsrichtlinie blockiert den abschließenden Prüfsocket")
    assert result.returncode == 0, result.stderr


def certificate(tmp_path):
    if not shutil.which("openssl"):
        pytest.skip("openssl fehlt")
    cert, key = tmp_path / "certificate.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", "/CN=atlas.example.test", "-keyout", str(key), "-out", str(cert)],
                   check=True, capture_output=True, text=True)
    return cert, key


def site_files(deployment, tmp_path, kind, http_listener, https_listener, **overrides):
    module, project, user, node = deployment
    cert, key = certificate(tmp_path)
    locations = tmp_path / "locations.conf"
    files = module.render(project, user, node, tls_certificate=cert, tls_certificate_key=key,
                          nginx_snippet=locations, acme_webroot=tmp_path / "acme", **overrides)
    locations.write_text(files["nginx-locations.conf"])
    site = files[f"nginx-site.{kind}.conf"]
    # Test only on isolated sockets; never bind the machine's real HTTP(S) ports.
    site = site.replace("listen [::]:80;", "").replace("listen [::]:443 ssl;", "")
    site = site.replace("listen 80;", f"listen {http_listener};")
    site = site.replace("listen 443 ssl;", f"listen {https_listener} ssl;")
    config = tmp_path / "nginx.conf"
    config.write_text(f'pid "{tmp_path}/nginx.pid";\nerror_log stderr;\nevents {{ worker_connections 32; }}\n'
                      f'http {{ access_log off; {site} }}\n')
    return config


@pytest.mark.parametrize("kind", ["http", "https"])
def test_nginx_checks_complete_vhosts_and_certificate(deployment, tmp_path, kind):
    nginx = shutil.which("nginx")
    if not nginx:
        pytest.skip("nginx fehlt")
    config = site_files(deployment, tmp_path, kind, f"unix:{tmp_path}/http.sock", f"unix:{tmp_path}/https.sock")
    result = subprocess.run([nginx, "-t", "-p", str(tmp_path) + "/", "-c", str(config)], capture_output=True, text=True)
    check_nginx(result)


@contextmanager
def upstream(name):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = f"{name}:{self.path}".encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    except OSError as exc:
        if exc.errno == errno.EPERM:
            pytest.skip("Ausführungsrichtlinie blockiert lokale Testlistener")
        raise
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def unused_port():
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return reservation.getsockname()[1]


def test_https_routing_redirect_and_acme_without_public_network(deployment, tmp_path):
    nginx = shutil.which("nginx")
    if not nginx:
        pytest.skip("nginx fehlt")
    module, project, _, _ = deployment
    with upstream("api") as api, upstream("web") as web:
        profile = project / "infra/systemd/production.json"
        profile.write_text(json.dumps({"host": "127.0.0.1", "apiPort": api, "webPort": web, "domain": "atlas.example.test"}))
        http_port, https_port = unused_port(), unused_port()
        while https_port == http_port:
            https_port = unused_port()
        config = site_files(deployment, tmp_path, "https", f"127.0.0.1:{http_port}", f"127.0.0.1:{https_port}")
        challenge = tmp_path / "acme/.well-known/acme-challenge/test-token"
        challenge.parent.mkdir(parents=True)
        challenge.write_text("challenge-content")
        # This test uses an ephemeral self-signed certificate, never a production key.
        context = ssl._create_unverified_context()

        def request(path, secure=True):
            connection = (http.client.HTTPSConnection("127.0.0.1", https_port, timeout=1, context=context)
                          if secure else http.client.HTTPConnection("127.0.0.1", http_port, timeout=1))
            try:
                connection.request("GET", path, headers={"Host": "atlas.example.test"})
                response = connection.getresponse()
                return response.status, dict(response.getheaders()), response.read().decode()
            finally:
                connection.close()

        with (tmp_path / "nginx.stderr").open("w+") as errors:
            process = subprocess.Popen([nginx, "-p", str(tmp_path) + "/", "-c", str(config),
                                        "-g", "daemon off; master_process off;"], stdout=subprocess.DEVNULL, stderr=errors)
            try:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        assert request("/health/ready")[0] == 200
                        break
                    except OSError:
                        if process.poll() is not None or time.monotonic() > deadline:
                            errors.seek(0)
                            pytest.fail(errors.read())
                        time.sleep(.05)
                for path, expected in [("/api/v1/datasets?test=1", "api"), ("/health/ready", "api"),
                                       ("/health/web", "web"), ("/methodik", "web"), ("/_nuxt/app.js", "web")]:
                    status, _, body = request(path)
                    assert status == 200 and body == f"{expected}:{path}"
                status, headers, _ = request("/methodik?test=1", secure=False)
                assert status == 301 and headers["Location"] == "https://atlas.example.test/methodik?test=1"
                status, _, body = request("/.well-known/acme-challenge/test-token", secure=False)
                assert status == 200 and body == "challenge-content"
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)
