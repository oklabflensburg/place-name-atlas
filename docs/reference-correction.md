# Korrektur anhand von ach-ingen-zell

Aktuelle Ergänzung zur Rasterdarstellung: [Befund, Datenvertrag und Regressionstests](map-rendering-fix.md). Die folgenden Einschränkungen beschreiben den früheren Prüfstand.

Stand: 21.10.2026. Die Implementierung ist korrigiert und die unten aufgeführten Prüfungen wurden ausgeführt. **Die vollständige Browserabnahme über nginx, neue Desktop-/Mobil-Screenshots und die Untersuchung der aktuellen Hostprozesse bleiben wegen der Ausführungsrichtlinie offen.** Es wurden keine fremden oder nicht eindeutig zugeordneten Prozesse beendet.

## Referenz tatsächlich gelesen

Alle sechs angeforderten Dateien wurden vollständig über den verbundenen GitHub-Zugriff gelesen. Dateipfade und Blob-SHAs stehen in [reference-review.json](reports/reference-review.json).

| Referenzdatei | Beobachtung und Umsetzung |
|---|---|
| `src/jsx/main.jsx` | Gemeinsame projizierte Ortsdaten, Hexbinradius 3 in Bildschirmkoordinaten. Hier: gemeinsames metrisches Backend-Raster für alle zehn Karten. |
| `src/jsx/Map.jsx` | Zeichnet **SVG-Kreise mit Radius 2,5**, keine sechseckigen Polygone. Große Endung, Varianten und Trefferzahl pro Karte. Hier: Vue-SVG-Kreise, identische Zentren, Titel, Trefferzahl und bedarfsgeladene Ortsnamen für Hover/Touch. |
| `src/jsx/Map.jsx` | Eigene Maxima je Karte, aber nur aus Zellen mit mehr als 20 Orten. Hier: eigene Maxima als Standard, zusätzlich gemeinsames Maximum; alle belegten Zellen gehen ein. |
| `src/jsx/Map.jsx` | Ein Anteil wird direkt mit Prozentzeichen ausgegeben. Hier: Anteil × 100; 0,25 = 25 %. Keine RegExp-Konstruktion aus Benutzereingaben übernommen. |
| `src/jsx/SuffixList.jsx` | Varianten sind zu Gruppen zusammengefasst, z. B. ing/ingen. Hier: keine stillen Gruppen; Varianten sind optional, einzeln eingegeben und direkt unter dem Titel sichtbar. |
| `src/sass/main.sass` | Gleich große, ruhige Kacheln mit dominierenden geografischen Mustern. Hier: responsives CSS-Grid, fünf Spalten ab 1.251 px, drei bis 1.250, zwei bis 850, eine bis 540 px; vertikales Scrollen. |
| `README.md` | Literales Zeichenende, keine Silben- oder Herkunftsermittlung; Komponenten rendern SVG. Diese Semantik bleibt erhalten. |
| `License.md` | Apache License 2.0, Copyright 2016 Moritz Stefaner. Eigenständige Neuimplementierung ohne kopierten React-/Sass-/Webpack-Code; Herkunft in [NOTICE](../NOTICE), Referenzlizenz unter [LICENSES](../LICENSES/ach-ingen-zell-Apache-2.0.txt). |

Die vorhandene grüne Farbwelt bleibt erhalten; die umgekehrte Viridis-Palette der Referenz wird bewusst nicht kopiert. Vue verwaltet das SVG. Für die einfache lineare RGB-Interpolation und Maxima genügen kleine geprüfte Funktionen; Bildschirmprojektion und clientseitiges D3-Hexbinning werden nicht benötigt. MapLibre bleibt auf die optionale vergrößerte Detailansicht beschränkt. Kein React-/Webpack-Umbau und kein neuer Datenanbieter.

## Karten, Raster und Zähler

