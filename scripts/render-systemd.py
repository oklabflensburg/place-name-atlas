"""Render application units and nginx locations without installing or starting services."""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
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


def render(root, user, node):
    root = root.resolve()
    account = pwd.getpwnam(user)
    if account.pw_uid == 0:
        raise ValueError("Als Dienstbenutzer einen bestehenden Benutzer ohne Root-Rechte verwenden")
    python = root / ".venv/bin/python"
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError("Python-Umgebung fehlt; zuerst uv sync --locked ausführen")
    if not (root / ".env").is_file():
        raise ValueError("Bestehende .env mit der Runtimeverbindung fehlt")
    config = json.loads((root / "infra/local.json").read_text())
    ports = [config.get(key) for key in ("apiPort", "webPort", "nginxPort")]
    if config.get("host") != "127.0.0.1" or any(type(port) is not int or not 1024 <= port <= 65535 for port in ports) or len(set(ports)) != 3:
        raise ValueError("infra/local.json muss verschiedene gültige Ports und host=127.0.0.1 enthalten")
    values = {
        "USER": unit_scalar(user), "WORKDIR": unit_scalar(root),
        "ENVFILE": unit_scalar(root / ".env"),
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
    nginx_values = {"HOST": config["host"], "API_PORT": str(config["apiPort"]), "WEB_PORT": str(config["webPort"])}
    files = {}
    for filename in ("place-name-atlas-api.service", "place-name-atlas-web.service", "nginx-locations.conf"):
        template = (TEMPLATES / (filename + ".in")).read_text()
        replacements = nginx_values if filename.endswith(".conf") else values
        files[filename] = re.sub(r"@([A-Z_]+)@", lambda match: replacements[match[1]], template)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=ROOT)
    parser.add_argument("--user", default=pwd.getpwuid(os.getuid()).pw_name)
    parser.add_argument("--node", default="node")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        node = node_executable(args.node)
        files = render(args.project_dir, args.user, node)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    output = args.output or args.project_dir.resolve() / "artifacts/systemd"
    output.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (output / filename).write_text(content)
    print(json.dumps({"rendered": [str(output / name) for name in files],
                      "user": args.user, "node": str(node)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
