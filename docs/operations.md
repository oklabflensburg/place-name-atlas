# Installation und Betrieb

Voraussetzungen: Docker Engine mit Compose v2 oder Python 3.13, uv 0.12.5, Node 22.22.1+, pnpm 12.14.0, PostgreSQL 18 mit PostGIS 3.6 und GDAL. Versionen/Hashes stehen in Lockfiles und Dockerfiles. Containerbasen sind mit überprüften Registry-Digests fixiert; Updates müssen bewusst geprüft werden.

Für den dauerhaften Betrieb ohne Container auf einem Server mit bestehendem nginx und PostgreSQL: [systemd-Anleitung für Frontend und Backend](systemd.md). Die folgenden Entwicklungs-/Vorschauhelfer sind für den lokalen Stack vorgesehen.

## Compose

```sh
cp .env.example .env
# Passwörter in .env ersetzen; bei URL-Sonderzeichen URL-Encoding berücksichtigen.
docker compose --env-file .env -f infra/compose.yaml up --build -d
docker compose --env-file .env -f infra/compose.yaml run --rm importer import tests/fixtures/synthetic.json
docker compose --env-file .env -f infra/compose.yaml run --rm importer publish synthetic-v1
curl http://127.0.0.1:8080/health/ready
```

Die Fixture liegt im API-Image unter `/app/tests/fixtures/`. Für reale Daten wird `./data` nach `/data` eingebunden; beispielsweise `run --rm importer import /data/bkg-2024.json` und anschließend `publish bkg-2024`. Der Migrationseinmaljob läuft vor dem API-Start. Ohne veröffentlichten Bestand ist `/health/live` erfolgreich, `/health/ready` meldet ausdrücklich 503. PostgreSQL wird nicht öffentlich gebunden. nginx lauscht zunächst ausschließlich lokal auf Port 8080. `up --build` ist kein behaupteter Test dieser Container in einer Umgebung ohne Dockerzugriff.

## Entwicklung ohne Container

```sh
uv sync --locked
pnpm install --frozen-lockfile
uv run python scripts/setup-postgres.py
# Einen echten Bestand importieren und veröffentlichen (siehe Importpipeline).
pnpm dev
```

Der Einrichtungshelfer legt `atlas` in der regulären PostgreSQL-Instanz auf **127.0.0.1:5432** an. Er verwendet `sudo -u postgres` über den lokalen Socket, erzeugt getrennte Rollen `atlas_owner`, `atlas_runtime`, `atlas_import`, aktiviert PostGIS/pg_trgm und führt alle Migrationen aus. Voraussetzung ist ein laufendes PostgreSQL 18+ mit installiertem PostGIS; unter Ubuntu gegebenenfalls `sudo systemctl start postgresql@18-main`. Bei fehlender `.env` erzeugt er individuelle Passwörter und speichert sie mit Dateirechten 0600. Eine bestehende `.env` muss bereits passende Verbindungen enthalten; bestehende Rollenpasswörter werden nicht geändert. Der Helfer löscht keine Datenbank und setzt keine Tabellen zurück.

Den vorhandenen lokalen BKG-Bestand aus der Sicherung übernehmen:

```sh
uv run python scripts/setup-postgres.py --restore backups/atlas_dev_20261021_215050.dump
pnpm dev
```

`--restore` benötigt eine leere Zieldatenbank und übernimmt auch den gespeicherten Veröffentlichungszeiger. Anschließend werden Eigentümer/Rechte gesetzt und ausstehende Migrationen ausgeführt. Nach einem erfolgreichen Restore zum erneuten Prüfen den Helfer **ohne** `--restore` aufrufen. `--prepare-only` erstellt bzw. validiert nur die `.env`, ohne Datenbankzugriff. Ein bereits laufender Projektstack muss nach dem Verbindungswechsel mit `pnpm local:stop` regulär beendet und neu gestartet werden. Explizit exportierte Datenbankvariablen haben weiterhin Vorrang vor `.env`.

