# Importpipeline

Die CLI liegt in `apps/api/atlas/cli.py`. Import und API verwenden dieselben Normalisierungs- und Datenmodelle. Kein Importendpunkt im Web.

```sh
export PYTHONPATH=apps/api
uv run python -m atlas.cli download OFFIZIELLE_HTTPS_URL data/produkt.zip --sha256 BEKANNTE_PRUEFSUMME
uv run python -m atlas.cli inspect data/produkt.zip
unzip data/produkt.zip -d data/produkt
uv run python -m atlas.cli inspect data/produkt/DATEI.gpkg
uv run python -m atlas.cli prepare-bkg data/manifest.json data/bkg-2024.json
uv run python -m atlas.cli inspect data/bkg-2024.json
uv run python -m atlas.cli import data/bkg-2024.json
uv run python -m atlas.cli report DATENKENNUNG
# Erst nach Prüfung des Berichts ausdrücklich freischalten:
uv run python -m atlas.cli publish DATENKENNUNG
```

Die genauen BKG-Adressen und das Manifestformat stehen in `data-sources.md`. `inspect` zeigt bei JSON die interne `dataset.id`, Metadaten, Zeilenzahlen und SHA-256; bei CSV Spalten/Beispiel, bei GPKG Ebenen und bei ZIP den Inhalt. Die Kennung ist unabhängig vom Dateinamen. Die JSON-Prüfung liest die Datei bis zum Ende, benötigt keine Datenbank und gibt erst nach erfolgreicher Prüfung ein Ergebnis auf stdout aus. Fortschritt steht auf stderr. Vor einem neuen Produktschema Dokumentation und tatsächlich gelieferte Attribute prüfen. Der Adapter verweigert fehlende Pflichtfelder und ein abweichendes CRS; keine unkontrollierte Feldnamenheuristik.

Das vorbereitete Bundle enthält Quellenmetadaten, Verwaltungsflächen, Einwohnerzeilen und GN250-Namensobjekte. Dieses Format ist auch der explizite Vertrag für kleine Fixtures. Archive und vollständige Bundles bleiben unter ignoriertem `data/`. Der Adapter kontrolliert SHA-256 der Archive. Der Import erfasst zusätzlich die Prüfsumme des tatsächlich verarbeiteten Bundles. Änderungen derselben Datenkennung sind verboten.

Der Import liest das vorhandene JSON-Format einmal mit ijson. SHA-256 wird über dieselben gelesenen 64-KiB-Blöcke berechnet. Verwaltungsflächen, Einwohner und Orte werden in verbindungslokalen temporären PostgreSQL-Tabellen abgelegt. Batches enthalten höchstens 100 Zeilen und normalerweise höchstens 1 MiB serialisierten UTF-8-Inhalt; ein einzelnes größeres Objekt wird separat geschrieben. Metadaten dürfen vor oder nach den Arrays stehen. Auch unbekannte Zusatzfelder werden vollständig syntaktisch geprüft, ohne sie im Speicher aufzubauen. Abgeschnittenes JSON, Zusatzinhalt hinter dem JSON und doppelte Hauptfelder sind Fehler. Eine Veränderung von Dateigröße oder Zeitstempeln des geöffneten Dateiinhalts während des Lesens führt zum Abbruch. Metadaten und importierte Zeilen stammen immer aus demselben gehashten Lesestrom; die Datei wird für den Import nicht erneut geöffnet.

Erst nach erfolgreicher vollständiger Dateiprüfung werden Quellen und Importhülle mit Status `staging` protokolliert. Fehler vor diesem Schritt hinterlassen keine Importhülle und keinen Teilbestand; die Fehlermeldung steht auf stderr. Sämtliche fachlichen Zeilen entstehen anschließend in **einer** Transaktion. Batchgrenzen verursachen keine Zwischen-Commits der Fachdaten. Fehler darin rollen Verwaltungs-/Ortsidentitäten, Flächen, Einwohner, Orte und Namen gemeinsam zurück und speichern einen Fehlerbericht an der Importhülle. Jeder öffentliche Lesezugriff verlangt `published`; der aktive Zeiger bleibt erhalten.

