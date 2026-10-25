# Ortsnamenatlas

Ein selbst hostbarer Ortsnamenatlas für OK Lab Flensburg. Frei ergänzbare literale Namensendungen auf vergleichbaren kleinen Karten erkunden, beginnend mit zehn Vorschlägen. Gemeinsame Region, Ortsart und Datenversion; eigene Anteilsfarbskalen als Standard und eine gemeinsame Vergleichsskala; jede Endung ist einzeln bearbeitbar und entfernbar, die Karten sind umordnungsfähig. Zellwerte, Ortsnamen, vergrößerte Detailkarte und teilbare Ansichten. Zeichenübereinstimmungen sind kein Beleg für Etymologien.

Stack: nginx · PostgreSQL/PostGIS · Python/FastAPI/Pydantic v2/SQLModel · Nuxt 4/Nuxt UI/SVG (Detailkarte: MapLibre) · uv/pnpm · Docker Compose. Quellen: **VG25 für Grenzen, VG250-EW für Einwohnerzahlen und GN250 für Ortsnamen**.

**Deployment:** Die vollständige [Server-Anleitung](docs/deployment.md) beschreibt Docker Compose, eigene Zugangsdaten, BKG-Import, HTTPS mit Caddy, Updates, Monitoring, Backups und Wiederherstellung. Der Quellcode liegt unter [oklabflensburg/place-name-atlas](https://github.com/oklabflensburg/place-name-atlas).

Tatsächlich lokal freigeschaltet: **45.858 GN250-Ortsobjekte**, VG25 und VG250-EW zum **31.12.2024**, 10.956 eindeutig verknüpfte Gemeinde-Einwohnerwerte. GN250 ist eine maßstabsbezogene Auswahl, keine vollständige Ortsteilliste. 17 Quellen-/Lagekonflikte bleiben ausdrücklich ohne Gemeindezuordnung. [Abnahme und Grenzen](docs/test-results.md).

Eine neue Installation benötigt die Schema-Migrationen einschließlich **0003** mit der Eigentümerverbindung (`MIGRATION_DATABASE_URL=… uv run alembic upgrade head`), anschließend `pnpm build` und `pnpm preview:local`. Migration 0002 berechnet die Orts-Zell-Zuordnung auch für vorhandene Orte. Migration 0003 speichert projizierte, vereinfachte Darstellungsgrenzen, damit diese beim ersten Kartenaufruf bereits vorliegen. Der geprüfte lokale BKG-Bestand liefert bereits 1.006 belegte Rasterzellen; für die Darstellungskorrektur wurde weder zurückgesetzt noch neu importiert. Aufruf: **http://127.0.0.1:8080**. Einrichtung auf einem anderen Rechner siehe unten. Docker Compose ist bereitgestellt, wurde in dieser Umgebung mangels Dockerzugriff aber nicht ausgeführt.

Die Korrektur anhand des vollständigen Referenzcodes, Raster- und Farbentscheidungen stehen in [docs/reference-correction.md](docs/reference-correction.md). Die aktuelle Untersuchung der Rasterpunkte mit echten Browserdaten über nginx, Cachekorrektur und Regressionstests steht in [docs/map-rendering-fix.md](docs/map-rendering-fix.md). `pnpm local:diagnose-maps` prüft eine laufende Anwendung und speichert Messwerte und Screenshots in `artifacts/`.

Die Erweiterung um eigene Endungen und die gemessene SQL-Optimierung sind in [docs/dynamic-endings-performance.md](docs/dynamic-endings-performance.md) dokumentiert, einschließlich Einzelmessungen, Cacheverträgen, Tests und der noch ausstehenden Browserabnahme.

Die weitere Beschleunigung des ersten Ladens durch gespeicherte Darstellungsgeometrien und paralleles Laden der Regionsauswahl steht in [docs/initial-load-performance.md](docs/initial-load-performance.md).

## Lokal starten

```sh
cp .env.example .env
docker compose --env-file .env -f infra/compose.yaml up --build -d
docker compose --env-file .env -f infra/compose.yaml run --rm importer import tests/fixtures/synthetic.json
docker compose --env-file .env -f infra/compose.yaml run --rm importer publish synthetic-v1
```

Dann `http://127.0.0.1:8080`. Die anfängliche Fixture ist ausdrücklich **synthetisch**, kein Deutschlandimport. Den tatsächlich geprüften Datenumfang und ausgeführte Prüfungen dokumentiert [docs/test-results.md](docs/test-results.md).

Ohne Docker: Python 3.13, PostgreSQL 18/PostGIS 3.6, Node 22.22.1+, uv 0.12.5 und pnpm 12.14.0 installieren und die reguläre PostgreSQL-Instanz auf Port **5432** starten:

```sh
uv sync --locked
pnpm install --frozen-lockfile
uv run python scripts/setup-postgres.py
# Einen echten BKG-Bestand importieren und veröffentlichen (siehe unten).
pnpm dev
```

Der Einrichtungshelfer erstellt `atlas`, getrennte Rollen, individuelle Passwörter in `.env` und alle Migrationen über `sudo -u postgres`. Für den vorhandenen lokalen BKG-Bestand stattdessen `uv run python scripts/setup-postgres.py --restore backups/atlas_dev_20261021_215050.dump` verwenden (leere Zieldatenbank erforderlich). Details: [Betrieb ohne Container](docs/operations.md#entwicklung-ohne-container).

Vorgesehener Einstieg für Entwicklung und Vorschau: **http://127.0.0.1:8080**. `pnpm dev` startet den verwalteten Entwicklungsstack; `pnpm build` und danach `pnpm preview:local` die gebaute Vorschau. HTTP-Ports stehen zentral in `infra/local.json` (API 8000, Web 3000, nginx 8080); das Frontend weicht nicht auf einen anderen Port aus. `pnpm local:status` liest Prozesse, Health und Upstreams; `pnpm local:stop` beendet ausschließlich verifizierte Projektprozesse über deren regulären Lebenszyklus. Der Stopphelfer erkennt auch ältere Projektstarts ohne Managerdatei anhand von Socketbesitzer, Kommandozeile, Arbeitsverzeichnis, Benutzer und Prozessstartzeit. Er beendet deren verifizierten Projektmanager bzw. bekannte Einzelstarts regulär; fremde oder unklare Prozesse bleiben bestehen. Passende bereits laufende Instanzen werden wiederverwendet. Fremde oder veraltete Dienste führen vor dem Start weiterer Prozesse zu einer Fehlermeldung. Einrichtung der lokalen Testdatenbank, Rechte und alle Betriebsbefehle: [docs/operations.md](docs/operations.md).

## BKG-Daten importieren

```sh
export PYTHONPATH=apps/api
uv run python -m atlas.cli inspect data/vg25.zip
uv run python -m atlas.cli prepare-bkg data/manifest.json data/bkg-2024.json
uv run python -m atlas.cli import data/bkg-2024.json
uv run python -m atlas.cli report bkg-2024
uv run python -m atlas.cli publish bkg-2024
```

Bezugsadressen, Stichtage, Prüfsummen und Manifest: [Datenquellen](docs/data-sources.md). Pipeline, Freischaltung und Fehlerverhalten: [Importpipeline](docs/import-pipeline.md). Große Daten werden ausschließlich lokal unter ignoriertem `data/` abgelegt.

## Prüfen

```sh
TEST_DATABASE_URL=postgresql+psycopg://TESTBENUTZER@127.0.0.1:55439/atlas_test uv run pytest
pnpm test
pnpm typecheck
pnpm build
make client
pnpm exec playwright install chromium
pnpm test:e2e
pnpm test:e2e --restore
```

`pnpm test:e2e --backend` richtet die dedizierte lokale Testdatenbank über `TEST_ADMIN_URL` ein und führt pytest aus. Die Anwendung benötigt für lokale Tests keine externe Basiskarte. Es werden keine Produktionsserver verändert oder Veröffentlichungen ausgelöst.

Weitere Dokumentation: [Architektur](docs/architecture.md), [Datenmodell](docs/data-model.md), [Suchsemantik](docs/search-semantics.md), [Entscheidungen](docs/decisions/0001-modular-monolith.md).

Quellcode: AGPL-3.0-or-later, siehe [LICENSE](LICENSE). Synthetische Fixtures: CC0-1.0. BKG-Ausschnitte behalten ihre separat dokumentierte Datenlizenz und Quellenangaben.
