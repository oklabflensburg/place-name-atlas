# Zehn vergleichbare Endungskarten

**Historischer Stand vor der Referenzkorrektur.** Die aktuelle Kreiszeichnung, beide Farbmodi, explizite Varianten und der überarbeitete Start sind in [reference-correction.md](reference-correction.md) dokumentiert. Die folgenden Aussagen zu Rasterflächen und einer festen Skala gelten für den damaligen Stand.

Produktkorrektur vom 21.10.2026. Die Hauptansicht ist jetzt die Übersicht mit zehn Karten. **Die Umsetzung ist noch nicht vollständig abgenommen: Browserprüfung, neue Screenshots und Migration der bestehenden lokalen Datenbank sind durch die Ausführungsbeschränkungen dieser Sitzung offen.**

## Verhalten

Die Startauswahl lautet in Reihenfolge: -ach, -ingen, -zell, -heim, -hausen, -dorf, -bach, -itz, -ow, -by. Es handelt sich um eine redaktionelle Auswahl. Jede Karte hat Titel, eindeutige Trefferzahl, Änderungsaktion, Zellinformationen und Vergrößerung. Die Eingabe schlägt zusätzlich -ing, -burg, -berg, -bek, -büttel, -büll, -leben und -rode vor.

Das Raster verwendet fünf Spalten ab 1.251 px, drei bis 1.250 px, zwei bis 850 px und eine bis 540 px. Alle zehn Karten bleiben im Dokument. Die Kartengröße folgt der Breite mit festem Seitenverhältnis; die Seite scrollt ohne feste Gesamthöhe. Region, Ortsart, Datenbestand, Darstellung, Zurücksetzen und Ansicht teilen stehen in einer gemeinsamen Werkzeugleiste. Die ruhige grüne Farbwelt, Serifentitel und bestehende Marke bleiben erhalten.

Die größere Ansicht montiert die vorhandene MapLibre-Komponente mit einem gemeinsamen Regionsausschnitt. Dort ist freies Erkunden möglich; der Unterschied zwischen Punkten und dem Anteilsraster ist ausdrücklich beschriftet. Zurück erhält Endungen und Filter. Die Methodenseite erhält denselben URL-Zustand. URL-Vertrag v2 enthält die zehn Endungen in Reihenfolge, Region, Ortsart, explizite Datenkennung, Darstellungsmodus und Rasterkennung. Alte v1-Links werden sichtbar zurückgewiesen.

SVG benötigt keinen WebGL-Kontext für die Übersicht. Gemeinsame Rasterpfade stehen einmal in SVG-Definitionen und werden pro Karte referenziert. MapLibre wird nur bei geöffneter Detailansicht verwendet. Die Übersicht lädt eine gemeinsame Geometrie und eine gebündelte Auswertung für zehn Endungen, keine initialen Ortsobjekte oder langen Namenslisten. Geometrie wird bei Endungs-/Ortsartänderungen wiederverwendet.

## Berechnung und Raster