Ein sitzungsgebundener Advisory Lock auf dem bisherigen Schlüssel `atlas-import` serialisiert den gesamten Vorgang einschließlich Dateiprüfung und Protokoll-Commits gegenüber anderen Importen und dem transaktionsgebundenen Lock von `publish`. Die Verbindung bleibt bis zur Bereinigung der temporären Tabellen und Freigabe des Locks reserviert. Ein identischer bereits validierter/veröffentlichter Import bleibt nach vollständiger Prüfsummenprüfung idempotent. Abweichende Bytes bei gleicher Kennung sind auch bei bloß veränderter Formatierung verboten. Ein fehlgeschlagener oder nach Prozessabbruch unvollständiger fachlicher Versuch verlangt weiterhin eine neue Importkennung.

Flächenteile werden einzeln auf Gültigkeit geprüft und in einer indizierten temporären Geometrietabelle abgelegt. Die Vereinigung erfolgt in PostgreSQL je `(level, code)`, auch wenn zugehörige Teile im Bundle weit auseinanderliegen. Name, ARS und IBZ müssen übereinstimmen; Quellkennung und Elternschlüssel stammen wie bisher vom ersten Teil. Keine Geometrienliste des gesamten Bestands, kein Rücktransport vereinigter Flächen als EWKT nach Python. Einwohnerkandidaten, bereits verarbeitete NNID und Dublettenverdacht liegen ebenfalls in temporären Tabellen. Serverseitige Cursor begrenzen den Rücktransport auf eine Geometrie beziehungsweise kleine Metadatenmengen. ijson-Dezimalzahlen werden bei der Objektbildung zu Python-float, Ganzzahl-Tokens bleiben int: Koordinaten sind serialisierbar, `123.0` wird weiterhin nicht als ganzzahlige Einwohnerzahl akzeptiert.

Prüfungen: Produkt-/Stichtagskonsistenz, gültige Textschlüssel, eindeutige Verwaltungseinheiten, valide Geometrien ohne stille Reparatur, gezielte AX_Ortslage-Auswahl, virtuelle Ortslagen, fehlende Namen, doppelte NNID, Dublettenverdacht, räumliche Gemeindezuordnung und Quellenkonflikte, getrennte Einwohnerverknüpfung. GN250-AGS wird bevorzugt, wenn die zugehörige Fläche den Punkt abdeckt. Bei Widerspruch bleibt die Zuordnung offen. Ohne geeigneten Quellschlüssel wird nur bei genau einer bedeckenden Fläche zugeordnet.

Der Bericht enthält Quell-/Übernahme-/Ausschlusszahlen samt Gründen, ungültige Namen/Geometrien, Dublettenverdacht, offene/mehrdeutige Zuordnung, Quellen-/Lagekonflikte, fehlende/mehrdeutige Einwohnerwerte, nicht verknüpfte Einwohnerzeilen, Differenz zum vorigen Ortsumfang und weggefallene öffentliche Identitäten. Mehrdeutige Einwohnerverknüpfungen blockieren die Freischaltung. Fehlende Einwohnerwerte bleiben NULL und werden in der Anwendung offengelegt.

Noch innerhalb der Staging-Transaktion wird `ANALYZE admin_area` vor der Ortszuordnung ausgeführt. Autovacuum kann unveröffentlichte neue Zeilen vorher nicht analysieren. Ein tatsächlich untersuchter Plan ohne diese Statistiken nutzte ausschließlich den Datenversionsindex und prüfte sämtliche Gemeindeflächen pro Punkt; der zweite Deutschlandversuch wurde deshalb kontrolliert abgebrochen. Fortschrittsmeldungen nennen Phase und verarbeitete Anzahl, ohne eine vorzeitige Veröffentlichung vorzutäuschen.