Der vorgesehene Browser-Einstieg ist für Entwicklung und Vorschau **http://127.0.0.1:8080**. API 8000, Nuxt 3000 und nginx 8080 sind in `infra/local.json` zentral festgelegt. `pnpm dev` startet alle drei Dienste; kein separates `make api` erforderlich. `pnpm preview:local` verwendet den aktuellen Produktionsbuild nach `pnpm build`. Beide Befehle verwenden denselben nginx-Upstream auf Port 3000. `DATABASE_URL` aus der Umgebung bzw. `.env` bestimmt die lesende Datenbank; Standard ist nun `atlas_runtime@127.0.0.1:5432/atlas`. Für einen temporären PostgreSQL-Testcluster:

```sh
/usr/lib/postgresql/18/bin/initdb -D /tmp/ortsnamenatlas-pg --auth=trust --no-locale -E UTF8
/usr/lib/postgresql/18/bin/pg_ctl -D /tmp/ortsnamenatlas-pg -l /tmp/ortsnamenatlas-pg.log -o '-k /tmp -p 55439 -h 127.0.0.1' start
pnpm test:e2e --backend
pnpm test:e2e
```

Automatisierte synthetische Tests verwenden ausschließlich `infra/test-local.json`: API 18000, Nuxt 13000, nginx 18080. Sie übernehmen keine bereits laufenden Server und setzen nur `atlas_test_web` zurück. Der echte Browserlauf benutzt den vorgesehenen nginx-Einstieg und prüft die Herkunftskennungen beider Upstreams. Für große geteilte Filter setzen die Startskripte und nginx eine konsistente Headergrenze von 64 KiB; der Filtervertrag selbst bleibt enger begrenzt.

Die Trust-Authentifizierung ist ausschließlich für diesen isolierten lokalen Testcluster bestimmt. Tests nutzen `atlas_test` bzw. `atlas_test_web`; die Python-Suite verweigert Datenbanknamen ohne `atlas_test`-Präfix. Alternativ `TEST_ADMIN_URL` auf eine lokale Testadministrationsverbindung setzen. Reguläre pytest-Ausführung verlangt `TEST_DATABASE_URL`; ohne diese werden räumliche Tests ausdrücklich übersprungen, nicht als bestanden bezeichnet.

## CSS-Import von Tailwind

`apps/web/app/assets/main.css` importiert `tailwindcss` direkt. Deshalb deklariert `apps/web/package.json` Tailwind 4.3.3 ausdrücklich als eigene Abhängigkeit; ein nur transitiv durch Nuxt UI installiertes Paket ist bei isolierter pnpm-Auflösung nicht zuverlässig aus dem Assetsverzeichnis erreichbar. Die bereits vorhandene Version und deren Integritätsdaten werden im Lockfile wiederverwendet. Der zuvor reproduzierte Importfehler wird mit dem echten Tailwind-Compiler aus genau diesem Verzeichnis geprüft: [Prüfbericht](reports/tailwind-resolution-check.json).

Nach Übernahme der Abhängigkeitskorrektur im Hostterminal `pnpm install --frozen-lockfile` ausführen und den Projektstack neu starten. Eine Neuinstallation des gesamten Abhängigkeitsbaums war in der eingeschränkten Sitzung wegen des schreibgeschützten gemeinsamen pnpm-Verzeichnisses nicht möglich; die vorhandene Paketversion wurde für die Compiler- und Buildprüfung innerhalb des Workspace verknüpft. Typprüfung, 28 Tests und Produktionsbuild sind ausgeführt. Ein Browserlauf wird damit nicht behauptet.

## Konfiguration und Rechte

Pydantic Settings liest `.env` und Umgebungsvariablen. `DATABASE_URL` ist die lesende Runtimeverbindung, `IMPORT_DATABASE_URL` darf Fachzeilen hinzufügen/aktualisieren und Tabellen analysieren, `MIGRATION_DATABASE_URL` gehört dem Schemaeigentümer. Runtime bekommt SELECT und kein INSERT/UPDATE/DDL. `infra/db/init.sh` setzt Rollen und Defaultprivilegien beim ersten Containerstart. Bestehende Volumes benötigen eine explizite Rechtepflege; geänderte Initialisierungsdateien laufen nicht erneut.

