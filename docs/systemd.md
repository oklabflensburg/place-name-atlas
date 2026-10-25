# Frontend und Backend mit systemd betreiben

Für den vorhandenen Server mit nginx, bestehender `.env` und bereits veröffentlichtem Datenbestand. Die beiden Dienste laufen als vorhandener Benutzer `oklab` im Repository `/opt/git/place-name-atlas`. Andere Pfade/Benutzer sind über den Generator möglich. PostgreSQL und nginx bleiben eigenständig verwaltet.

- `place-name-atlas-api.service`: ein FastAPI/Uvicorn-Prozess aus `.venv`, mit dem richtigen Python-Modulpfad.
- `place-name-atlas-web.service`: ein Node-Prozess für den gebauten Nuxt-Server, einschließlich 64-KiB-Headergrenze für geteilte Ansichtslinks.

Beide binden an die bestehenden Loopback-Adressen aus `infra/local.json`: standardmäßig Backend `127.0.0.1:8000`, Frontend `127.0.0.1:3000`. Die Datenbankverbindung kommt weiterhin aus `.env`. Es werden keine Rollen, Zugangsdaten, Ports, Migrationen, Importe oder Veröffentlichungen angelegt/geändert. Es laufen weder Entwicklungsserver noch Paketinstallation oder Build bei einem Dienststart. Dienstfehler führen zu begrenzten Neustartversuchen; Logs gehen ins Journal.

## 1. Abhängigkeiten und Frontend vorbereiten

Als `oklab` im Repository auf dem Webserver:

```sh
cd /opt/git/place-name-atlas
UV_LINK_MODE=copy uv sync --locked
pnpm install --frozen-lockfile
pnpm build
```

Die Node-/Python-Anforderungen stehen im [README](../README.md). Node muss in dieser Shell verfügbar sein. Das gebaute Frontend liegt anschließend unter `apps/web/.output/server/index.mjs`. Der Build kann mehr Speicher benötigen als der anschließende Betrieb; diese Änderung misst keinen Spitzenverbrauch des Frontend-Builds.

## 2. Dienste erzeugen und prüfen

```sh
uv run --locked python scripts/render-systemd.py --user oklab
cat artifacts/systemd/place-name-atlas-api.service
cat artifacts/systemd/place-name-atlas-web.service
systemd-analyze verify --man=no artifacts/systemd/*.service
```

Der Generator schreibt ausschließlich unter `artifacts/systemd/`. Er liest die Portkonfiguration, ermittelt die tatsächliche Node-Binärdatei der aktuellen Shell (auch bei nvm/asdf/mise) und verwendet absolute Pfade. Er installiert und startet nichts. Benutzer und Python-Umgebung müssen vorhanden sein. Für andere Installationspfade/Node-Versionen:

```sh
uv run --locked python scripts/render-systemd.py \
  --project-dir /opt/git/place-name-atlas --user oklab --node /ABSOLUTER/PFAD/ZU/node
```

Die vorhandene `.env` muss für `oklab` lesbar sein und `KEY=VALUE`-Zeilen enthalten, keine Shellbefehle oder `export`-Präfixe. Sie wird unverändert als `EnvironmentFile` verwendet. Frontend-Public-Konfiguration wie `NUXT_PUBLIC_BASEMAP_URL` bleibt damit verfügbar; die bekannten Datenbankverbindungen und -passwörter werden vor dem Frontendstart aus dessen Umgebung entfernt. Der Backendprozess verwendet weiterhin `DATABASE_URL`. `PYTHONPATH` und die HTTP-Bindungen werden im Startkommando ausdrücklich gesetzt, damit fremde `PORT`-/`HOST`-/`PYTHONPATH`-Einträge in `.env` keine anderen Ports oder Modulpfade aktivieren.

Die Unit-Vorlagen stehen unter [`infra/systemd/`](../infra/systemd/). Es werden systemweite Units für einen vorhandenen Benutzer erzeugt. Dessen vorhandene uv-Python-/Node-Installation bleibt lesbar; die Dienste benötigen keine interaktive Shell und keine Aktivierung einer virtuellen Umgebung.