`publish` akzeptiert nur `validated` oder bereits `published`, aktualisiert Status und Zeiger atomar. Alte Veröffentlichungen bleiben explizit adressierbar. Rollback ist dieselbe Freischaltung eines vorherigen Bestands. Ein Datenimport löscht niemals den funktionierenden Bestand. Eine automatische Bereinigung alter Versionen ist bewusst nicht enthalten.

## Vorhandenes Bundle auf dem Webserver importieren

Im Repository-Verzeichnis mit der bestehenden `.env` arbeiten. Es sind weder neue Rollen/Ports noch eine erneute Einrichtung/Migration der bereits auf 0003 stehenden Datenbank erforderlich:

```sh
uv sync --locked
export PYTHONPATH=apps/api
uv run --locked python -m atlas.cli inspect data/bkg-2024-r3.json
# Die hier tatsächlich geprüfte Datei enthält dataset.id = bkg-2024-r3.
uv run --locked python -m atlas.cli import data/bkg-2024-r3.json
uv run --locked python -m atlas.cli report bkg-2024-r3
# Nach erfolgreichem Import UND Prüfung des Berichts separat ausführen:
uv run --locked python -m atlas.cli publish bkg-2024-r3
```

`import` verwendet unverändert `IMPORT_DATABASE_URL`, andernfalls `DATABASE_URL`, aus der Konfiguration. `inspect` meldet die erkannte Kennung früh als noch ungeprüft auf stderr, danach das vollständig geprüfte Ergebnis auf stdout. Weitere Meldungen nennen Dateiprüfung, Verwaltungsflächen, Einwohner, Orte und Validierung. `validated` bedeutet erfolgreicher Import. Erst ein erfolgreich abgeschlossener `publish`-Befehl meldet `published`. Bei einem Kernelabbruch vor Anlage der Hülle ist ein erneuter Versuch möglich; bei vorhandenem unvollständigem Bestand gilt die bisherige Kennungsregel. Dafür niemals Tabellen leeren oder den aktiven Bestand löschen.

## Speichergrenzen und Lastmessung

Der Python-Speicher hängt von Parserpuffer, Batch und größtem einzelnen Feature ab, zusätzlich von den kleinen Manifest-/Berichtsmetadaten. Es gibt keine feste Obergrenze für ein beliebig großes einzelnes JSON-Objekt. PostgreSQL benötigt zusätzlich temporären Plattenplatz für Rohzeilen und Geometrien, neue Fachtabellen, Indizes und WAL. Dafür mehrere GiB Reserve auf einem Datenträger einplanen; keine temporären Tablespaces auf RAM-Dateisystemen für den Deutschlandimport verwenden. Der konkrete Platzbedarf wurde hier nicht gemessen.

Der Import setzt `work_mem=8MB` und deaktiviert parallele Abfrageworker nur für seine Transaktionen; vorhandene Verbindungen, Rollen und globale Einstellungen bleiben erhalten. `work_mem` ist keine Gesamt-RAM-Grenze: GEOS/PostGIS kann bei Vereinigung, Transformation und Vereinfachung einer großen Verwaltungseinheit zusätzlichen Speicher benötigen. Dazu kommen `shared_buffers`, `temp_buffers`, weitere Verbindungen, Betriebssystemcache und die anderen Dienste. Ein niedriger Python-RSS allein belegt daher keine sichere Gesamtlast auf einem Server mit 3,8 GiB.

Reproduzierbare Messung: `scripts/measure-import-memory.py` startet einen frischen Python-Unterprozess und erfasst dessen `ru_maxrss` in KiB. Bei `--mode import` misst der Elternprozess zusätzlich alle 200 ms RSS und PSS der isolierten PostgreSQL-Prozessgruppe. PSS berücksichtigt gemeinsam benutzte Seiten anteilig; die RSS-Summe zählt sie mehrfach. Kurze Spitzen zwischen Stichproben können fehlen, eingeschränkte Sichtbarkeit wird ausdrücklich ausgewiesen. Der Lasttest schreibt und veröffentlicht keine Messdaten außerhalb der lokalen Dateien.