`QUERY_TIMEOUT_MS` standardmäßig 10.000 ms, `EXPORT_LIMIT` 10.000, `TILE_LIMIT_BYTES` 2.000.000. Die UI beschreibt die Standardexportgrenze; bei einer Änderung auch den Oberflächentext anpassen. Basiskarten über `NUXT_PUBLIC_BASEMAP_URL` (Raster-URL mit z/x/y) und `NUXT_PUBLIC_BASEMAP_ATTRIBUTION`; beide müssen vorhanden sein. Keine externe Karte wird vorausgesetzt.

Logs enthalten JSON-Einträge mit Request-ID, Pfad ohne Suchparameter, Status und Dauer. SQL-Fehlerdetails oder Zugangsdaten werden nicht öffentlich ausgegeben. Query-Timeouts werden mit einem stabilen 503-Fehlerformat behandelt. Für unveränderte produktive Deployments gegebenenfalls Access-Logs der Infrastruktur ebenfalls von Suchparametern bereinigen.

Proxy-Header der API werden standardmäßig nicht vertraut. nginx entfernt eingehende Forwarded-Header; die App benötigt sie derzeit nicht für Links. Bei einem späteren vorgeschalteten HTTPS-Proxy dessen genaue Netzgrenzen und nginx-realip-Konfiguration bewusst festlegen. Niemals `forwarded-allow-ips=*` auf einem direkt erreichbaren API-Port einsetzen.

## HTTPS und Freigabe

Für öffentlichen Betrieb einen kontrollierten Hostnamen, HTTPS-Terminierung und ACME-Zertifikatsverwaltung am eigenen Reverse Proxy einrichten. Zertifikatsdateien schreibgeschützt einbinden, Verlängerung und Reload testen. Die lokale Beispielkonfiguration erzeugt keine Domain, keine Zertifikate und öffnet keine produktiven Ports. Security-Updates und vollständige Containerprüfung sind vor Freigabe erforderlich. Bei Hosting einer Zusatzbasiskarte deren Lizenz, Attribution und Kapazitätsbedingungen prüfen.

## Backup und Restore

```sh
docker compose --env-file .env -f infra/compose.yaml exec -T db pg_dump -U atlas_owner -d atlas -Fc --no-owner > atlas.dump
# In einer getrennten Testinstanz mit denselben PostgreSQL-/PostGIS-Versionen:
createdb -h TESTHOST -U RESTORE_OWNER atlas_restore
pg_restore -h TESTHOST -U RESTORE_OWNER -d atlas_restore --no-owner --exit-on-error atlas.dump
psql -h TESTHOST -U RESTORE_OWNER -d atlas_restore -c 'SELECT * FROM publication'
```

Zugangsdaten über `.pgpass` (0600) oder sichere Laufzeitgeheimnisse bereitstellen. Keine Passwörter in Shellhistorie schreiben. `pg_dump` enthält Fachschema, Daten, Quellenmetadaten und aktiven Zeiger, keine Clusterrollen; Rollen separat sicher dokumentieren und im Ziel mit den beschriebenen Minimalrechten anlegen. Originalarchive samt Prüfsummen separat sichern. Backups verschlüsselt und außerhalb des Datenvolumes aufbewahren, Wiederherstellung regelmäßig üben.

Der mitgelieferte praktische Test `pnpm test:e2e --restore` erstellt einen Custom-Dump einer lokalen Testdatenbank, stellt ihn in einer neuen zufällig benannten `atlas_restore_*`-Datenbank wieder her, vergleicht Orte, Grenzen, Einwohner, Publikationszeiger und Geometrievalidität und entfernt anschließend nur diese temporäre Zieldatenbank. Das Ergebnis steht in `artifacts/restore-check.json`.

## Bereits eingerichtete lokale Abnahmeumgebung