Die unveränderte Startauswahl lautet **-ach, -ingen, -zell, -heim, -hausen, -dorf, -bach, -itz, -ow, -by**. Alle zehn Karten sind ohne Anlegen von Gruppen vorhanden. Jede Endung kann unabhängig ersetzt und um höchstens sieben explizite Varianten ergänzt werden. Eine Variante pro Eingabezeile; Kommas bleiben literale Zeichen. URL-Zustand und geteilte Ansichten erhalten die Varianten sowie den Farbmodus. Alte v2-Links mit `mode:share` erhalten weiterhin ihre gemeinsame Vergleichsskala.

Rasterkennung `laea-3035-square-20000-origin-0-v1`: 20.000-m-Quadrate in EPSG:3035, Ursprung (0,0), halboffene Zellzuordnung `floor(x/20000), floor(y/20000)`. Ein Kreis liegt bei `((i+0,5)×20000, −(j+0,5)×20000)` im SVG; Radius 8.200 m, also 41 % der Zellkante. Alle Karten bekommen dieselben Zentren, Radien und dieselbe gepolsterte viewBox. Es werden **Kreise**, keine Zellpolygone gefüllt. Das metrische Quadratgitter ist eine bewusste methodische Abweichung vom historischen Bildschirm-Hexbinning: reproduzierbare Zuordnung unabhängig von Bildschirmgröße und Projektion des Browsers. Kreispositionen ändern sich nicht bei Endungs- oder Ortsartwechsel.

Migration 0002 und das Backend berechnen die gespeicherte Ortszuordnung und gebündelt alle zehn Zähler/Nenner. GN250 liefert Ortsobjekte, VG25 Grenzen und Regionszuordnung, VG250-EW Einwohner auf Verwaltungsebene. Die tatsächliche Regionsauswahl benutzt die unveränderten VG25-Geometrien; die vereinfachte Ausgabe dient nur der Anzeige. Einwohner gehen nicht in die Ortsanteile ein.

Die vorhandenen validierten Filter werden als gebundene SQL-Parameter kompiliert. `EXISTS` über Namen und eindeutige Ortsidentitäten zählen einen Ort pro Karte einmal, auch bei mehreren passenden Namen oder Endungsvarianten. Karten dürfen überlappen; ihre Summen werden nicht addiert. Die Gesamtanzeige zählt die gemeinsame Grundgesamtheit ohne Namensfilter.

## Farbmodi und Grenzfälle

- **Muster hervorheben** (Standard): linearer Wertebereich 0 bis zum größten Zellanteil **dieser Karte**. Legende unter jeder Karte. Gleiche Farben können verschiedene Anteile bedeuten.
- **Anteile vergleichen**: linearer Wertebereich 0 bis zum größten Zellanteil **aller zehn Karten**. Eine gemeinsame Legende sowie identische Bereiche unter allen Karten. Derselbe Anteil erzeugt überall exakt dieselbe RGB-Farbe.

Alle belegten Zellen zählen für die Maxima, auch bei nur einem Ort. Die Schwelle der Referenz wird bewusst nicht übernommen: Sie könnte dünn besetzte Karten ohne gültiges Maximum lassen oder hohe Anteile außerhalb des Bereichs zeichnen. Es gibt kein Quantil-Clipping. Ein passender von einem Ort ergibt 100 % und bestimmt nötigenfalls die Obergrenze. Unter zehn Orten weist die Zellinformation auf die geringe Fallzahl hin. Der Vergleichsmodus kann dadurch schwache Muster zurückhaltender zeigen; hierfür bleibt der Standardmodus verfügbar.

Null Treffer: eigener Bereich 0 %, sichtbare Karte und explizite Leermeldung. Nenner > 0 und Zähler 0: sehr helles Grün, 0 %. Nenner 0: grau, „Keine Daten“, undefinierter Anteil. Das ist kein Nullwert. Auch sehr kleine positive Anteile bleiben von 0 % unterscheidbar; Prozentformatierung zeigt bei Bedarf zusätzliche Dezimalstellen. Wechsel des Farbmodus benötigt keine neue API-Anfrage. Endungs-/Regionswechsel berechnen die wirksamen Bereiche neu.

