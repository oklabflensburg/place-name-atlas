# Deployment auf einem eigenen Server

Diese Anleitung beschreibt den Betrieb von `oklabflensburg/place-name-atlas` auf einem einzelnen Linux-Server mit Docker Compose. Sie umfasst Erstinstallation, Datenübernahme, HTTPS, Aktualisierungen und Wiederherstellung. Für den Betrieb ohne Container mit vorhandenem nginx und PostgreSQL siehe [Frontend und Backend mit systemd](systemd.md); für Entwicklung siehe [Installation und Betrieb](operations.md).

## Aufbau und Voraussetzungen

```text
Browser → HTTPS :443 → Caddy auf dem Host
                       → 127.0.0.1:8080 → nginx
                                          ├─ /api/v1/*, /health/* → FastAPI :8000
                                          └─ übrige Seiten       → Nuxt :3000
FastAPI → PostgreSQL 18 / PostGIS 3.6 :5432 im Compose-Netz
```

Die Datei [infra/compose.yaml](../infra/compose.yaml) enthält die Dienste `db`, `migrate`, `api`, `web`, `nginx` und den nur bei Bedarf gestarteten `importer`. Datenbank, API und Nuxt veröffentlichen keine Hostports. nginx ist ausschließlich an `127.0.0.1:8080` gebunden. Als öffentlich erreichbarer Dienst ist der HTTPS-Proxy auf dem Host vorgesehen.

Benötigt werden:

