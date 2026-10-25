> **Neuer Produktstand: Zehn-Karten-Übersicht (21.10.2026).** Die folgenden älteren Browserergebnisse betreffen die frühere Einzelkartenansicht. Maßgeblich für die neue Umsetzung ist [ten-map-overview.md](ten-map-overview.md): SQL-Prüfung mit echten Daten, Unit-Tests, TypeScript, Build und SSR erfolgreich; Browser-Abnahme, neue Screenshots und Migration der bestehenden lokalen Datenbank durch die Sitzungsrichtlinie blockiert und weiterhin offen.

# Tatsächlich ausgeführte Abnahme

Prüftag: **21.10.2026**, lokale Linux-x86_64-Umgebung. Kein öffentlicher Betrieb und keine produktiven Serveränderungen. Die Datenfreischaltung erfolgte ausschließlich lokal.

Zum Abschluss wurde die Vorschau mit dem realen Bestand auf **http://127.0.0.1:8080** gestartet. nginx bindet ausdrücklich an Loopback; Readiness, Datenbestands-API und servergerenderte Methodenseite wurden erneut mit HTTP 200 geprüft. Neustart: `pnpm preview:local`, solange der dokumentierte lokale PostgreSQL-Cluster läuft.

## Ausgangslage

Das Arbeitsverzeichnis war ohne Implementierung. Die vorhandenen Metadatenverzeichnisse waren leer bzw. schreibgeschützt; es gab kein verwendbares Git-Repository, keinen Branch und keine bestehenden Änderungen oder `AGENTS.md`-Vorgaben. Es wurden keine fremden Dateien überschrieben und keine Commits oder Pushes behauptet.

## Lokale Prüfungen

| Prüfung | Ergebnis |
|---|---|
| Python/echtes PostgreSQL/PostGIS, `pnpm test:e2e --backend` | **35 bestanden, 4,44 s**, einschließlich realem BKG-Ausschnitt, CSV-Härtung und kombinierenden Unicode-Zeichen |
| Vitest, `pnpm test` | 5 bestanden |
| Striktes TypeScript, `pnpm typecheck` | erfolgreich |
| Nuxt-Produktionsbuild, `pnpm build` | erfolgreich; MapLibre-Hauptchunk ca. 1,03 MB / 272 kB gzip, separater Worker ca. 471 kB |
| Playwright, `pnpm test:e2e --production` | **14 bestanden, 38,4 s**, Desktop Chromium und Pixel-7-Emulation, echter nginx vor gebautem Nuxt und echter PostGIS-API |
| Playwright im frischen Entwicklungsserver, `pnpm test:e2e` | **14 bestanden, 1,7 min**, eigener Port 3002 mit 64-KiB-Headergrenze |
| Browser mit vollständigem BKG-Bestand, `pnpm test:e2e --real-browser` | **4 bestanden, 55,4 s**, reale freie by/büll-Suche in Schleswig-Holstein, Teilen, Details, axe und MVT auf Zoom 0 und 9 |
| OpenAPI-/Client-Regeneration | SHA-256 vor/nach identisch |
| Kleine synthetische Fixture neu generiert | SHA-256 vor/nach identisch |
| Frische Quellkopie unter `/tmp/ortsnamenatlas-clean-check` | Installation mit `uv sync --offline --locked` und `pnpm install --offline --frozen-lockfile` aus vorhandenem Store erfolgreich. Danach vollständiger Nuxt-Build und **2 Browser-Durchstiche über nginx bestanden, 18,2 s** (Desktop/Mobil, API, Migration/Fixture, Karte, Liste, Details, Statistik, Teilen). Kein behaupteter Git-Checkout-/Containerstart |

Der Python-Lauf meldet eine Starlette-Warnung zur künftigen TestClient-Umstellung auf HTTPX2. Die verwendete fixierte Kombination funktioniert; die Warnung ist kein nicht ausgeführter Test.

Integration deckt ab: idempotente Importe, atomarer Fehlerrollback, führende Schlüsselnullen, mehrteilige Gemeinden, fehlende/mehrdeutige Einwohner, Gebietsstandabweichungen, räumliche Grenzmehrdeutigkeit, stabile Ortsidentitäten, Unicode/Casefold, literale SQL-Wildcards, ing/ingen, ach/bach und Ausschlüsse, Varianten ohne Mehrfachzählung, Namenszusätze, übereinstimmende Listen/Statistiken/Exporte, Exportlimits, lesende Runtime-Rechte und reale BKG-Fixture. Keine SQLite-Ersatztests.

