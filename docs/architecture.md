# Architektur

Modularer Monolith: Nuxt 4 stellt die Entdeckeroberfläche und servergerenderte Methodenseite bereit. FastAPI liefert einen versionierten Vertrag. PostgreSQL/PostGIS speichert sämtliche Fach- und Geodaten. nginx ist der einzige öffentliche Einstieg. Keine Konten, Tracker, Redis-, Such- oder Tile-Dienste.

`atlas.schemas` definiert öffentliche Modelle und Filter, `search` übersetzt alle Filter in gebundene SQL-Parameter, `service` liest Daten und erzeugt MVT. `models` enthält ausschließlich SQLModel-Tabellen. `importer`, `bkg` und `cli` führen kontrollierte Offlineimporte durch. Räumliche SQL-Funktionen und GeoAlchemy2-Spaltentypen ergänzen SQLModel. Alembic migriert ein eingefrorenes SQL-Schema.

Alle Datenbankendpunkte sind synchrone FastAPI-Funktionen im Threadpool mit synchronem Psycopg/SQLAlchemy. Kein blockierender Datenbankzugriff in asynchronen Endpunkten. Eine lesende REPEATABLE-READ-Transaktion hält den gewählten Veröffentlichungsstand innerhalb einer Anfrage konsistent. Die UI bindet nach der Bestandsauswahl sämtliche weiteren Anfragen an eine konkrete unveränderliche Veröffentlichung.

Karte, Liste, Statistik und Export verwenden `compile_filter`. Namen werden über EXISTS abgefragt, damit Varianten keine Ortsdubletten erzeugen. Statistiken lesen den vollständigen Filterbestand. Karten werden nicht zum Berechnen von Statistiken ausgewertet.

MVT: 4326 für Speicherung/GeoJSON, 3857 für Kacheln, Ausdehnung 4096, Puffer 64. Unter Zoom 9 Rasteraggregation mit Gruppenzugehörigkeitsmaske, danach Einzelpunkte. Ursprüngliche Quellkennungen ergeben stabile UUIDs und 48-Bit-Featurekennungen. Aggregate erhalten deterministische Rasterkennungen. Mehr als 2 MB Kachelgröße ergibt HTTP 413, keine stillschweigende LIMIT-Kürzung. Maximalzoom 14.

Für explizit gewählte unveränderliche Datenversionen können erfolgreiche Tiles öffentlich gecacht werden. Der URL-Schlüssel enthält den vollständigen Filter, der ETag zusätzlich Kachelinhalt, Filter und Datenkennung. Fehler und Exporte sind `no-store`; nginx aktiviert keinen separaten Proxycache. Änderungen bestehender Veröffentlichungen sind nicht vorgesehen.

Die Hauptansicht beginnt mit zehn frei ergänzbaren SVG-Karten, die je einen Kreis pro räumlicher Zelle an gemeinsam gelieferten Mittelpunkten zeichnen. Alle verwenden dieselbe EPSG:3035-viewBox, dasselbe 20-km-Raster sowie lineare eigene Anteilsfarbskalen im Standardmodus „Muster hervorheben“ oder eine gemeinsame lineare Skala im Modus „Anteile vergleichen“. MapLibre wird ausschließlich bei geöffneter Detailansicht montiert (höchstens ein WebGL-Kontext). SSR zeigt bereits zehn Karten mit Platzhaltern; `/methodik` ist ebenfalls servergerendert. Kein externer Hintergrunddienst wird benötigt. Die Kreisfarben der Detailkarte werden ausdrücklich als Punktdarstellung erklärt.

OpenAPI wird aus der ausführbaren API exportiert. Ein kleiner Generator erzeugt die verwendeten TypeScript-Modelle und typisierten GET-Funktionen; keine manuell gepflegten API-Duplikate. Für serialisierte Modelle werden auch Defaultfelder verlangt. Zod validiert den separaten URL-Vertrag zur Laufzeit. CI regeneriert Vertrag und Client und vergleicht die Dateien.

Bewusste Grenzen: keine historischen Etymologien, keine vollständige Ortsteilabdeckung, keine Hintergrundjobs über HTTP. Große Importe benötigen lokale CLI-Ausführung und freien Plattenplatz. Die tatsächliche Deutschlandleistung wird separat gemessen.

## Gemeinsame Rasterauswertung

`atlas.grid` trennt `GET /api/v1/grid/geometry` (VG25-Region, feste Kreiszentren cx/cy, EPSG:3035, Ansicht und WGS84-Detailgrenzen) von `GET /api/v1/grid/base` (gemeinsame Grundgesamtheit) und `GET /api/v1/grid/counts` (sparse Treffer je Endung). `GET /api/v1/grid/values` bleibt als zusammengesetzte Kompatibilitätsantwort erhalten. `GET /api/v1/grid/cells/{cell}/places` lädt begrenzte, paginierte Zellnamen bei Bedarf. Die Übersicht lädt keine vollständigen Ortsobjekte und lädt die Geometrie beim Ändern der Endung/Ortsart nicht erneut.

Migration 0002 speichert generierte grid_x/grid_y-Spalten: floor(ST_X/Y(ST_Transform(geom,3035))/20000). Der zusammengesetzte Index (dataset_id, grid_x, grid_y, kind) unterstützt Zelllisten. Vorhandene Namen-/Geometrieindizes bleiben erhalten. UNIQUE(dataset_id,place_id) und EXISTS-Suchbedingungen verhindern doppelte Zählung von Namensvarianten. Die Geometrie benutzt ST_SquareGrid mit demselben Ursprung (0,0); 150-m-Vereinfachung betrifft nur die Ausgabe, nie die Regionszuordnung.

Pro API-Worker existiert ein nach serialisierter Größe auf 24 MiB begrenzter LRU-Cache für veröffentlichte Rasterantworten. Schlüssel enthalten Datenkennung, Bundle-Fingerprint, Rasterdefinition und sämtliche wirksamen Filter/Muster (bei Geometrie nur Geometriefilter). Erfolgreiche Antworten mit expliziter Datenkennung dürfen privat einen Tag unveränderlich gecacht werden; Fehler bleiben no-store. Der Browser hält höchstens 16 Geometrien. Mehrere API-Worker teilen keinen Anwendungscache; kein zusätzlicher Dienst nötig.

Die UI bricht überholte Anfragen ab und kontrolliert zusätzlich die Antwortreihenfolge, auch bei Regions-/Versionswechseln und Detailabfragen. Fehler werden nicht als null Treffer angezeigt. Der URL-Vertrag version:2 umfasst eine frei veränderliche geordnete Auswahl von Endungen, je höchstens sieben explizite Varianten, Farbmodus und sämtliche ergebniswirksamen gemeinsamen Einstellungen. Ältere v2-Links mit mode:share werden als gemeinsame Vergleichsskala gelesen. Farbmoduswechsel benötigen keine erneute API-Abfrage. Alle belegten Zellverhältnisse gehen ohne Fallzahlschwelle und ohne Clipping in das jeweilige Maximum ein; Nenner 0 bleibt als fehlender Anteil erkennbar.

Die aktuelle Datenversorgung, messbare Ursachen, vollständigen Cache-Schlüssel und Grenzen der Abnahme beschreibt [Frei ergänzbare Endungen und Ladezeiten](dynamic-endings-performance.md). Die Übersicht bündelt maximal zehn Muster pro Request und begrenzt sämtliche parallelen Trefferrequests gemeinsam auf zwei. Treffer warten auf die Grundauswahl, jedoch nicht auf die Geometrie. D3 interpoliert Farben und formatiert Zahlen; Vue rendert alle SVG-Elemente.