## 3. Installieren und aktivieren

Nach erfolgreicher Prüfung der erzeugten Units:

```sh
sudo install -m 0644 artifacts/systemd/place-name-atlas-api.service /etc/systemd/system/
sudo install -m 0644 artifacts/systemd/place-name-atlas-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now place-name-atlas-api.service place-name-atlas-web.service

systemctl status --no-pager place-name-atlas-api.service place-name-atlas-web.service
curl --fail http://127.0.0.1:8000/health/ready
curl --fail http://127.0.0.1:3000/health/web
```

Die Prüfadressen oben gelten für die unveränderte `infra/local.json`. Bei bereits belegten Ports die zuständigen Prozesse zunächst zuordnen; die Units wechseln auf keinen Ersatzport und beenden keine fremden Dienste. `active` bestätigt den laufenden Prozess; die Healthchecks prüfen zusätzlich Backendbereitschaft bzw. Frontenderreichbarkeit. Ein schon laufender Entwicklungs-/Vorschaustack darf nicht dieselben Ports belegen. Für diesen systemd-Betrieb `systemctl` und `journalctl` verwenden.

## 4. Vorhandenen nginx anbinden

Im Produktionsbuild übernimmt nginx die API-Weiterleitung; Nuxts `devProxy` gilt für den Entwicklungsserver. Die bestehende Domain, `listen`-Direktiven und TLS-Konfiguration beibehalten. Der Generator erzeugt passende Locations mit denselben Ports wie die Units:

```sh
cat artifacts/systemd/nginx-locations.conf
sudo install -d -m 0755 /etc/nginx/snippets
sudo install -m 0644 artifacts/systemd/nginx-locations.conf /etc/nginx/snippets/place-name-atlas.locations.conf
```

Im **bestehenden zur Anwendung gehörenden** `server`-Block die bisherigen entsprechenden Locations durch diesen Include ersetzen:

```nginx
include /etc/nginx/snippets/place-name-atlas.locations.conf;
```

Vorhandene gleichnamige `location`-Blöcke bzw. bereits gesetzte Headerpuffer nicht doppelt aufnehmen. Das Snippet routet `/api/v1/` und `/health/` zum Backend, `/health/web` und die übrigen Seiten zum Frontend. Es öffnet keinen weiteren Listener und enthält keine Domain-/TLS-Vorgaben. Anschließend prüfen und die laufende nginx-Konfiguration neu laden:

```sh
sudo nginx -t
sudo systemctl reload nginx
```

Danach die Anwendung über die bereits eingerichtete öffentliche HTTPS-Adresse öffnen und `/health/ready` über dieselbe Domain prüfen. Der Generator verändert keine nginx-Konfiguration; die Einbindung erfolgt ausdrücklich durch die oben beschriebenen Schritte.

## Logs und spätere Updates

```sh
journalctl -u place-name-atlas-api.service -u place-name-atlas-web.service -n 100 --no-pager
```

Anwendungs-/Abhängigkeitsupdates mit `uv sync --locked`, `pnpm install --frozen-lockfile` und einem neuen Produktionsbuild vorbereiten; Builds im Wartungsfenster oder in einem separaten Releaseverzeichnis erstellen. Danach die beiden **Anwendungsdienste** gezielt neu starten:

```sh
sudo systemctl restart place-name-atlas-api.service place-name-atlas-web.service
```

Ändern sich Repositorypfad, Node-Binärpfad oder `infra/local.json`, die Units und nginx-Locations neu erzeugen, prüfen und installieren. Für geänderte Units ist `daemon-reload` nötig, für geänderte Locations `nginx -t` und ein nginx-Reload. Eine reine Änderung der `.env` erfordert einen Neustart der jeweiligen Anwendungsdienste, kein erneutes Rendern. Datenbankeinrichtung, Migration, Import und Publish bleiben separate administrative Schritte; der bereits veröffentlichte Bestand bleibt bestehen.

Referenzen: [systemd.service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html), [systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html), [Nuxt Node-Deployment](https://nuxt.com/docs/4.x/getting-started/deployment).