Browser deckt freie Suche/Voreinstellungen, Vergleichsgruppen, Liste, Detaildialog samt Fokusführung, URL-Roundtrip, leere Resultate, API-Fehler, fehlende historische Version, abgebrochene Anfrage, einen gültigen großen Unicode-Vergleichslink über nginx/Nuxt/API und decodierte MVT-Aggregation ab. Methodenseite wird servergerendert; sowohl Methodenseite als auch die tatsächlich geladene Entdeckerkarte wurden ohne ausgeschaltete axe-Regeln geprüft. Dabei gefundene Kontrast- und Überschriftenfehler wurden behoben. Screenshots `artifacts/desktop-map.png`, `mobile-map.png`, `real-desktop-map.png` und `real-mobile-map.png` wurden tatsächlich geöffnet: Kartenhöhe, Zoomsteuerung, Hinweis/Skala und Panelgrößen kontrolliert. WebGL läuft im Test per Software-Rendering; keine Aussage über jedes physische Mobilgerät.

## Reale Daten

Die vollständigen offiziellen Archive sind lokal heruntergeladen, SHA-256 und ZIP-CRC geprüft; die tatsächlich extrahierten CSV-/GPKG-Schemata und Aktualitätsdateien wurden untersucht. Fixierung siehe `data-source-lock.json` und `data-sources.md`.

Der reale Flensburg-Prüfausschnitt wurde erstellt und erfolgreich integriert: zwölf GN250-Quellobjekte, **neun übernommene Ortslagen/Gemeindeteile**, drei ausgeschlossene andere Objektklassen, eine Gemeinde mit **96.326 Einwohnern**, Stand 31.12.2024. Namen/Erwartungen sind aus den fixierten Quellzeilen abgeleitet. Grenzen sind ausschließlich für dieses Fixture ausdrücklich vereinfacht; Auswahl und Lizenzen stehen in `tests/fixtures/README.md`.

Der erste vollständige Deutschlandversuch wurde durch die strikte Geometrieprüfung abgebrochen und nicht veröffentlicht. Ursache war die standardmäßige Rundung bei GeoJSONSeq-Konversion auf sieben Nachkommastellen. Der Adapter verwendet jetzt 15 und nennt bei ungültigen Geometrien Ebene, Schlüssel und PostGIS-Grund. Ein zweiter Staging-Lauf wurde wegen eines anhand EXPLAIN nachgewiesenen ungünstigen Zuordnungsplans kontrolliert abgebrochen. ANALYZE innerhalb der Importtransaktion ist jetzt vor die Zuordnung gezogen. Der vollständige Import **bkg-2024-r3 wurde erfolgreich freigeschaltet**, wiederholter Import blieb ohne Dubletten. Laufzeit einschließlich erneuter Idempotenzprüfung: **769,557 Sekunden**. [Qualitätsbericht](reports/bkg-import-report.json), [Abgleich des veröffentlichten Bestands](reports/dataset-check.json).

Aus 172.403 GN250-Quellobjekten wurden **45.858** reale Ortslagen übernommen (9.790 Ortslagen, 36.068 Gemeindeteile). Ausgeschlossen: 125.579 andere Objektklassen und 966 virtuelle Ortslagen. Keine ungültigen Namen/Geometrien und kein Dublettenverdacht im erfolgreichen Lauf. **17 Quellen-/Lagekonflikte** bleiben ohne Gemeindezuordnung; 45.841 Quellzuordnungen sind räumlich bestätigt. Keine willkürliche Grenzzuordnung.

VG25: **16 Länder, 400 Kreise und 10.956 Gemeinden**, aus 11.410 Quellflächenzeilen; 32 dokumentierte Sonderflächen ausgeschlossen, reguläre Landes-Teilflächen vereinigt. VG250-EW: **10.956 eindeutige, vorhandene Werte**, Summe **83.577.140**, gegen die einzigen GF=4-Quellzeilen direkt geprüft. Keine fehlenden/mehrdeutigen Einwohnerverknüpfungen und keine unmatched Einwohner-Gemeindeschlüssel. Geometrie- und Einwohnerstichtag jeweils **31.12.2024**. GN250-Produktstand und spätere Bearbeitungen sind getrennt dokumentiert.

Echter API-Durchstich: Enthält `otter` ergibt **55 eindeutige Orte**, in Liste, vollständiger Statistik und GeoJSON übereinstimmend. Diese Zahl wurde aus dem importierten fixierten Archiv ermittelt, nicht als erwarteter Deutschlandwert erfunden.

## Restore und Leistung