## Startkonflikt: Befund und Korrektur

Nachweisbar im alten Startcode und in der vorhandenen `/tmp/ortsnamenatlas-nginx/nginx.conf`: nginx verwendete `127.0.0.1:3001`, der separate Nuxt-Entwicklungsstart standardmäßig 3000. Der alte Vorschauhelfer startete bei jedem Aufruf erneut ein Backend auf 8000. **Ob die aktuell laufenden Hostprozesse genau diese Konfiguration verwenden und welches Frontend der Browser erhielt, konnte nicht nachgewiesen werden.** Die alten PIDs wurden nicht als aktuelle Prozesskennungen verwendet.

Der neue read-only-Aufruf `pnpm local:status` untersucht Socketbesitzer, vollständige Kommandozeile, Arbeitsverzeichnis, Elternprozess/Cgroups, Health und nginx-Konfiguration einschließlich Upstreams. Port 3001 bleibt als Diagnosekandidat enthalten. Ein vorhandenes File wird ausdrücklich nicht als Beweis eines aktiven nginx behandelt. Der aktuelle [Diagnosebericht](reports/local-process-audit.json) zeigt nur die isolierte Namespace: kein sichtbarer Hostprozess, fehlgeschlagene lokale Health-Aufrufe und `ss` mit „Operation not permitted“. Das ist kein Beleg, dass die Hostports frei wären.