- Ein Linux-Server mit Docker Engine und dem Compose-v2-Plugin; Installation nach der [offiziellen Docker-Anleitung](https://docs.docker.com/engine/install/).
- Git, Python 3, `curl` und `unzip` auf dem Host. Python wird für das Generieren der Konfiguration und des Quellenmanifests verwendet; Python-/Node-Anwendungsabhängigkeiten werden in den Images installiert.
- Für öffentlichen Betrieb ein eigener DNS-Name, der auf den Server zeigt, und Caddy nach dessen [Installationsanleitung](https://caddyserver.com/docs/install). Für die normalen ACME-Verfahren müssen TCP 80 und 443 erreichbar sein.
- Ausgehender HTTPS-Zugriff zu GitHub, den Container-/Paketregistries und den BKG-Datenquellen.
- Ausreichend Speicher für Quellarchive, entpackte Geodaten, das vorbereitete Bundle, Datenbank und Backups. Build und Deutschlandimport benötigen mehr Ressourcen als der anschließende Lesebetrieb; eine garantierte Mindestgröße oder Nutzerkapazität ist nicht gemessen.

Die Laufzeitversionen und Image-Digests stehen in den Dockerfiles, Lockfiles und der Compose-Datei. PostgreSQL 18 verwendet hier bewusst ein Volume unter `/var/lib/postgresql`; die Verzeichnisstruktur unterscheidet sich von älteren Major-Versionen. Siehe [Dokumentation des PostgreSQL-Images](https://hub.docker.com/_/postgres). Ein PostgreSQL-Major-Upgrade benötigt einen eigenen Migrations- bzw. Dump/Restore-Plan.

## 1. Quellstand auschecken

```sh
git clone https://github.com/oklabflensburg/place-name-atlas.git
cd place-name-atlas
git rev-parse HEAD
docker compose version
```

Für eine wiederholbare Installation einen geprüften Commit oder Release-Tag verwenden und die ausgegebene Commit-ID dokumentieren. `main` bezeichnet den Entwicklungsstand.

Die `.gitignore` schließt `.env`-Dateien, lokale Zugangsdaten, Abhängigkeiten, Builds, Quellarchive, Datenbank-Dumps und Backups aus. `.env.example` enthält ausschließlich Entwicklungsvorgaben. Die vollständigen BKG-Daten werden separat bezogen; sie sind nicht Bestandteil eines Git-Clones.

## 2. Eigene Zugangsdaten erzeugen

Der folgende Aufruf erstellt eine neue `.env.production` mit drei unabhängigen, zufälligen Passwörtern und Dateimodus 0600. Eine vorhandene Datei wird nicht überschrieben. Hexadezimale Passwörter können direkt in die von Compose zusammengesetzten Datenbank-URLs eingesetzt werden.

```sh
python3 - <<'PY'
import os
import secrets

values = {key: secrets.token_hex(32) for key in (
    'POSTGRES_PASSWORD', 'RUNTIME_PASSWORD', 'IMPORT_PASSWORD')}
values.update(QUERY_TIMEOUT_MS='10000', EXPORT_LIMIT='10000',
              TILE_LIMIT_BYTES='2000000', NUXT_PUBLIC_BASEMAP_URL='',
              NUXT_PUBLIC_BASEMAP_ATTRIBUTION='')
fd = os.open('.env.production', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as target:
    target.write(''.join(f'{key}={value}\n' for key, value in values.items()))
print('.env.production erstellt; Passwörter werden nicht ausgegeben.')
PY
mkdir -p data backups
chmod 700 backups
```

`POSTGRES_PASSWORD` gehört zur Datenbank-/Migrationseigentümerrolle `atlas_owner`. `RUNTIME_PASSWORD` gehört zur ausschließlich lesenden Rolle `atlas_runtime`; `IMPORT_PASSWORD` zur Rolle `atlas_import`. Die Anwendung erhält nur die jeweils benötigte Verbindung. Beim Compose-Betrieb müssen keine Host-`DATABASE_URL`-Werte in `.env.production` eingetragen werden: Compose setzt die Containerverbindungen mit Hostname `db` selbst zusammen.

Die Datei sicher außerhalb des Servers hinterlegen und niemals veröffentlichen. Bei eigenen Passwörtern mit Sonderzeichen ist deren Verwendung in URLs zu berücksichtigen; die hier erzeugten Hexwerte vermeiden dieses Problem.

Für die folgenden Befehle im Repositoryverzeichnis diese Shellfunktion definieren:

```sh
dc() {
  docker compose --project-name place-name-atlas \
    --env-file .env.production -f infra/compose.yaml "$@"
}
```

In einer neuen Shell die Funktion erneut definieren. Der feste Projektname bestimmt auch die Volumenamen; bei einem Umzug oder Update denselben Namen weiterverwenden.

## 3. Images bauen und Schema einrichten

```sh
dc config --quiet
dc pull db nginx
dc build migrate api web importer
dc up -d --wait --wait-timeout 300
dc ps -a
dc logs --tail=100 migrate
curl --fail http://127.0.0.1:8080/health/live
```

`config --quiet` validiert die Konfiguration, ohne aufgelöste Zugangsdaten auszugeben. `db` initialisiert bei einem neuen Datenvolume Rollen und Erweiterungen. Der Dienst `migrate` führt `alembic upgrade head` aus und beendet sich bei Erfolg mit Status 0. Die API startet erst danach. Diese Reihenfolge ist über [Compose-Abhängigkeiten und Healthchecks](https://docs.docker.com/compose/how-tos/startup-order/) festgelegt.

Zum aktuellen Schema gehören die generierten Orts-Zell-Indizes aus Migration 0002 und die gespeicherten Darstellungsgeometrien aus Migration 0003. Ein bestehender Datenbestand wird bei der Migration ergänzt; ein erneuter Import ist dafür nicht erforderlich. Insbesondere Migration 0003 benötigt eine Tabellensperre und gehört bei Updates in das Wartungsfenster vor dem API-Neustart.

Der Container-Healthcheck der API prüft die Erreichbarkeit über `/health/live`. Ohne freigeschalteten Datenbestand kann daher der Stack starten, während `/health/ready` noch HTTP 503 liefert. Das ist beim ersten Start erwartet. Die öffentliche Freigabe erfolgt erst nach Import, Veröffentlichung und erfolgreicher Readiness-Prüfung.

## 4. Daten bereitstellen

### Option A: Synthetische Funktionsprobe

```sh
dc run --rm importer import tests/fixtures/synthetic.json
dc run --rm importer publish synthetic-v1
curl --fail http://127.0.0.1:8080/health/ready
curl --fail http://127.0.0.1:8080/api/v1/datasets
```

Die Oberfläche kennzeichnet diesen Bestand als synthetisch. Er dient zur Installationsprüfung und ist keine Deutschlandauswertung. Ein nachfolgender echter Import verwendet eine eigene Datenkennung.

### Option B: Neue BKG-Daten vorbereiten und importieren

Die festgelegte Kombination verwendet GN250 für Ortsnamen, VG25 für Grenzen und VG250-EW für Einwohner. Quellen, Gebietsstände, Prüfsummen, Lizenzen und Einschränkungen stehen ausführlich unter [Datenquellen](data-sources.md). Die dortigen Quellenvermerke müssen auch bei eigener Veröffentlichung erhalten bleiben.

Auf dem Host im Repositoryverzeichnis:

```sh
curl --fail --location --retry 5 --continue-at - \
  https://daten.gdz.bkg.bund.de/produkte/vg/vg25_ebenen/2024-12/vg25.utm32s.gpkg.zip \
  -o data/vg25.zip
curl --fail --location --retry 5 --continue-at - \
  https://daten.gdz.bkg.bund.de/produkte/vg/vg250-ew_ebenen_1231/2024/vg250-ew_12-31.utm32s.gpkg.ebenen.zip \
  -o data/ew.zip
curl --fail --location --retry 5 --continue-at - \
  https://daten.gdz.bkg.bund.de/produkte/sonstige/gn250/2024/gn250.utm32s.csv.zip \
  -o data/gn.zip
unzip -t data/vg25.zip
unzip -t data/ew.zip
unzip -t data/gn.zip
unzip data/vg25.zip -d data/vg25
unzip data/ew.zip -d data/ew
unzip data/gn.zip -d data/gn
python3 scripts/create-bkg-manifest.py data
```

Der Manifesthelfer berechnet Archiv-Prüfsummen und kontrolliert die mitgelieferten Stichtagsangaben. Ein vorhandenes `data/manifest.json` wird nicht überschrieben. Für einen weiteren Stand ein eigenes Arbeitsverzeichnis und eine neue Kennung verwenden; keine bereits importierte Kennung mit verändertem Inhalt wiederverwenden.

Das Importer-Image läuft mit UID 10001. Es muss die Dateien lesen und das vorbereitete Bundle schreiben können. Auf einem frisch ausschließlich dafür angelegten `data/`-Verzeichnis die Eigentümerschaft entsprechend setzen, dann im Container vorbereiten:

```sh
sudo chown -R 10001:10001 data
dc run --rm importer prepare-bkg /data/manifest.json /data/bkg-2024.json
dc run --rm importer import /data/bkg-2024.json
dc run --rm importer report bkg-2024
```

`data/` wird als `/data` eingebunden; innerhalb des Containers deshalb die absoluten `/data/...`-Pfade verwenden. GDAL und die Python-Abhängigkeiten sind im API-/Importer-Image enthalten. Für spätere Downloads oder Änderungen der nun dem Containerbenutzer gehörenden Hostdateien passende Benutzerrechte verwenden.

Vor der Freischaltung den Bericht kontrollieren: übernommene Ortsobjekte, Geometriefehler, Ausschlüsse, Gemeindezuordnung, Quellen-/Lagekonflikte und Einwohnerverknüpfung. Import und Validierung können mehrere Minuten dauern und laufen unabhängig von öffentlichen HTTP-Anfragen. Der bisher veröffentlichte Stand bleibt währenddessen erhalten. Ein Prozessabbruch oder fehlgeschlagener Import wird nicht automatisch veröffentlicht.

Erst nach erfolgreicher Validierung freischalten:

```sh
dc run --rm importer publish bkg-2024
curl --fail http://127.0.0.1:8080/health/ready
curl --fail http://127.0.0.1:8080/api/v1/datasets
```

Der standardmäßige Manifesthelfer erzeugt die Kennung `bkg-2024`. Bereits geteilte Links mit einer anderen expliziten Kennung, etwa `bkg-2024-r3`, behalten diese Kennung. Bei einem Umzug des vorhandenen Bestands dessen Datenbank wiederherstellen, wenn solche Links erhalten bleiben sollen. Ein neuer Import wird nicht automatisch unter einer fremden alten Kennung veröffentlicht.

### Option C: Vorhandenen Bestand übernehmen

Für eine bestehende Installation eine Datenbanksicherung mit Quellenmetadaten und Veröffentlichungszeiger verwenden. Das Vorgehen steht im Abschnitt „Backup und Wiederherstellung“. Keine laufenden PostgreSQL-Datenverzeichnisse zwischen inkompatiblen Major-Versionen kopieren. Nach einer Wiederherstellung ausstehende Migrationen mit `migrate` anwenden.

## 5. HTTPS mit Caddy freischalten

In DNS den eigenen Namen auf den Server zeigen lassen; einen AAAA-Eintrag nur setzen, wenn der Host auch über IPv6 korrekt erreichbar ist. Die Datei [infra/Caddyfile.example](../infra/Caddyfile.example) enthält eine Vorlage für Caddy auf demselben Host:

```caddyfile
atlas.example.org {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8080
}
```

Den Beispielnamen durch den eigenen vollständigen Hostnamen ersetzen. Bei einem Caddy-Host mit weiteren Websites den Block in die bestehende Konfiguration aufnehmen. Danach beispielsweise:

```sh
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
curl --fail https://atlas.example.org/health/ready
curl --fail https://atlas.example.org/methodik
```

Caddy übernimmt bei erfüllten DNS-/Erreichbarkeitsvoraussetzungen Zertifikatsverwaltung und HTTP-zu-HTTPS-Weiterleitung; siehe [Automatic HTTPS](https://caddyserver.com/docs/automatic-https). Caddy-Zustandsverzeichnis und Zertifikatsverlängerung müssen den Serverneustart überstehen. Läuft ein anderer HTTPS-Proxy bereits auf dem Host, kann er stattdessen auf denselben Loopback-Port weiterleiten.

Die Vorlage enthält keine zusätzlichen Access-Logs mit vollständigen URLs. Geteilte Ansichten stehen im Queryparameter `s`; bei einer eigenen Logging-Konfiguration entsprechend entscheiden, ob vollständige Suchzustände gespeichert werden sollen. Die API protokolliert Pfad, Status, Dauer und Request-ID ohne Queryinhalt.

Zur Abnahme im Browser Startseite, mehrere Endungen, Regionsfilter, Zellwerte, Detailkarte, Methodik und einen geteilten Link prüfen. Auf kleinen Bildschirmen auch die Filteransicht und Dialoge kontrollieren. Haupt- und alternative Ortsnamen können Treffer auslösen; passende Alternativnamen stehen in der Detailansicht unter „Treffer über“.

## 6. Konfiguration und laufender Betrieb

| Einstellung in `.env.production` | Bedeutung | Standard |
|---|---|---|
| `POSTGRES_PASSWORD` | Eigentümer-/Migrationsrolle | selbst erzeugen |
| `RUNTIME_PASSWORD` | lesende API-Rolle | selbst erzeugen |
| `IMPORT_PASSWORD` | Import-/Veröffentlichungsrolle | selbst erzeugen |
| `QUERY_TIMEOUT_MS` | SQL-Statement-Zeitlimit der API | `10000` |
| `EXPORT_LIMIT` | maximale Ortszahl für einen Export | `10000` |
| `TILE_LIMIT_BYTES` | maximale Kachelgröße | `2000000` |
| `NUXT_PUBLIC_BASEMAP_URL` | optionale Raster-URL mit `{z}/{x}/{y}` | leer |
| `NUXT_PUBLIC_BASEMAP_ATTRIBUTION` | erforderlicher Quellenvermerk der Zusatzkarte | leer |

Die Übersicht und die Detailkarte funktionieren ohne externen Basiskartendienst. Eine konfigurierte Zusatzkarte benötigt gültige Nutzungsrechte, Attribution und geeignete Kapazitätsgrenzen. Beide Basiskartenvariablen gemeinsam setzen. Bei Änderung der Exportgrenze auch den zugehörigen Oberflächentext prüfen.

Nach einer Konfigurationsänderung die betroffenen Container mit `dc up -d` neu erstellen lassen; `dc restart` allein übernimmt keine neuen Umgebungswerte. Passwortänderungen bei vorhandenen Datenvolumes brauchen zusätzlich die tatsächliche Änderung der PostgreSQL-Rollen: `infra/db/init.sh` läuft nur bei einem neuen Volume. Eine geänderte `.env.production` ändert bestehende Rollenpasswörter nicht. Für interaktive Rotation kann `dc exec db psql -U atlas_owner -d atlas` mit `\password ROLLENNAME` verwendet werden; anschließend die passenden Konfigurationswerte und Container aktualisieren.

```sh
dc ps -a
dc logs --tail=100 api web nginx
dc logs --tail=100 migrate
dc exec -T db psql -U atlas_owner -d atlas -c 'SELECT * FROM publication'
```

| Prüfung | Erwartung |
|---|---|
| `/health/live` | API-Prozess antwortet |
| `/health/ready` | Datenbank, erforderliche Schemaspalten und veröffentlichter Bestand verfügbar |
| `/api/v1/datasets` | aktive Kennung und Quellen stimmen |
| `/methodik` | Nuxt liefert HTML |

Für den öffentlichen Dienst Readiness überwachen; Container-Liveness allein bestätigt keinen freigeschalteten Bestand. Container-Logs mit der auf dem Host üblichen Rotation begrenzen. API-, Datenbank- und Build-Last regelmäßig beobachten, bevor zusätzliche Nutzerkapazität angenommen wird.

## 7. Backup und Wiederherstellung

Ein Datenbank-Dump enthält Fachdaten, Quellenmetadaten, Datenversionen, Schema und Veröffentlichungszeiger. Zusätzlich `.env.production`, den verwendeten Git-Commit und die ursprünglichen Quellenarchive samt Manifest sicher aufbewahren. Eine Kopie außerhalb dieses Servers vorhalten.

Backup aus dem laufenden Stack:

```sh
umask 077
atlas_backup="backups/atlas-$(date -u +%Y%m%dT%H%M%SZ).dump"
dc exec -T db pg_dump -U atlas_owner -d atlas \
  --format=custom --no-owner > "$atlas_backup"
test -s "$atlas_backup"
dc exec -T db pg_restore --list < "$atlas_backup" > /dev/null
sha256sum "$atlas_backup"
```

Eine Inhaltsliste ist noch kein Restore-Test. Wiederherstellung zunächst mit eigenem Compose-Projektnamen und damit eigenem Datenvolume prüfen. In diesem Projekt nur die Datenbank starten; dadurch entsteht kein zweiter Listener auf Port 8080:

```sh
dr() {
  docker compose --project-name place-name-atlas-restore \
    --env-file .env.production -f infra/compose.yaml "$@"
}
dr up -d --wait db
dr exec -T db pg_restore -U atlas_owner -d atlas \
  --no-owner --no-privileges --exit-on-error < "$atlas_backup"
dr run --rm --no-deps migrate
dr exec -T db psql -U atlas_owner -d atlas \
  -c 'SELECT * FROM publication' \
  -c 'SELECT count(*) FROM place_record' \
  -c 'SELECT grid_x,grid_y FROM place_record LIMIT 1' \
  -c 'SELECT ST_SRID(display_geom) FROM admin_area LIMIT 1' \
  -c "SELECT has_table_privilege('atlas_runtime','place_record','SELECT') AS can_read, has_table_privilege('atlas_runtime','place_record','INSERT') AS can_write"
dr down
```

Für diesen Ablauf muss die Restore-Datenbank neu und ohne bereits restaurierte Anwendungstabellen sein. Das Init-Skript hat dort nur Erweiterungen und Rollen eingerichtet; die Tabellen entstehen beim Restore. Erwartet werden ein gültiger Veröffentlichungszeiger, plausible Ortszahlen, EPSG:3035 für `display_geom`, `can_read=true` und `can_write=false`. Bei einer vollständigen Umzugsabnahme zusätzlich API und Browser am restaurierten Bestand prüfen. Der Testprojekt-Datenbestand bleibt nach `dr down` im eigenen Volume erhalten und kann nach Abschluss gezielt aufgeräumt werden.

Für eine echte Wiederherstellung denselben Ablauf auf einer neuen Zielinstallation durchführen, bevor deren API gestartet wird. Der Restore-Test greift nicht auf das Volume des laufenden Projekts `place-name-atlas` zu. Im regulären Betrieb `dc down` ohne `--volumes` verwenden, wenn die Container entfernt werden sollen; ein Löschen des Datenvolumes gehört nicht zum Update- oder Neustartablauf.

## 8. Code und Schema aktualisieren

Vor einer Aktualisierung Commit, aktive Datenkennung und ein geprüftes Backup festhalten. Release-Hinweise und Migrationen lesen. Danach:

```sh
git fetch origin --tags
git checkout GEPRUEFTER_COMMIT_ODER_TAG
dc config --quiet
dc build migrate api web importer
dc stop nginx api web
dc run --rm --no-deps migrate
dc up -d --wait --wait-timeout 300
curl --fail http://127.0.0.1:8080/health/ready
curl --fail http://127.0.0.1:8080/api/v1/datasets
```

Die Datenbank bleibt beim Wartungsstopp erhalten. Eine fehlgeschlagene Migration zuerst anhand von `dc logs migrate` bzw. der Ausgabe des Einmalaufrufs untersuchen. Die API erst wieder mit dem passenden Schema starten. Ein Code-Rollback ist nur möglich, wenn der vorherige Code mit dem aktuellen Schema kompatibel ist; andernfalls die vorher gesicherte Kombination auf einer getrennten Zielinstallation wiederherstellen. Keine automatischen Schema-Downgrades oder Volumenlöschungen im Updatepfad.

Ein Rollback ausschließlich der veröffentlichten Datenversion benötigt keinen Codewechsel:

```sh
dc run --rm importer publish VORHERIGE_VERÖFFENTLICHTE_KENNUNG
```

Dies setzt atomar den aktiven Zeiger um. Explizit versionierte Links behalten ihren jeweiligen Stand. Alte Datenversionen werden nicht automatisch gelöscht.

## 9. Typische Fehler

| Symptom | Prüfung und Abhilfe |
|---|---|
| `up --wait` scheitert | `dc ps -a`, dann Logs des betroffenen Dienstes und `migrate` lesen. |
| `/health/ready` liefert 503 | Migrationen, Datenbankverbindung und freigeschalteten Datenbestand prüfen. Ein erster Import muss auch veröffentlicht werden. |
| `display_geom` oder `grid_x` fehlt | Mit dem aktuellen `migrate`-Image `alembic upgrade head` ausführen. |
| Importer meldet `Permission denied` | Leserechte der Quellen und Schreibrechte im gemounteten `/data` für UID 10001 prüfen. |
| Passwort nach Änderung ungültig | Bestehende Rollen in PostgreSQL anpassen; Init-Skripte laufen bei bestehenden Volumes nicht erneut. |
| 502 vom Proxy | `api`/`web`, Containerzustand und nginx-Upstreams prüfen; externe Zugriffe laufen über Host-Caddy und Loopback-nginx. |
| HTTPS-Zertifikat wird nicht ausgestellt | A/AAAA, Hostnamen, TCP 80/443, belegte Ports und Caddy-Logs prüfen. |
| Geteilter Link liefert 410 | Der explizite Datenstand fehlt. Passenden Bestand übernehmen oder bewusst eine verfügbare Version auswählen. |
| Kein externer Kartenhintergrund | Ohne beide Basiskartenvariablen ist der eingebaute Hintergrund vorgesehen. |
| Viel Wartezeit bei einer Abfrage | Request-ID und `Server-Timing` auswerten, SQL-Zeitlimit und Filterumfang prüfen; Messungen stehen unter [Initiales Laden](initial-load-performance.md). |

## Prüfstand dieser Anleitung

Compose-Konfiguration, Quellstand und dokumentierte Befehle werden lokal auf Konsistenz geprüft. Die vorhandene CI unter [.github/workflows/ci.yml](../.github/workflows/ci.yml) enthält Datenbanktests, Frontend-Tests, Build, Browserprüfungen, Restore und einen Container-/nginx-Test. Ein neuer GitHub-Push ist erst nach einem tatsächlich erfolgreichen CI-Lauf als dort geprüft zu bezeichnen.

Diese Dokumentation ist kein Nachweis eines ausgeführten Serverdeployments. Auf dem Server bleiben insbesondere DNS, TLS, Dateirechte, tatsächlicher Containerstart, Backup-Restore und Browserabnahme zu prüfen. Messungen ohne Netzwerk und deren Grenzen sind in [Testresultate](test-results.md) und [Initiales Laden](initial-load-performance.md) dokumentiert.