Ein tatsächlicher Custom-Dump mit anschließendem Restore in eine neue isolierte Datenbank war für die synthetische Fixture erfolgreich: 19 Orte, vier Verwaltungseinheiten, Einwohner-Summe 1.234, aktiver Zeiger erhalten, keine ungültigen Ortsgeometrien. Originaldatenbank unverändert; nur die temporäre Restore-Datenbank wurde danach entfernt. Auch der vollständige BKG-Bestand wurde tatsächlich wiederhergestellt: **45.858 Orte, 11.372 Verwaltungseinheiten, Einwohner-Summe 83.577.140, aktiver Zeiger bkg-2024-r3**, keine ungültigen Ortsgeometrien. Custom-Dump **214.095.053 Bytes**. Abgleich von Quelle und isolierter Zieldatenbank erfolgreich, Zieldatenbank anschließend entfernt. [Restore-Ergebnis](reports/restore-check.json).

Leistungsmessung auf dem vollständigen veröffentlichten Bestand: Intel Core i5-8265U, 8 logische CPUs, ca. 15 GiB Host-RAM, Linux x86_64, PostgreSQL 18.6/PostGIS 3.6.4, shared_buffers 128 MB, Datenbank ca. 342 MB. Je Suche 11 sequenzielle Durchläufe: Trefferzahl + erste 30 Listenzeilen + vollständige Regionalstatistik + Welt-Aggregatkachel. Kein Anwendungscache, bereits benutzte PostgreSQL-/OS-Caches; erste Messung separat, **kein behaupteter Kaltstart**. Warm-p95 ist der größte von zehn Warmdurchläufen (Nearest Rank). Keine parallelen Nutzer, kein HTTP-/TLS-Lasttest. SQL-Zeitlimit 10 s. [Messwerte und EXPLAIN ANALYZE/BUFFERS](reports/benchmark.json), [kurze Enthält-Suche](reports/benchmark-short.json).

| Filter | Eindeutige Orte | Erster Durchlauf ms | Warm-Median ms | Warm-p95 ms |
|---|---:|---:|---:|---:|
| Endet mit `bach` | 2711 | 1057.6 | 1049.4 | 1070.6 |
| Endet mit `a` | 987 | 992.4 | 999.4 | 1037.0 |
| Enthält `otter` | 55 | 751.7 | 767.0 | 1285.3 |
| Exakt `Flensburg` | 1 | 266.7 | 273.3 | 306.4 |
| Beginnt mit `Neu` | 780 | 1013.5 | 995.0 | 1036.8 |
| Enthält `a` | 21455 | 1336.8 | 1322.5 | 1402.8 |

Die gemessenen Namenspläne nutzen name_suffix für beide Suffixe, name_trigram für otter, name_prefix für exakte Gleichheit und im C-Locale name_exact für Neu. Gleichheits-/Präfixindizes sind je nach Kollation teilweise alternativ nutzbar; text_pattern_ops bleibt für andere Clusterkollationen sinnvoll. Die räumliche Gemeindeprüfung nutzt admin_geom (GiST). Sehr kurze Enthält-Muster liefern keine selektiven Trigramme; der tatsächliche Plan der a-Suche nutzt Seq Scans auf Orts- und Namenzeilen statt eines unselektiven GIN-Zugriffs. Sie bleibt vollständig, ohne unbemerkte Trefferbegrenzung. Regionale Zwei-Gruppen-Abfragen waren im Browser mitunter deutlich langsamer (Schleswig-Holstein-Statistik ca. 4–6,4 s); hierfür besteht vor hoher öffentlicher Last weiterer Optimierungs-/Kapazitätsprüfbedarf. Die Messung belegt keine Produktionskapazität.

## Nicht ausgeführt und Grenzen

Docker Engine war in dieser Umgebung nicht zugänglich und das Compose-Plugin fehlte. Die Compose-/Dockerfiles wurden erstellt und ihre Basisimages mit Registry-Digests fixiert, aber **hier nicht gebaut oder gestartet**. Lokales nginx 1.28.3 wurde tatsächlich verwendet; das Containerimage ist nginx 1.30.6. GitHub Actions wurde erstellt, aber nicht auf GitHub ausgeführt. Kein behauptetes erfolgreiches Deployment, kein DNS/HTTPS-Test. Keine Last-/Kapazitätszusage aus Fixtures.

GN250 bleibt eine maßstabsbezogene Auswahl, keine vollständige Liste aller Ortsteile/Weiler/Wohnplätze. Ortsart wird nur soweit geliefert unterschieden. Einwohner gehören Gemeinden, niemals automatisch den GN250-Ortslagen. Etymologien werden nicht behauptet. Export maximal 10.000 eindeutige Orte, Überschreitung als Fehler statt unvollständiger Datei. Vor öffentlichem Betrieb stehen Containerprüfung in einer Docker-Umgebung, HTTPS/Zertifikatsverwaltung, Sicherungsziel und ein Lasttest auf dem Zielhost aus.
