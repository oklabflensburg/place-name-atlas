# Speicherprüfung des Bundle-Imports, 25.10.2026

Implementiert sind Streaming, blockweises Hashing desselben Inhalts, begrenztes temporäres PostgreSQL-Staging und serverseitige Geometrievereinigung je Verwaltungseinheit. Ein vollständiger Import des Deutschlandbundles und dessen PostgreSQL-Last konnten in dieser Sitzung **nicht** gemessen werden. Das Ziel von weniger als 512 MiB Python-RSS für den vollständigen Import bleibt deshalb offen.

## Tatsächlich gemessen

Alle Messungen liefen in separaten frischen Python-Prozessen im lokalen Entwicklungsarbeitsbereich, ohne Last auf dem Webserver. Linux x86_64, Host-RAM 15.330 MiB, Python 3.13.15, ijson 3.4.0 mit Backend `yajl2` (ctypes/systemweites YAJL). Netzwerkzugriff der Shell war gesperrt; für die ausführbaren Tests wurden die unveränderten öffentlichen ijson-Releasequellen über den GitHub-Connector bezogen. Eine Installation des PyPI-Wheels mit dessen C-Erweiterung wurde nicht verifiziert. Der aktualisierte Lockfile enthält die offiziellen PyPI-Artefakte mit SHA-256; `uv lock --check --offline` war erfolgreich.

| Geprüfter Pfad | Dateigröße | Maximales Python-RSS | Dauer |
|---|---:|---:|---:|
| Reales Bundle, CLI `inspect` einschließlich CLI-/ORM-Imports | 588.969.901 Bytes (561,69 MiB) | 99.552 KiB = 97,22 MiB | 101,75 s |
| Reales Bundle, dedizierter Lese-/Prüfworker | 588.969.901 Bytes | 54.260 KiB = 52,99 MiB | 98,322 s |
| Generiertes kleines Bundle, Lese-/Prüfworker | 5.635.754 Bytes | 23.548 KiB = 22,996 MiB | 0,940 s |
| Generiertes größeres Bundle, Lese-/Prüfworker | 78.089.991 Bytes (74,47 MiB) | 25.048 KiB = 24,46 MiB | 12,487 s |

Das reale Bundle wurde jeweils vollständig bis JSON-EOF gelesen, einschließlich aller Zeilen. Ergebnis: interne Kennung `bkg-2024-r3`, 172.403 Ortsquellobjekte, 11.378 Verwaltungsquellzeilen und 11.110 Einwohnerzeilen. Dies sind Quellzahlen, keine Behauptung einer erfolgreichen fachlichen Übernahme. SHA-256: `1c33b9f40b917b14ab5adb71fcc15a83847039e19691ee3a9d7860de4217e412`, zusätzlich unabhängig mit `sha256sum` bestätigt.

Die synthetischen Dateien entstanden objektweise in einem eigenen Prozess. Der größere Fall enthält 1.600 Gemeinden mit jeweils zwei nicht zusammenhängend gelieferten Flächenteilen à 600 Ringpunkten, zwei übergeordnete Flächen, 20.000 Ortsobjekte und 3.200 Einwohnerzeilen. Beide Dateien verwenden dieselben Objektgrößen; die Gesamtmenge der Geometrien steigt. Der Python-RSS steigt um 1.500 KiB. Das belegt begrenzten Speicher im geprüften Leseweg, nicht die Gesamtlast mit PostgreSQL und Fachdatenimport.

Maschinenlesbare Werte: [import-memory.json](reports/import-memory.json). Messbefehle:

```sh
PYTHONPATH=apps/api /usr/bin/time -v .venv/bin/python -m atlas.cli inspect data/bkg-2024-r3.json
.venv/bin/python scripts/measure-import-memory.py data/bkg-2024-r3.json --output artifacts/import-reader-memory.json
.venv/bin/python -m pytest apps/api/tests/test_import_memory.py -q
```

## Tests und offene Integration

Der abschließende Lauf `.venv/bin/python -m pytest -q` hat **52 Tests bestanden und 37 übersprungen**. Er enthält die bisherigen ohne Datenbank ausführbaren Tests sowie neue Vergleiche des Streaming-Parsers mit beiden bestehenden JSON-Fixtures, Feldreihenfolgen, Koordinaten-/Einwohnerzahlentypen, beschädigtes/abgeschnittenes JSON, Dateiänderungen, CLI-Inspektion, Batchgrenzen nach Zeilenzahl und UTF-8-Bytes einschließlich übergroßem Einzelobjekt, den größeren Subprozess-Speichertest und einen socketfreien echten PostGIS-SQL-Test. `py_compile` für die geänderten Import-/Messmodule und die Lockfile-Prüfung waren erfolgreich. Eine bestehende FastAPI/Starlette-Testclient-DeprecationWarning bleibt unverändert.

