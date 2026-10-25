# Frei ergänzbare Endungen und Ladezeiten

Stand: 22.10.2026. Die zehn redaktionellen Endungen bleiben die Startauswahl. Eingabe mit Enter oder Button, Vorschlagschips, Bearbeiten, Entfernen und Verschieben sind möglich. Ein führender Bindestrich ist Schreibnotation; äußere Leerzeichen werden entfernt. NFC und vollständiges Unicode-Casefold entsprechen dem Backend (Unicode 15.1, einschließlich ß/ss, Sigma und Cherokee). Normalisierte Duplikate fokussieren und markieren die vorhandene Karte. Es gibt keine feste Kartenobergrenze. Die sichtbare Grenze von 48.000 URL-Zeichen schützt teilbare Links vor der 64-KiB-Headergrenze des Einstiegsservers. Zu lange Ansichten werden vor einer Änderung mit einer Meldung abgelehnt. Alte v2-Links bleiben lesbar, auch mit dem früheren Farbmodus `share`.

Kleine SVG-Kreise, Radius, 20-km-Zellen, Ursprung, gemeinsame viewBox und responsives Kartenraster bleiben erhalten. Die nicht gerenderte SVG-Umrisslinie wird nicht mehr berechnet oder übertragen. Vue verwaltet weiterhin den gesamten SVG-DOM. D3 war zuvor nicht vorhanden; `d3-interpolate` übernimmt jetzt die bisherige lineare RGB-Farbinterpolation, `d3-format` deutsche Zahlen und Prozentwerte. Es gibt keinen zweiten Renderer und keinen Wechsel zu Canvas. Referenzen: [D3-Farbinterpolation](https://d3js.org/d3-interpolate/color), [D3-Zahlenformatierung](https://d3js.org/d3-format).

## Belegte Ursachen und Bestandsaufnahme vor der Optimierung

Die Ausgangsabfragen wurden **vor der Änderung** mit allen 45.858 GN250-Ortsobjekten aus `data/bkg-2024-r3.json` ausgeführt und mit `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` untersucht. Rohdaten, alle Einzelmessungen und Pläne: [Prüfbericht](reports/overview-performance.json). Die Original-SQL-Abfragen sind zusätzlich in [overview-baseline-sql.json](../scripts/overview-baseline-sql.json) eingefroren.

- Die ursprüngliche Werteabfrage benötigte 1.277 ms Ausführungszeit. Davon entfielen 1.149 ms auf JIT-Kompilierung (181 Funktionen). Die zehn `count(*) FILTER (WHERE EXISTS …)`-Ausdrücke mit leeren Ausschlüssen erzeugten einen teuren Plan. Das ist ein gemessener Engpass, keine Vermutung über fehlende Indizes.
- Die ursprüngliche Geometrieabfrage benötigte 1.564 ms. Sie transformierte die Regionsgeometrien, vereinigte sie und berechnete polygonale Zellverschneidungen, obwohl die Darstellung ausschließlich Zellmittelpunkte benötigt. Die Planung zeigt diese Arbeit innerhalb der Geometrieabfrage.
- Beim Ändern einer Endung setzte die UI alle Trefferwerte auf `null` und lud die gesamte Auswahl neu. Der Wertcache war an die vollständige Zehnerauswahl samt Gruppenkennungen gebunden. Dieser Ablauf ist im ursprünglichen Quellcode feststellbar.
- JSON-Serialisierung lag im ursprünglichen Service-Test unter 1 ms und erklärt diese SQL-Zeiten nicht.

Weitere geprüfte Punkte:

| Frage | Feststellung am Ausgangszustand |
|---|---|
| Zehn Karten seriell geladen? | Nein: eine gebündelte Werteabfrage; Geometrie und Werte über `Promise.all`. Metadaten wurden davor geladen. |
| Raster und Nenner zehnmal übertragen? | Nein: jeweils eine Geometrie und eine gebündelte Werteantwort. Bei Endungsänderungen wurde aber der Nenner erneut berechnet und die gesamte Werteantwort übertragen. |
| SQL je Zelle? | Nein: ein `GROUP BY` für alle Zellwerte. |
| Rasterzuordnung räumlich neu berechnet? | Nein: generierte `grid_x/grid_y` aus Migration 0002. Geometrieverschneidungen liefen gesondert; Regionsauswahl nutzt unveränderte Originalgrenzen. |
| Vollständige Ortslisten für die Übersicht? | Nein; Zellnamen wurden bereits bei Bedarf geladen, aber noch nicht im Browser gecacht. |
| Synchrones SQL in asynchronem Handler? | Nein: synchrone FastAPI-Endpunkte im Threadpool. |
| Vue-Watcher als Mehrfachauslöser? | Keine entsprechenden Watcher vorhanden; explizite Ereignishandler lösen die Requests aus. |
| Alle Karten bei einer Endungsänderung betroffen? | Ja: gemeinsames `busy`, Verwerfen der Werte und erneutes Laden aller Endungen. |
| SQL-Indizes? | `name_suffix` wird verwendet; `place_record`-Primärschlüssel unterstützt die Namenszuordnung. Vorhandene Dataset-/Kind-, räumliche und Zellindizes bleiben bestehen. Ein fehlender Index wurde für diesen Engpass nicht belegt; daher keine zusätzliche Indexmigration. |
| Wartezeit nach Antwortempfang? | Nicht gemessen: localhost und Browserstart sind in dieser Sitzung gesperrt. Es wird kein Browserengpass behauptet. |

## Änderungen am Datenfluss

`GET /grid/geometry` liefert weiterhin stabile Zell-IDs und Mittelpunkte. Die neue Abfrage prüft die positive Flächenüberschneidung je ausgewählter Regionsgeometrie, statt vollständige Zellpolygone und eine ungenutzte gemeinsame Umrisslinie zu erzeugen. Die 150-m-Vereinfachung bleibt ausschließlich eine Darstellungsentscheidung. Regionsfilter für Ortsobjekte verwenden weiterhin die unvereinfachten Grenzen. Alle 1.062 Deutschland-Zellkennungen, Mittelpunkte, WGS84-Grenzen und viewBox-Werte wurden gegen die Ausgangsantwort geprüft.

`GET /grid/base` liefert einmal die Grundgesamtheit je Zelle, den Gesamt-Nenner und `base_key`. `missing_cells: "no-places"` garantiert ausdrücklich, dass in der vollständigen Grundauswahl fehlende Zellen keine erfassten Orte enthalten. Intern wird die gefilterte Zuordnung von eindeutigen Datensatzkennungen zu Zellen wiederverwendet. Räumliche Regionsprüfungen fallen damit nur beim Erstellen einer neuen Filterauswahl an.

`GET /grid/counts` liefert pro Endung nur Zell-ID/Treffer-Paare und eindeutige Gesamtzahlen. `missing_counts: "zero"` garantiert Null für fehlende Treffer **innerhalb einer validierten Grundauswahl**. Unbekannte Zell-IDs, falsche Datenstände, doppelte Zellen und widersprüchliche Summen sind Fehler. Die Namensabfrage beginnt beim bestehenden Endungsindex, dedupliziert Ortsobjekte und bündelt fehlende Muster mit `UNION ALL`. Anschließend wird mit der gecachten Grundauswahl abgeglichen. Ausschlüsse gelten wie bisher für sämtliche Namen eines Ortsobjekts. `/grid/values` bleibt als kompatible zusammengesetzte Antwort verfügbar.

Geometrie und Grundauswahl starten parallel. Sobald die Grundauswahl vorliegt, starten Trefferabfragen **während** die Geometrie gegebenenfalls noch lädt. Anfragen enthalten höchstens zehn Endungen; ein gemeinsames Browser-Semaphor erlaubt höchstens zwei gleichzeitige Trefferrequests, auch bei vielen raschen einzelnen Ergänzungen. Der API-Worker serialisiert Treffer-Cache-Misses; identische parallele Cache-Builds teilen ein Ergebnis. Es gibt keine Begrenzung der gesamten Kartenzahl auf zehn.

Der Worker-LRU ist auf 256 Einträge und 24 MiB mit konservativem sechsfachem Größenansatz begrenzt. Schlüssel enthalten veröffentlichte Datenkennung, Fingerprint, Rasterversion, Normalisierung und Namenssemantik, Region, Ortsart, Ausschnitt, normalisierte Muster und Ausschlüsse. Titel und UI-Reihenfolge beeinflussen Treffer nicht. Fehler werden nicht gecacht. Die aktuelle Veröffentlichung wird weiterhin vor Cachezugriff aufgelöst; neue Startseiten wählen die aktuelle Version, explizit versionierte Links behalten bewusst ihren Stand.

Der Browser hält höchstens 16 Geometrien, 16 Grundauswahlen, 256 Endungsergebnisse und 128 Zellnamenseiten. Laufende identische Endungen werden zusammengeführt; überholte gemeinsame Requests werden abgebrochen und ihre Ergebnisse zusätzlich über Generation und Signal verworfen. Entfernte oder überarbeitete Karten verlieren ihre aktiven Reaktivzustände. Entfernen, Umordnen, Farbmodus und Größenänderung benötigen keine API-Anfrage. Gemeinsame Farbbereiche werden aus vorhandenen Werten neu berechnet. Stabile Karten- und Zellschlüssel, vorbereitete Zellmodelle und Vue `v-memo` verhindern unnötige SVG-Aktualisierungen.

## Vorher-/Nachher-Messungen

Gleiche isolierte PostGIS-Datenbank, gleiche Quelle (`bkg-2024-r3`, Bundle-SHA256 im Bericht), gleicher Rechner: Intel Core i5-8265U, acht logische CPUs. Deutschland, alle Ortsarten, zehn Standardendungen. Die isolierte Datenbank enthält alle Orte/Namen und die 16 Bundeslandsgeometrien; sie ersetzt keine Prüfung der laufenden Runtime-Rollen, Kreisfilter oder des Veröffentlichungszeigers.

Je fünf Messungen mit geleertem **Anwendungscache** und fünf anschließende Cache-Hits. PostgreSQL läuft ohne Netzwerksocket im Single-User-Modus und wird pro SQL-Aufruf gestartet. Servicezeiten enthalten deshalb Prozessstart, SQL-Ausführung und Dekodierung des Testtransports. Sie sind **keine HTTP-Ladezeiten**. PostgreSQL-Shared-Buffers sind nicht zwischen Prozessen warm; OS-Caches wurden nicht geleert. „Kalt“ bezeichnet hier ausschließlich den Anwendungscache.

Nach der ersten Ausgangsmessung wurden Original-SQL und neue SQL nochmals nacheinander auf demselben Cluster ohne parallelen Build gemessen. Alle Einzelwerte und die ursprüngliche Messreihe bleiben im Bericht erhalten.

| Service, Anwendungscache kalt | Vorher, fünf Werte in ms | Nachher, fünf Werte in ms | Median vorher → nachher |
|---|---|---|---|
| Vollständige zehn Kartenwerte, kompatible Antwort | 1.450,5 / 1.315,4 / 1.413,4 / 1.305,2 / 1.314,9 | 376,6 / 424,2 / 380,7 / 393,0 / 396,7 | **1.315,4 → 393,0 ms (−70,1 %)** |
| Geometrie | 1.703,2 / 1.585,6 / 1.595,1 / 1.595,0 / 1.608,7 | 1.089,9 / 1.126,5 / 1.118,4 / 1.095,9 / 1.102,4 | **1.595,1 → 1.102,4 ms (−30,9 %)** |
| Neue Grundauswahl allein | – | 162,0 / 161,1 / 162,2 / 161,1 / 167,2 | 162,0 ms |
| Zehn Treffer bei vorhandener Grundauswahl | – | 218,3 / 212,7 / 211,8 / 212,1 / 219,6 | 212,7 ms |
| Neue elfte Karte `-bek`, Grundauswahl vorhanden | zuvor nur Bearbeiten einer Zehnerauswahl möglich | 31,2 / 30,7 / 29,3 / 30,8 / 30,5 | **30,7 ms; eine SQL-Abfrage; 1.056 Byte** |

Im abschließenden Query-Plan benötigt die neue gemeinsame Grundauswahl 68,6 ms und die gebündelte Trefferabfrage 132,7 ms; die frühere Abfrage benötigt im paarweisen Lauf 1.442,8 ms. Die neue Trefferabfrage hat keine JIT-Kompilierung. Der Geometrieplan sinkt von 1.520,5 auf 1.078,2 ms. Die zusätzlichen separaten Pläne zu `/base` und `/counts` stehen ebenfalls im Bericht. EXPLAIN ist instrumentiert und ein eigener Durchlauf; seine Werte werden nicht mit den fünf Service-Samples gleichgesetzt.

Bei warmem Anwendungscache benötigen neue Grundauswahl-/Trefferendpunkte im Median 0,014 / 0,095 ms, ohne SQL. Geometrie: 0,008 ms. Die alte vollständig gecachte Werteantwort war mit 0,006 ms ebenfalls schnell. Der kompatible neue `/values`-Zusammenbau benötigt warm 3,24 ms und ist damit langsamer als die alte vollständig gecachte Antwort; die neue Übersicht verwendet ihn nicht. Diese Werte schließen HTTP, Browsercache und Rendering aus.

Unkomprimierte initiale Rasterantworten: vorher **207.631 Byte**, nachher **179.693 Byte (−13,5 %)**. Die neue gesonderte Trefferantwort ist mit 94.013 Byte größer als die alte kompakte Zehn-Spalten-Antwort (66.046 Byte); dafür werden ihre Grunddaten bei Änderungen nicht wiederholt, und die ungenutzte Umrisslinie entfällt. Keine behauptete Übertragungsdauer folgt aus dieser Größenmessung.

Backend-Verarbeitung und Serialisierung stehen pro Sample getrennt im Bericht. Die neue Serialisierung liegt je nach Endpunkt bei rund 0,5–1,2 ms. Die Browserseite misst außerdem `atlas:json`, Grunddaten-/Trefferverarbeitung, Vue-SVG-Updates und eine doppelte `requestAnimationFrame`-Grenze. Letztere bezeichnet eine Rendergelegenheit, keinen Nachweis tatsächlich gemalter Pixel. `Server-Timing` trennt Datenbankausführung, Serialisierung und übrige Requestdauer (einschließlich Scheduling und Verbindungsaufwand).

## Verifikation und offene Abnahme

Ausgeführt: 41 Frontend-Tests; 24 Python-Tests ohne Netzwerk; Typprüfung; Produktionsbuild; Produktions-SSR über Nitros `localFetch`. Ein Frontend-Test und 20 reguläre PostGIS-/Rechtetests sind mangels freigegebener Laufzeitdatenbank übersprungen. Der separate reale SQL-Lauf ist erfolgreich: Jede Zelle und jede Startendung gegen den ursprünglichen vollständigen Antwortstand und eine unabhängige Python-Auswertung geprüft; außerdem zwanzig Endungen in zwei Batches, null Treffer, Unicode, Varianten, Ausschlüsse und Schleswig-Holstein/Gemeindeteile. Zähler, Nenner und daraus berechnete Anteile bleiben gleich. Die zusätzliche Endung führt genau eine Namensabfrage ohne räumliche Operationen aus; erneutes Laden derselben Endung führt keine SQL-Abfrage aus.

Gezielte Regressionen prüfen Singleflight, Cachegrenzen und vollständige Schlüssel, globale Requestparallelität, veraltete Antworten, Fehlerwiederholung, Sparsity-Vertrag, Grunddatenfehler, dynamische URL-Auswahl und Laden von Treffern vor Abschluss der Geometrie. Der Lockfile wurde geparst und die Versions-/Integritätsverknüpfungen geprüft; eine Neuinstallation war wegen des schreibgeschützten gemeinsamen pnpm-Stores nicht möglich. Vorhandene identische D3-Paketversionen wurden zur lokalen Prüfung innerhalb des Workspace bereitgestellt.

Der tatsächliche Playwright-Aufruf über `playwright.real.config.ts` wurde versucht, scheiterte aber vor dem Browserlauf beim Start des nginx-Stacks. Die Sandbox verweigert localhost-Verbindungen und Portprüfungen mit `EPERM`; die automatische Freigabe der Eskalation wurde abgelehnt. Deshalb sind **TTFB, HTTP-Übertragungsdauer, Browserverarbeitung und sichtbare Kartenlaufzeit nicht gemessen**. Es gibt **keinen neuen Screenshot der elften Karte**. Ältere PNGs in `artifacts/` belegen diese Änderung nicht.

Die Browserprüfungen sind in [dynamic.spec.ts](../tests/real-e2e/dynamic.spec.ts) ergänzt und durch Playwright erfolgreich aufgelistet, aber nicht ausgeführt. Sie prüfen Enter/Button, leere/normalisierte doppelte Eingaben, unveränderte bestehende SVG-Knoten beim Hinzufügen, gezieltes Nachladen, Bearbeiten, Entfernen, Reihenfolge, zwanzig Karten, geteilte Links, Farbe, Größe, Region, Ortsart, Fehler und überholte Requests. Sie schreiben `artifacts/overview-eleventh-desktop.png` bzw. `overview-eleventh-mobile.png` sowie fünf getrennte Browserzeitreihen. Die Zeitreihen unterscheiden TTFB, Übertragungsdauer/-größe, JSON-Verarbeitung, Vue-Patch und Rendergrenze. Fünf Navigationen ersetzen keinen kalten Backend-Neustart und kein CPU-Profil der SVG-Rasterisierung.

Für die ausstehende Abnahme in einer Umgebung mit lokalen Sockets:

```sh
pnpm install --frozen-lockfile
pnpm build
pnpm exec playwright test --config playwright.real.config.ts
```

Der konfigurierte Einstieg bleibt **http://127.0.0.1:8080**, einschließlich Prüfung der tatsächlichen nginx-Upstreams und des veröffentlichten echten Datenbestands. Eine Aktualisierung des Datenbestands, Migration, Veröffentlichung oder ein Deployment wurde hier nicht vorgenommen.

Der SQL-Vergleich kann mit `PYTHONPATH=apps/api .venv/bin/python scripts/measure-overview-offline.py --compare` wiederholt werden. Er nutzt den isolierten Messcluster dieser Sitzung; für einen neuen Cluster zunächst `--before` ausführen. Der eingefrorene Original-SQL wird bei `--compare` erneut ausgeführt. Keine laufende Datenbank wird zurückgesetzt.