Die frühere Abnahmeumgebung verwendete den isolierten PostgreSQL-Cluster unter `/tmp/ortsnamenatlas-pg`, Port 55439. `atlas_dev` war die separate BKG-Entwicklungsdatenbank; `atlas_test*` sind ausschließlich Testdatenbanken. Der lokale Helfer `pnpm test:e2e --import-bkg` migriert weiterhin ausschließlich `atlas_dev` im Testcluster, setzt getrennte Runtime-/Importrechte, importiert `data/bkg-2024-r3.json`, veröffentlicht nur nach erfolgreicher Prüfung und prüft Idempotenz plus Liste/Statistik/Export. Er überschreibt keinen vorhandenen Import mit anderer Prüfsumme. Die vorherigen fehlgeschlagenen/abgebrochenen Versuche `bkg-2024` und `bkg-2024-r2` bleiben als Berichte erhalten. Die reguläre lokale Einrichtung auf Port 5432 ist oben beschrieben.

Nach erfolgreicher Freischaltung und beim Upgrade zuerst alle Migrationen bis einschließlich 0003 mit der Schemaeigentümerverbindung ausführen. Migration 0003 berechnet die Darstellungsgeometrien bestehender Verwaltungsgrenzen einmalig; sie benötigt eine Tabellensperre und sollte vor dem Neustart der Anwendung laufen. Ein erneuter Import ist nicht erforderlich. Die bestehende Runtime-Rolle benötigt weiterhin nur SELECT. Der Vorschauhelfer selbst migriert oder importiert nichts.

```sh
MIGRATION_DATABASE_URL=postgresql+psycopg://awendelk@127.0.0.1:55439/atlas_dev uv run alembic upgrade head
pnpm build
pnpm preview:local
# http://127.0.0.1:8080, beendet mit Strg+C
```

Dies startet Python/FastAPI, den gebauten Nuxt-Server und den lokal installierten nginx. Es verändert keine Daten. Wer ausdrücklich den alten Testcluster verwenden möchte, muss für den Vorschauaufruf `DATABASE_URL=postgresql+psycopg://atlas_runtime@127.0.0.1:55439/atlas_dev` setzen. Sonst wird die Verbindung aus `.env` bzw. der Standard auf Port 5432 verwendet.

`pnpm test:e2e --real-browser` prüft den bereits veröffentlichten vollständigen BKG-Bestand im Browser. `--benchmark` misst diesen Bestand und schreibt `artifacts/benchmark.json`; `--benchmark-short` misst zusätzlich die wenig selektive Enthält-Suche nach einem einzelnen `a`. `--restore-real` verwendet `atlas_dev` als Dumpquelle und restauriert ausschließlich in eine neue Wegwerfdatenbank. Diese lokalen Helfer sind ausdrücklich auf die beschriebene Abnahmeumgebung zugeschnitten; die allgemeine Import-/Betriebsschnittstelle bleibt die CLI bzw. Compose.


## Prozessdiagnose und Portkonflikte

```sh
pnpm local:status
pnpm local:stop
pnpm dev
# Alternativ nach pnpm build:
pnpm preview:local
```

Vor einem Stopp liest der Helfer vollständige Kommandozeilen, Arbeitsverzeichnisse, Elternprozesse/Cgroups, Socketbesitzer und Health-Endpunkte. Bei eindeutig zugeordnetem nginx liest er dessen Konfiguration und `nginx -T`; die neue `/health/proxy`-Kennung enthält zusätzlich die tatsächlich konfigurierten lokalen Upstreams. Auch der frühere Webport 3001 wird geprüft. Ein vorhandenes Konfigurationsfile allein beweist keinen laufenden nginx. Die Grenzen der sichtbaren Prozess-/Netzwerk-Namespace werden ausdrücklich protokolliert.

Der Startmanager sperrt seinen Lebenszyklus pro Projektpfad und Portprofil, prüft **alle** Ports vor dem ersten Start und vergleicht Projekt-, Quellstand- und Moduskennungen. Readiness benötigt einen veröffentlichten echten Datenbestand, das Raster aus Migration 0002 und die Darstellungsgeometrien aus Migration 0003. Ein veralteter Build wird mit der Aufforderung `pnpm build` abgewiesen. Ein zweiter identischer Start verwendet die Instanz wieder; ein Moduswechsel verlangt den regulären Stopp des alten Managers. Nuxt/Listhen erhält `alternativePortRange: []` und `random: false`; auch ein Rennen nach der Portprüfung darf keinen anderen Frontendport wählen.

