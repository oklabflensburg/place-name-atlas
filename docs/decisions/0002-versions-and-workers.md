# ADR 0002: Laufzeitversionen und MapLibre-Worker

Status: angenommen, geprüft 21.10.2026.

Python 3.13.15, PostgreSQL 18/PostGIS 3.6 und Node 22.22.1 bilden die Basis. Die direkten Python-/JavaScript-Abhängigkeiten sind exakt in `pyproject.toml` bzw. den `package.json` fixiert; `uv.lock` und `pnpm-lock.yaml` fixieren den aufgelösten Graphen. Die Containerbasen enthalten zusätzlich Registry-Digests. Keine `latest`-Tags. Betriebssystempakete innerhalb der Images erhalten die zum Buildzeitpunkt verfügbaren Sicherheitsstände; deren vollständiger Paketgraph ist nicht separat archiviert.

Die [Nuxt-4-Installationsdokumentation](https://nuxt.com/docs/4.x/getting-started/installation) verlangt Node 22 oder neuer; Node 22 ist hier bewusst gewählt. [Nuxt UI für Nuxt](https://ui.nuxt.com/docs/getting-started/installation/nuxt) beschreibt das Modul und den CSS-Import für UI 4. Die offiziellen Seiten wurden zusätzlich per HTTP abgerufen, nachdem das Recherchewerkzeug deren Markdown-Antwort nicht verarbeiten konnte.

[MapLibre 6](https://maplibre.org/maplibre-gl-js/docs/) verwendet ESM und einen getrennten Worker. Der [Migrationsleitfaden](https://maplibre.org/maplibre-gl-js/docs/guides/v5-to-v6-migration-guide/) erklärt die Änderungen gegenüber Version 5. Die Anwendung bündelt den Worker gemäß Vite-Anleitung mit `?worker&url`, ruft `setWorkerUrl` auf und initialisiert ausschließlich im Browser. Echte Browserprüfungen prüfen geladene Kacheln und Kartenhöhe; ein erfolgreicher Nuxt-Build allein hätte diese Integration nicht bewiesen.

[FastAPI](https://fastapi.tiangolo.com/async/) führt gewöhnliche `def`-Endpunkte im Threadpool aus; das passt zum synchronen Psycopg-/SQLAlchemy-Zugriff. [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) ist das eigene Paket für Umgebungs-/Dotenv-Konfiguration in Pydantic v2. SQLModel-Tabellen und öffentliche Pydantic-Schemas bleiben getrennt.

Python 3.13 verwendet [Unicode 15.1](https://docs.python.org/3.13/library/unicodedata.html). Dieser Stand gehört zur Suchnormalisierung und wird ausdrücklich getestet. Ein Laufzeitwechsel mit anderem Unicode-Stand verlangt eine neue Normalisierungskennung und Neuaufbau der Suchformen.

[GDAL GeoJSONSeq](https://gdal.org/en/stable/drivers/vector/geojsonseq.html) rundet standardmäßig auf sieben Nachkommastellen. Der Adapter setzt ausdrücklich 15, weil die Rundung dichter VG25-Ringe im ersten tatsächlichen Deutschlandversuch eine ungültige Geometrie erzeugte. Eine Geometriereparatur erfolgt nicht stillschweigend. PostGIS validiert nach der Konversion und vor Veröffentlichung.

Die konkret erfolgreich ausgeführten Versionen und verbleibende Prüfgrenzen stehen in `../test-results.md`; Containerkonfiguration und lokale Laufzeit dürfen dabei nicht gleichgesetzt werden.
