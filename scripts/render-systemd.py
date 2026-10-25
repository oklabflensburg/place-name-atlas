"""Render systemd units and complete nginx vHosts without installing or starting services."""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "infra/systemd"


def unit_quote(value, command=False):
    value = str(value)
    if any(ord(character) < 32 for character in value):
        raise ValueError("Steuerzeichen sind in Dienstpfaden nicht zulässig")
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if command:
        value = value.replace("$", "$$")
    return '"' + value + '"'


def unit_scalar(value):
    # User, WorkingDirectory and EnvironmentFile are scalar directives: unlike
    # ExecStart's arguments, wrapping them in quotes makes the quotes literal.
    value = str(value)
    if value != value.strip() or value.endswith("\\") or any(ord(character) < 32 for character in value):
        raise ValueError("Ungültiger Dienstpfad oder Benutzername")
    return value.replace("%", "%%")


def node_executable(command):
    candidate = shutil.which(command)
    if not candidate:
        raise ValueError("Node nicht gefunden; --node /ABSOLUTER/PFAD/ZU/node angeben")
    # Resolve nvm/asdf/mise shims in the caller's prepared shell, so systemd
    # invokes the actual binary without depending on interactive shell setup.
    result = subprocess.run([candidate, "-p", "process.execPath"], check=True,
                            capture_output=True, text=True, timeout=15)
    path = Path(result.stdout.strip())
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("Node hat keinen ausführbaren absoluten Binärpfad geliefert")
    return path


def config_file(root, path=None):
    path = Path(path or "infra/systemd/production.json")
    return (path if path.is_absolute() else root / path).resolve()


def domain_name(value):
    if not isinstance(value, str):
        raise ValueError("Ein gültiger DNS-Hostname ist erforderlich")
    value = value.lower().rstrip(".")
    labels = value.split(".")
    if len(value) > 253 or len(labels) < 2 or labels[-1].isdigit() or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
    ):
        raise ValueError("Ein gültiger DNS-Hostname ohne Schema, Port oder Pfad ist erforderlich")
    return value


def nginx_path(value):
    value = str(value)
    if not Path(value).is_absolute() or "$" in value or any(ord(char) < 32 for char in value):
        raise ValueError("nginx-Pfade müssen absolut sein und dürfen keine Variablen oder Steuerzeichen enthalten")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(root, user, node, config_path=None, domain=None, tls_certificate=None, tls_certificate_key=None,
           acme_webroot=Path("/var/lib/place-name-atlas/acme"),
           nginx_snippet=Path("/etc/nginx/snippets/place-name-atlas.locations.conf")):
    root = root.resolve()
    account = pwd.getpwnam(user)
    if account.pw_uid == 0:
        raise ValueError("Als Dienstbenutzer einen bestehenden Benutzer ohne Root-Rechte verwenden")
    python = root / ".venv/bin/python"
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError("Python-Umgebung fehlt; zuerst uv sync --locked ausführen")
    if not (root / ".env").is_file():
        raise ValueError("Bestehende .env mit der Runtimeverbindung fehlt")
    config_path = config_file(root, config_path)
    config = json.loads(config_path.read_text())
    ports = [config.get(key) for key in ("apiPort", "webPort")]
    if config.get("host") != "127.0.0.1" or any(type(port) is not int or not 1024 <= port <= 65535 for port in ports) or len(set(ports)) != 2:
        raise ValueError("Das Portprofil muss verschiedene gültige Ports und host=127.0.0.1 enthalten")
    domain = domain_name(domain if domain is not None else config.get("domain"))
    if bool(tls_certificate) != bool(tls_certificate_key):
        raise ValueError("Zertifikat und Schlüssel müssen gemeinsam angegeben werden")
    certificate = tls_certificate or Path("/etc/letsencrypt/live") / domain / "fullchain.pem"
    certificate_key = tls_certificate_key or Path("/etc/letsencrypt/live") / domain / "privkey.pem"
    values = {
        "USER": unit_scalar(user), "WORKDIR": unit_scalar(root),
        "ENVFILE": unit_scalar(root / ".env"),
        "CONFIG": unit_quote("ATLAS_LOCAL_CONFIG=" + str(config_path), command=True),
        "PYTHONPATH": unit_quote("PYTHONPATH=" + str(root / "apps/api"), command=True),
        "PYTHON": unit_quote(python, command=True),
        "API_SCRIPT": unit_quote(root / "scripts/serve-real.py", command=True),
        "NODE": unit_quote(node, command=True),
        "WEB_ENTRY": unit_quote(root / "apps/web/.output/server/index.mjs", command=True),
        "HOST": unit_quote("HOST=" + config["host"]),
        "NITRO_HOST": unit_quote("NITRO_HOST=" + config["host"]),
        "PORT": unit_quote("PORT=" + str(config["webPort"])),
        "NITRO_PORT": unit_quote("NITRO_PORT=" + str(config["webPort"])),
    }
    nginx_values = {"HOST": config["host"], "API_PORT": str(config["apiPort"]), "WEB_PORT": str(config["webPort"]),
                    "DOMAIN": domain, "ACME_WEBROOT": nginx_path(acme_webroot),
                    "LOCATIONS": nginx_path(nginx_snippet), "TLS_CERTIFICATE": nginx_path(certificate),
                    "TLS_CERTIFICATE_KEY": nginx_path(certificate_key),
                    "CERTIFICATE_DIRECTORY": shlex.quote(str(Path(certificate).parent))}
    files = {}
    for filename in ("place-name-atlas-api.service", "place-name-atlas-web.service", "nginx-locations.conf",
                     "nginx-site.http.conf", "nginx-site.https.conf", "certbot-deploy-hook.sh"):
        template = (TEMPLATES / (filename + ".in")).read_text()
        replacements = values if filename.endswith(".service") else nginx_values
        files[filename] = re.sub(r"@([A-Z_]+)@", lambda match: replacements[match[1]], template)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=ROOT)
    parser.add_argument("--user", default=pwd.getpwuid(os.getuid()).pw_name)
    parser.add_argument("--node", default="node")
    parser.add_argument("--config", type=Path, help="Portprofil, Standard: infra/systemd/production.json")
    parser.add_argument("--domain", help="Domain aus dem Profil überschreiben")
    parser.add_argument("--tls-certificate", type=Path)
    parser.add_argument("--tls-certificate-key", type=Path)
    parser.add_argument("--acme-webroot", type=Path, default=Path("/var/lib/place-name-atlas/acme"))
    parser.add_argument("--nginx-snippet", type=Path, default=Path("/etc/nginx/snippets/place-name-atlas.locations.conf"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        node = node_executable(args.node)
        profile = config_file(args.project_dir.resolve(), args.config)
        files = render(args.project_dir, args.user, node, profile, args.domain, args.tls_certificate,
                       args.tls_certificate_key, args.acme_webroot, args.nginx_snippet)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    output = args.output or args.project_dir.resolve() / "artifacts/systemd"
    output.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (output / filename).write_text(content)
    print(json.dumps({"rendered": [str(output / name) for name in files],
                      "user": args.user, "node": str(node), "config": str(profile)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