Die lokale HTTP-Konfiguration liegt jetzt zentral in `infra/local.json`: API **8000**, Web **3000**, nginx **8080**, Host **127.0.0.1**. Beide vorgesehenen Startarten nutzen dieselben nginx-Upstreams. Der Manager prüft alle Ports, Projekt-/Quellstand-/Moduskennungen, Build-Aktualität, Datenbereitschaft und die Upstreams über nginx. Passende Instanzen werden wiederverwendet; belegte fremde oder veraltete Dienste führen vor dem Start weiterer Kinder zu einer verständlichen Meldung. Nuxt/Listhen erhält keine Alternativports und keinen Zufallsport. Details und regulärer Stopp: [Betrieb](operations.md#prozessdiagnose-und-portkonflikte).

Bei fehlgeschlagenem Start beendet und erwartet der Manager ausschließlich seine eigenen Prozessgruppen. Bereits wiederverwendete Dienste bleiben bestehen. Der Stopp prüft zusätzlich PID-Startzeit, Managerkommando und Arbeitsverzeichnis und protokolliert die Diagnose vor dem Signal. Es gibt kein pauschales `pkill`. Synthetische Browsertests verwenden getrennte Ports aus `infra/test-local.json` und ausschließlich ihre Testdatenbank.

## Tatsächlich ausgeführte Prüfungen

Zusammengefasster maschinenlesbarer Stand: [reference-validation.json](reports/reference-validation.json).

| Prüfung | Ergebnis |
|---|---|
| `pnpm test` | 17 Tests bestanden: Startauswahl, URL-Zustand/Varianten, eigene/gemeinsame Maxima, Farben, Prozentwerte, leere/extreme Zellen sowie Portprüfung, Upstreams, Wiederverwendung und Prozessgruppen-Aufräumen mit simulierten Kindprozessen. Kein realer Prozess-Lebenszyklustest. |
| `.venv/bin/python -m pytest -q` | 20 bestanden, 20 PostGIS-/HTTP-Integrationstests ohne erreichbare Datenbank explizit übersprungen; eine bestehende TestClient-Deprecation-Warnung; die lokale Herkunftsantwort ist als Funktionsprüfung ohne HTTP-Listener oder Datenbank getestet. |
| `PYTHONPATH=apps/api .venv/bin/python scripts/check-grid-offline.py --real` | Produktions-SQL mit echtem PostgreSQL/PostGIS in einem neuen temporären Single-User-Cluster bestanden. Synthetische Daten (19 Orte), 10/40 = 25 %, ein einzelner Ort = 100 % und echter Bestand (45.858 Orte). Jeder Zellzähler und -nenner gegen eine unabhängige Python-Auswertung, explizite Varianten, alle zehn Karten ohne Treffer, Regions-/Ortsartfilter, Zentren, Namenslisten und Pagination. [SQL-Bericht](reports/grid-sql-check.json). |
| `pnpm typecheck` | Bestanden. |
| `pnpm build` | Produktionsbuild bestanden; der Vorschauhelfer prüft dessen Quellfingerprint. |
| OpenAPI/Client-Neugenerierung | Neu erzeugt; enthält Kreiszentren und lokale Herkunftsprüfung. |
| `node scripts/check-ssr.mjs` | Produktions-SSR in-process ohne Listener: zehn initiale Karten und Methodenseite. Kein Browser-, Hydrations- oder Layoutnachweis. [SSR-Bericht](reports/grid-ssr-check.json). |
| Playwright `--list` | 12 synthetische sowie zwei echte Desktop-/Mobilfälle werden eingelesen. Das ist keine Ausführung der Browserfälle. |
| `pnpm dev`, `pnpm preview:local` | Lokale Portprüfung scheitert an `EPERM` der Ausführungsrichtlinie. Keine Dienste gestartet; kein weiterer Backendprozess. |
| `pnpm local:stop` ohne eigenen Manager | Saubere Meldung, keine Prozesse beendet. |
| Wiederholter gesperrter Start | Zwei echte Vorprüfungen mit EPERM, jeweils Startsperre entfernt; kein Dienst gestartet. Kein erfolgreicher vollständiger Wiederholungsstart. [Bericht](reports/startup-preflight-check.json). |
| Nuxt-Konfigurationsauflösung ohne Listener | Tatsächlich geladen: Host 127.0.0.1, Port 3000, leere Alternativportliste, random=false; Web-Herkunftsroute wird nicht zum Backend weitergereicht. |
| nginx-Konfigurationstest | Upstreams auf 8000/3000 geprüft; nginx meldet gültige Syntax, kann seinen Sockettest wegen Operation not permitted nicht abschließen. Kein laufender nginx damit nachgewiesen. |
| Direkter Chromium-/Screenshotversuch | Chromium endet mit `sandbox_host_linux.cc:41 … shutdown: Operation not permitted`, bevor eine Seite geöffnet wird. Keine neue Screenshotdatei entstanden. |
| Erweiterte Hostdiagnose | Bereits die Eskalation für den read-only-Prozessbericht wurde von der Ausführungsrichtlinie abgelehnt. Keine Hostprozesse gestoppt. |

Echte nationale Trefferzahlen aus der erneuten SQL-Prüfung:

| Endung | Eindeutige Orte |
|---|---:|
| -ach | 3.218 |
| -ingen | 1.342 |
| -zell | 153 |
| -heim | 1.323 |
| -hausen | 2.088 |
| -dorf | 3.933 |
| -bach | 2.711 |
| -itz | 1.256 |
| -ow | 916 |
| -by | 60 |

1.006 belegte von 1.062 dargestellten Zellen; Median 45 Orte, Minimum 1, Maximum 126; 66 belegte Zellen mit weniger als zehn Orten. Die gemeinsame Geometrieantwort ist jetzt ungefähr 142 KB statt zuvor 292 KB; sie enthält Zentren statt beschnittener Polygonpfade. Die Werteantwort beträgt ungefähr 66 KB. Das sind unkomprimierte API-Modellgrößen, keine Browser-Netzwerkmessung.

## Nachtrag: ältere Projektstarts blockieren Port 8000

Der erste Stopphelfer erfasste nur den neuen Manager mit seiner Kennungsdatei. Ein Backend eines älteren Vorschauhelfers oder ein manuell gestarteter Projektserver konnte den Port deshalb weiterhin belegen. Der Stoppbefehl ist jetzt um eine Erkennung über aktuelle Socketbesitzer und die vollständige Elternkette ergänzt. Beendet werden ausschließlich bekannte Projektkommandos mit passendem Arbeitsverzeichnis, Benutzer und Prozessstart. Der verifizierte übergeordnete Vorschau-/Nuxt-Manager hat Vorrang vor seinen Kindern; nginx erhält SIGQUIT. Vor jedem Signal werden alle Prozessmerkmale neu gelesen, um PID-Wiederverwendung und geänderte Prozesse auszuschließen. Fremde Prozesse, unlesbare Besitzer und extern beaufsichtigte Dienste werden nicht direkt signalisiert. Der Host bleibt in dieser Sitzung unzugänglich; es wird kein tatsächlicher Hoststopp behauptet.

Im Hostterminal ist nun der vorgesehene Ablauf:

```sh
pnpm local:stop
pnpm preview:local
```

Ein erneuter Build ist für diese reine Start-/Stoppkorrektur nicht erforderlich, sofern der bestehende Frontendbuild aktuell ist. [Prüfbericht der Ergänzung](reports/legacy-stop-validation.json). Die früheren Prüfstände oben bleiben als ursprüngliche Referenzabnahme dokumentiert.

## Noch auszuführende Host- und Browserabnahme

In einer Sitzung mit erlaubtem Zugriff auf die tatsächlichen lokalen Prozesse und Verbindungen:

```sh
pnpm local:status
# Nur nach eindeutiger Zuordnung: alte Vorschau im zuständigen Terminal/Manager beenden.
# Falls Migration 0002 auf der bestehenden Datenbank noch fehlt, als Schemaeigentümer:
MIGRATION_DATABASE_URL=postgresql+psycopg://awendelk@127.0.0.1:55439/atlas_dev uv run alembic upgrade head
pnpm build
pnpm preview:local
# Zweites Terminal: wiederholter Start muss die laufende Instanz wiederverwenden.
pnpm preview:local
pnpm exec playwright test --config playwright.real.config.ts
```

**Vorgesehene lokale URL: http://127.0.0.1:8080. Startbefehl: `pnpm preview:local` nach `pnpm build`; Entwicklung: `pnpm dev`.** Ein veralteter unzugeordneter Einzelstart wird absichtlich nicht automatisch beendet. Die Migration wurde im temporären Testcluster ausgeführt; der aktuelle Schema-/Migrationsstand der laufenden Hostdatenbank ist noch ungeprüft.

Der echte Browserfall prüft vorab beide Upstreamkennungen über nginx, dann zehn Karten und ihre tatsächlichen Trefferzahlen, identische Kreispositionen, fünf Spalten/zwei Reihen auf Desktop, eigene und gemeinsame Wertebereiche, gleiche Farben für gleiche Vergleichsanteile, Hover/Touch-Namen, explizite Varianten, gemeinsame Region, URL-Rückkehr, Überbreite, Accessibility und fehlgeschlagene Anfragen. Erst nach erfolgreicher Ausführung entstehen:

- `artifacts/overview-desktop-real.png` und `artifacts/overview-mobile-real.png` (Standardmodus),
- `artifacts/overview-compare-desktop-real.png` und `artifacts/overview-compare-mobile-real.png`,
- `artifacts/overview-cell-desktop-real.png` und `artifacts/overview-cell-mobile-real.png`.

**Diese Screenshots existieren noch nicht. Vorhandene ältere Bilder unter `artifacts/` zeigen einen früheren Stand und werden nicht als Abnahme ausgegeben.** Auch ein wiederholbarer vollständiger Start, die aktiven nginx-Upstreams des Hosts und das Ausbleiben fehlgeschlagener API-Anfragen sind hier noch nicht real abgenommen. Die aktuelle Arbeitskopie hat keine lesbaren Git-Metadaten; es wurde kein Commit oder Deployment ausgelöst.