Bei Fehler, Zeitüberschreitung, Strg+C oder SIGTERM werden nur die vom Manager gestarteten Prozessgruppen beendet und abgewartet (nginx über SIGQUIT, Python/Node über SIGTERM). Ausschließlich diese eigenen Gruppen erhalten nach acht Sekunden erforderlichenfalls SIGKILL. Wiederverwendete Dienste werden nicht beendet. Die PID-Datei wird gegen `/proc`-Startzeit, Projektpfad und Managerkommando geprüft; PID-Wiederverwendung führt zu keinem Fremdstopp. Während des Aufräumens werden keine neuen Kinder gestartet.

`pnpm local:stop` erkennt zusätzlich ältere Projektstarts ohne Managerdatei anhand der aktuellen Socketbesitzer und ihrer Elternprozesse. Ein bekanntes Startkommando, ein Arbeitsverzeichnis innerhalb dieses Projekts, derselbe Benutzer und eine lesbare Prozessstartzeit sind erforderlich. Ein alter `scripts/preview.mjs`-Manager wird einmal signalisiert, damit er seine Kinder selbst beendet. Andernfalls werden eindeutig zugeordnete `serve-real.py`-/Atlas-Uvicorn-, gebaute Nuxt- und Nuxt-Dev-Starts mit SIGTERM beendet; nginx direkt nur über seinen bekannten lokalen Master mit SIGQUIT. Startzeit, Kommando, Benutzer, Arbeitsverzeichnis, Cgroup und Elternprozess werden unmittelbar vor dem Signal erneut verglichen. Es werden keine negativen PID-/Gruppensignale und kein SIGKILL für alte Einzelstarts verwendet. PM2, Supervisor und benannte systemd-Dienste werden ausgewiesen und müssen über ihren zuständigen Manager beendet werden. Fremde oder nicht zugeordnete Dienste bleiben bestehen. Nach dem Stopp werden die Ports erneut untersucht; verbleibende Belegungen oder fehlende Hostsicht ergeben einen Fehlerstatus. Keinesfalls pauschal Python, Node oder nginx beenden. Nach einer Konfigurationsänderung den zugeordneten alten Manager beenden und neu starten. Die generierte nginx-Konfiguration liegt unter dem projektspezifischen Verzeichnis `/tmp/ortsnamenatlas-<Kennung>/nginx/`.

## Datenrollback

```sh
PYTHONPATH=apps/api uv run python -m atlas.cli publish VORHERIGE_VERÖFFENTLICHTE_KENNUNG
```

Dies ändert atomar den aktiven Zeiger, löscht keine Daten und erhält explizit versionierte Links. Nach Änderungen Readiness, Liste, Statistik und eine Kachel prüfen. Alte Versionen nur nach einer eigenen dokumentierten Aufbewahrungsentscheidung entfernen; nicht automatisch beim Import.

## Rasterprüfung ohne Netzwerk

`PYTHONPATH=apps/api .venv/bin/python scripts/check-grid-offline.py --real` erzeugt einen neuen Wegwerfcluster unter /tmp und führt die Produktions-Rasterabfragen mit PostgreSQL im Single-User-Modus und echtem PostGIS aus. Bestehende Datenbanken werden nicht kopiert oder verändert. `--real` erfordert das vorhandene Bundle data/bkg-2024-r3.json und PostGIS 3.6 für PostgreSQL 18; POSTGRES_BIN kann den Binärpfad ändern. Dies ersetzt keinen Netzwerktest der Rollen/Transaktionen, keinen Browser und keine Screenshots. `scripts/audit-gn250.py` prüft die lokale GN250-Quelldatei samt Archivhash. Ergebnisse stehen unter docs/reports/.