Zusätzlich zur regulären Integration wurde eine ausführbare Alternative geprüft: `scripts/check-import-sql-offline.py` initialisiert ausschließlich einen neuen temporären Cluster und führt die **produktiven** Staging-/Flächen-/Einwohner-Helfer gegen `postgres --single` aus. Alle elf Szenarien bestanden: synthetische Fixture (vier Flächen, 1.234 Einwohner, eine fehlende Einwohnerverknüpfung), BKG-Flensburg (drei Flächen, 96.326 Einwohner, keine fehlende Verknüpfung), getrennt gelieferte Flächenteile mit zwei verbleibenden Geometrien, umgekehrte Feldreihenfolge, Widersprüche in Name/ARS/IBZ einschließlich JSON-Typabweichung sowie Einwohnerwerte als Float, negative Zahl und Text. Jede Szenario-Transaktion wird zurückgerollt. Es gibt keine Verbindung zu bestehenden Instanzen, kein Zurücksetzen bestehender Datenbanken und keine Veröffentlichung. [Einzelergebnisse](reports/import-sql-offline.json). Dieser Check ersetzt keinen echten SQLAlchemy-Treiber, keine serverseitigen Cursor und keinen vollständigen Ortsimport.

Die 37 übersprungenen Tests benötigen entweder eine erreichbare PostGIS-Testdatenbank oder das ausdrückliche Lasttest-Opt-in. Die neuen PostGIS-Tests für vollständige fachliche Ergebnisse, Flächenteil-/Attributkonsistenz, atomaren späten Rollback, `ANALYZE` vor Ortszuordnung, unveränderte Veröffentlichung, Idempotenz und abweichende Prüfsumme sind ergänzt, aber hier **nicht ausgeführt**. Ein zusätzlicher gezielter Start des bestehenden Idempotenztests gegen die neu initialisierte isolierte PostgreSQL-18-Instanz scheiterte bereits beim Verbindungsaufbau mit `Operation not permitted` auf dem privaten Unix-Socket. Es wurden keine Testassertionen und keine Datenbankbereinigung ausgeführt. Die Berechtigungsrichtlinie wies die angeforderte Freigabe für die Verbindung/Anlage der neuen Testdatenbank ab. Der ausschließlich für diesen Versuch gestartete temporäre PostgreSQL-Prozess wurde anschließend wieder aufgeräumt; bestehende Dienste und Datenbanken wurden nicht verändert.

Nachtrag aus [GitHub Actions, Job 121195043836](https://github.com/oklabflensburg/place-name-atlas/actions/runs/40202034998/job/121195043836): `uv sync --locked` und die reguläre Backend-Prüfung gegen den isolierten PostGIS-Service waren erfolgreich: **87 Tests bestanden, 2 übersprungen**. Damit sind die Treiber-/Cursor-Integration und die Import-/Rollback-Regressionen mit den Fixtures inzwischen auch über die reguläre SQLAlchemy-Verbindung geprüft. Der Job scheiterte später im mobilen Browsertest beim erneuten Öffnen eines Links mit 20 Karten. Die URL-Wiederherstellung wartet nun auf den vollständig serialisierten Ansichtsstand und öffnet diesen auf einer frischen Seite. Die oben genannten RSS-Werte bleiben lokale Lese-/Prüfmessungen; ein vollständiger Deutschlandimport einschließlich PostgreSQL-/GEOS-Last wurde weiterhin nicht durchgeführt.

Nicht durchgeführt: vollständiger Realimport, vollständiger synthetischer PostGIS-Lasttest, Messung des PostgreSQL-/GEOS-Spitzenbedarfs und temporären Platten-/WAL-Bedarfs. Die PostgreSQL-Gesamtlast auf einem 3,8-GiB-Server ist damit nicht abgesichert. Besonders Vereinigung und generierte Transformations-/Vereinfachungsgeometrien benötigen zusätzlichen Serverspeicher; `work_mem=8MB` begrenzt diesen GEOS-Speicher nicht. Der Python-Import braucht weiterhin Platz für das größte einzelne Feature und die Manifest-/Berichtsmetadaten. `prepare-bkg` hält unverändert den gesamten Ausgangsbestand und den serialisierten JSON-String im RAM.

Für die ausstehende Vollmessung steht ein Worker mit PostgreSQL-RSS/PSS-Stichproben bereit; genaue Befehle und Isolationsanforderungen stehen in der [Importpipeline](import-pipeline.md#speichergrenzen-und-lastmessung). Kein Bestand wurde durch diese Reparatur importiert oder veröffentlicht.