**Vollmessungen ausschließlich auf einer separaten Testmaschine oder in einer separaten PostgreSQL-Instanz ohne laufenden Webstack ausführen.** Eine neue leere `atlas_test*`-Datenbank dort bis 0003 migrieren; keine bestehende Datenbank zurücksetzen. `TEST_DATABASE_URL` muss ausschließlich diese Instanz adressieren. Das Skript prüft Datenbanknamen, leeren Bestand und Übereinstimmung mit `--postgres-data`, migriert/löscht selbst nichts und veröffentlicht nicht:

```sh
# Nur in der isolierten Umgebung; TEST_DATABASE_URL bereits dort gesetzt.
MIGRATION_DATABASE_URL="$TEST_DATABASE_URL" uv run --locked alembic upgrade head
uv run --locked python scripts/measure-import-memory.py data/bkg-2024-r3.json \
  --mode import --postgres-data /PFAD/ZUR/ISOLIERTEN/PGDATA \
  --output artifacts/import-memory.json

# Optional synthetisches Großbundle erzeugen, je Feature schreiben:
uv run --locked python scripts/generate-import-load.py artifacts/import-load.json
uv run --locked python scripts/measure-import-memory.py artifacts/import-load.json \
  --mode import --postgres-data /PFAD/ZUR/ISOLIERTEN/PGDATA \
  --output artifacts/import-load-memory.json
```

Die Vollmessung verlangt jeweils eine neue leere Testdatenbank. Der standardmäßig ausgeführte Subprozess-Speichertest erzeugt ein Bundle mit über 64 MiB Geometrieinhalt speicherschonend und prüft begrenzten RSS sowie Wachstum gegenüber einem kleineren Bundle. Ein zusätzlicher vollständiger Importlasttest ist mit `ATLAS_IMPORT_LOAD_TEST=1`, `TEST_DATABASE_URL` und `ATLAS_TEST_POSTGRES_DATA` für die isolierte Instanz verfügbar. Die übrigen gezielten Integrationstests prüfen Feldreihenfolge, getrennte Flächenteile/Konsistenz, Zahlentypen, späten Rollback ohne sichtbare Batches, Prüfsummen, Idempotenz und aktiven Veröffentlichungszeiger. Die bestehende Test-Fixture setzt ausschließlich ihre `atlas_test*`-Datenbank zurück: deshalb niemals gegen eine vorhandene oder gemeinsam verwendete Datenbank ausführen.

Wenn lokale Sockets gesperrt sind, prüft `uv run --locked python scripts/check-import-sql-offline.py` die produktiven Staging-/Flächen-/Einwohner-Abfragen mit den kleinen Fixtures in einem neu initialisierten `postgres --single`-Prozess. Es verbindet sich mit keiner bestehenden Datenbank und benötigt keinen laufenden Datenbankdienst. Dies prüft weder den SQLAlchemy-Treiber samt serverseitigen Cursorn noch den vollständigen Ortsimport, Veröffentlichung, konkurrierende Locks oder den Speicherbedarf des Vollimports. Der pytest-Test dafür läuft bei vorhandener lokaler PostgreSQL-18-/PostGIS-Installation ohne Root-Rechte automatisch.

Tatsächlich ausgeführte Messungen und offene Prüfungen dieser Reparatur: [Speicherbericht](import-memory.md).

## Weiterhin hoher Speicherbedarf bei prepare-bkg

Diese Reparatur betrifft ausschließlich den Import und die Prüfung bereits vorhandener JSON-Bundles. `prepare-bkg` in `bkg.py` sammelt weiterhin alle Orte, Flächen und Einwohner in Listen und erzeugt anschließend den vollständigen JSON-String. Der Vorbereitungsschritt kann deshalb weiterhin mehrere GiB RAM benötigen und gehört auf eine ausreichend große separate Maschine. Ein vorhandenes geprüftes Bundle muss für den Streaming-Import nicht neu erzeugt werden.