Gestalterische Referenz: [Moritz Stefaner, -ach, -ingen, -zell](https://truth-and-beauty.net/experiments/ach-ingen-zell/), insbesondere vergleichbare kleine Karten, relative Zellhäufigkeiten und literale Endungen. Die verlinkte [Repository-Dokumentation](https://github.com/MoritzStefaner/ach-ingen-zell) erläutert SVG, React und Hexbin. Es wurde kein fremder Implementierungscode übernommen. Die BKG-Quellen bleiben verbindlich.

Rasterkennung `laea-3035-square-20000-origin-0-v1`: Quadrate mit 20.000 m Kantenlänge, Ursprung (0 m, 0 m), flächentreues EPSG:3035. Zellindex `floor(x/20000), floor(y/20000)`, also halboffene Zellen. PostGIS `ST_SquareGrid` erzeugt dazu dieselben Flächen. Es gibt keine Einteilung in Grad. SVG zeigt die metrische Geometrie direkt; lediglich die y-Achse wird für SVG gespiegelt. Die Detailkarte erhält aus demselben Ausschnitt transformierte WGS84-Grenzen.

Migration 0002 berechnet gespeicherte generierte `grid_x/grid_y`-Spalten für vorhandene und zukünftige Ortsobjekte. Ein Index auf `(dataset_id, grid_x, grid_y, kind)` unterstützt Zelllisten. Die aggregierte API berechnet in einer SQL-Abfrage einen Nenner und alle zehn Zähler pro belegter Zelle. Zellen ohne Ortsobjekte stehen in der Geometrie, fehlen aber in der Werteantwort: Nenner 0, Anteil nicht definiert. Vorhandene Orte ohne Treffer ergeben Zähler 0 und Anteil 0 %.

Die Grundmenge entspricht der Datenversion sowie Regions-, Ortsart- und gegebenenfalls API-Ausschnittfiltern. Nur der Zähler benutzt die Namensendung. `UNIQUE(dataset_id,place_id)` und `EXISTS` über Namen verhindern Mehrfachzählung durch Varianten. Einwohner werden nicht verwendet. Originalnamen und NFC–Casefold–NFC bleiben erhalten. „Kirchbach“ passt zu „ach“ und „bach“; Kartenwerte werden nicht summiert. „ing“ und „ingen“ sind getrennte Muster.

VG25-Geometrien werden ausschließlich für die Darstellung in EPSG:3035 um 150 m vereinfacht und an Zellen beschnitten. Die tatsächliche Regionszuordnung benutzt unveränderte VG25-Geometrien mit ST_Covers. Alle Karten haben dieselbe viewBox und dieselben Zellpfade. Jede Farbe hat überall denselben Wert: 0; >0 bis <1; 1 bis <2; 2 bis <5; 5 bis <10; 10 bis <20; 20 bis 100 Prozent. Keine Normalisierung je Karte. „Keine Daten“ wird gesondert grau angezeigt.

Das Raster ist anhand der vorhandenen 45.858 GN250-Ortsobjekte begründet: 1.006 belegte Zellen, Median 45 Orte, Quartile 32 und 58, Minimum 1, Maximum 126. 66 belegte Zellen haben weniger als zehn Orte; die Zellinformation kennzeichnet diese niedrigen Fallzahlen. Von 1.062 dargestellten Zellen haben 56 keine erfassten Orte. 20 km erhalten damit erkennbare regionale Muster bei im Binnenland meist mehreren Dutzend Ortsobjekten. Ein feineres Raster würde besonders am Rand die kleinen Fallzahlen verstärken. GN250 bleibt eine maßstabsbezogene Auswahl, keine vollständige Siedlungszählung.

## Datenumfang und Befund zu 9.790

Die Originaldatei `data/gn/gn250/GN250.csv` und der fixierte Archivhash wurden erneut geprüft. Der Adapter `bkg.prepare` setzt ohne `municipalities` keinen AGS-Ausschnittfilter; `manifest-r3.json` hat keinen solchen Ausschnitt. Der Importer übernimmt `AX_Ortslage`, sofern nicht virtuell und mit gültigem Namen. Er filtert **nicht** nach GEMTEIL=Nein und verwendet **nicht** nur AX_Gemeinde.

| Prüfung | Ergebnis |
|---|---:|
| Sämtliche GN250-Quellzeilen | 172.403 |
| AX_Ortslage vor Ausschlüssen | 46.824 |
| Virtuelle Ortslagen ausgeschlossen | 966 |
| Ungültige leere Ortsnamen zusätzlich ausgeschlossen | 0 |
| Übernommene eindeutige NNID | 45.858 |
| GEMTEIL=Nein / interne Ortsart settlement | 9.790 |
| GEMTEIL=Ja / interne Ortsart district | 36.068 |
| Ortsobjekte mit NAME2-Variante | 1.238 |
| AX_Gemeinde, nicht zusätzlich als Ortslage gezählt | 10.956 |

9.790 entspricht exakt der Teilmenge ohne Gemeindeteile. Die frühere Bildschirmzahl allein beweist keinen Importfehler; ohne den ursprünglichen UI-Zustand lässt sich nicht behaupten, welcher Filter damals gesetzt war. Der vorliegende Import enthält beide Ortsarten; die neue Übersicht startet mit beiden. Es wurden weder zusätzliche Orte erfunden noch gleichnamige Objekte zusammengelegt. Orte werden über NNID identifiziert; NAME2 ist eine Variante desselben Objekts. Der ältere geprüfte Datenbankbericht bestätigt dieselbe Aufteilung, konnte wegen des blockierten Datenbankzugriffs in dieser Sitzung aber nicht erneut gegen die laufende Datenbank verifiziert werden.

[Reproduzierbarer Quellenaudit](reports/gn250-selection-audit.json), erzeugt durch `PYTHONPATH=apps/api .venv/bin/python scripts/audit-gn250.py`. Die SQL-Prüfung lud das vorhandene Importbundle separat in eine neue Wegwerfdatenbank, ohne die laufende Datenbank zu ändern.

Echte bundesweite Trefferzahlen in der Reihenfolge der Karten: 3.218; 1.342; 153; 1.323; 2.088; 3.933; 2.711; 1.256; 916; 60. Sie wurden unabhängig an der originalen CSV und mit PostGIS am vorbereiteten Bundle überprüft.

## API, Zustände und Interaktion

- `GET /api/v1/grid/geometry`: gemeinsame Pfade, Zellkennungen, Rasterdefinition, projizierte viewBox und Detailgrenzen; ohne Namenslisten.
- `GET /api/v1/grid/values`: alle zehn Zähler, gemeinsame Nenner und Kartensummen aus einem versionierten Filter.
- `GET /api/v1/grid/cells/{cell}/places`: paginierte Ortsnamen erst bei Bedarf, inklusive passender Namensvarianten und überprüfbarer Zähler/Nenner.

Hover lädt höchstens acht Namen. Tippen/Klick und die Tastaturaktion „Zellwerte“ öffnen einen nativen Dialog mit Zellenauswahl. Längere Listen öffnen eine vollständige paginierte Ansicht mit 50 Namen je Seite; die API begrenzt auf höchstens 100. Native Dialoge bieten Fokusbindung, Escape und Fokusrückgabe. Diese Browserfunktionen sind implementiert, aber in dieser Sitzung nicht im Browser abgenommen.

Zehn Kartenplatzhalter sind bereits im initialen Dokument vorhanden. Kein Bestand, API-Fehler und leere Treffer sind getrennte Zustände. Fehler haben eine Wiederholungsaktion. AbortController und Antwortzähler verhindern veraltete Raster-, Versions-, Regions- oder Zellantworten. Der serverseitige LRU-Cache ist pro Worker auf 24 MiB begrenzt und enthält Datenkennung, Fingerprint, Rasterdefinition und wirksame Filter/Muster im Schlüssel. Fehler sind no-store.

## Tatsächlich ausgeführte Prüfungen

| Prüfung | Tatsächliches Ergebnis |
|---|---|
| `pnpm test` | 10 Tests bestanden, einschließlich URL-v2, zehn Endungen, gemeinsame Filter und Skala |
| `.venv/bin/python -m pytest -q` | 19 bestanden, 20 räumliche/DB-Tests ohne erreichbare Testdatenbank ausdrücklich übersprungen; eine bestehende TestClient-Deprecation-Warnung |
| `scripts/check-grid-offline.py --real` | Bestanden: Produktions-SQL mit PostGIS, synthetischer Bestand (19 Orte), Referenzfall (40 Orte) und echter GN250-Bestand (45.858 Orte) |
| Jede Rasterzelle | Zehn Zähler und der Nenner stimmen mit einer separaten Python-Auswertung überein |
| Dedup-/Anteil-Referenzfall | Genau 10 passende von 40 eindeutigen Orten = 25 %, trotz jeweils mehrerer passender Varianten |
| `scripts/audit-gn250.py` | Original-CSV und Archiv-SHA-256 geprüft; Trefferzahlen stimmen auch unabhängig vom Bundle |
| `pnpm typecheck` | Bestanden |
| `pnpm build` | Produktionsbuild bestanden |
| OpenAPI-/Client-Neugenerierung | Reproduzierbar; kanonischer Export und generierter Client stimmen überein |
| `node scripts/check-ssr.mjs` | Produktionsrenderer ohne Listener direkt aufgerufen: Status 200, zehn Karten und Startendungen im HTML vor Hydration; Methodenseite enthält Raster-/Daten-/Überlappungserklärung |
| `pnpm exec playwright test --list` | 12 synthetische und 2 echte Desktop-/Mobil-Testfälle werden erfolgreich eingelesen; keine Browserausführung |
| Chromium-Start | Durch Ausführungsrichtlinie blockiert; keine neue Screenshot-Datei |
| Laufende Datenbank/HTTP-Stack | Zugriff blockiert; Migration der vorhandenen DB, Read-only-Transaktionen und reale HTTP-Aufrufe nicht erneut geprüft |

[Prüfung des initialen HTML](reports/grid-ssr-check.json). Der SSR-Test ersetzt den Netzwerk-Listener ausschließlich im Test durch eine No-op-Funktion und verwendet Nitros internen `localFetch`. Er führt keinen Browser, keine Hydration und keinen visuellen Layouttest aus. Die Netzwerksperre betrifft sowohl TCP als auch lokale Datenbank-Sockets; eine Eskalationsanfrage wurde von der Richtlinie abgewiesen. Der Chromium-Start scheiterte mit `sandbox_host_linux.cc:41 … shutdown: Operation not permitted`. Daher werden hier keine Browserprüfung und keine Screenshots behauptet.

PostGIS kann ohne Netzwerksocket im Single-User-Modus arbeiten. `scripts/check-grid-offline.py --real` erstellt dafür ausschließlich einen neuen temporären Cluster. Es führt die Produktionsmigrationen und Produktions-Rasterabfragen aus, lädt synthetische Prüfdaten und das tatsächliche BKG-Bundle und prüft jedes Zellpaar aus Zähler und Nenner gegen eine unabhängige Python-Auswertung. Das ist eine echte SQL-/PostGIS-Prüfung, aber kein Test des laufenden HTTP-Servers, des Runtime-Rollenmodells oder der Wiederverwendung derselben Transaktion.

[SQL-Prüfbericht](reports/grid-sql-check.json) enthält Fallzahlen, Datenmengen und Laufzeiten. Die unkomprimierte gemeinsame Deutschlandgeometrie beträgt rund 292 KB, die gebündelte Werteantwort rund 66 KB. Kaltmessungen enthalten den Start eines Single-User-Backends und sind kein HTTP-Benchmark.

## Noch erforderliche Abnahme

In einer Umgebung mit erlaubten lokalen Verbindungen:

```sh
# Schemaeigentümerverbindung, nicht Runtime-Rolle:
MIGRATION_DATABASE_URL=postgresql+psycopg://awendelk@127.0.0.1:55439/atlas_dev uv run alembic upgrade head
pnpm test:e2e --backend
pnpm build
pnpm test:e2e --production
pnpm test:e2e --real-browser
```

Die überarbeiteten Playwright-Tests decken nach ihrer Ausführung folgende Abnahme ab: Desktop und Pixel-7-Viewport, echte Zähler/Nenner, gemeinsame viewBox, Filterwechsel, URL-Rückkehr, leere/fehlerhafte Antworten, Touch/Klick, Zelllisten, Detailansicht und Accessibility. Bei erfolgreicher Ausführung schreiben sie neue Dateien `artifacts/overview-desktop-real.png`, `artifacts/overview-mobile-real.png` sowie Zell- und synthetische Ansichten. **Diese Dateien existieren aus dieser Sitzung noch nicht.** Die früheren Artefakte zeigen die alte Produktansicht und sind kein Nachweis für die neue.

Die neue Migration wurde nur im isolierten SQL-Test ausgeführt. Der Import und der Veröffentlichungszeiger der bestehenden Datenbank blieben unverändert. Kein Deployment oder Commit wurde ausgelöst. Die bereitgestellte Arbeitskopie enthält keine lesbaren Git-Metadaten; ein Git-Diff/Commit ist hier ebenfalls nicht möglich.
