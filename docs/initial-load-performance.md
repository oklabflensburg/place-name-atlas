# Erstes Laden der Karten

Die initiale Rasterberechnung projizierte und vereinfachte die Verwaltungsgrenzen bei jedem leeren Worker-Cache erneut. Der bisherige Ausführungsplan in `docs/reports/overview-performance.json` weist rund 886 ms im Schritt aus, der diese Geometrien erzeugt. Zusätzlich warteten die Karten auf die vollständige Regionsliste einschließlich Gemeinden, obwohl die Auswahl nur Bundesländer und Kreise anbietet.

Migration **0003** ergänzt `admin_area.display_geom` als gespeicherte generierte Spalte: `ST_SimplifyPreserveTopology(ST_Transform(geom,3035),150)`. PostgreSQL berechnet sie beim Einfügen oder Ändern einer Verwaltungsgeometrie. Die Rasterabfrage liest diese Spalte; räumliche Ortsfilter verwenden weiterhin die Originalgeometrie `geom`. Zellzuordnung, Vereinfachungstoleranz und Cacheverträge bleiben gleich. Bestehende Daten werden bei der Migration einmalig ergänzt, ohne erneuten Import. Die Migration benötigt eine Tabellensperre; sie sollte bei gestoppter Anwendung vor dem Neustart ausgeführt werden.

Eine normale SQL-View speichert keine Ergebnisse. Eine materialisierte View würde die Vorberechnung ebenfalls ermöglichen, bräuchte aber einen geregelten Refresh. Die generierte Spalte passt hier zur Berechnung aus genau einer Quellzeile und benötigt keinen Refresh. Zusätzliche GiST-Indizes wurden nicht angelegt: `admin_geom` und `place_geom` bestehen bereits, und der gemessene Engpass war die Berechnung der Darstellungsgeometrie. Auch das probeweise Zerlegen der Grenzen mit `ST_Subdivide` verbesserte die Messung nicht und ist nicht Teil der Änderung.

Im Frontend starten Regionsauswahl und Kartendaten parallel. `GET /api/v1/regions?scope=overview` liefert nur Bundesländer und Kreise: im vorhandenen VG25-Bestand **416 statt 11.372 Einträge**. Ohne `scope` liefert die API weiterhin alle Ebenen. Ein Fehler der Regionsliste verhindert die Kartenanzeige nicht; eine Meldung ermöglicht das gezielte erneute Laden der Auswahl, ohne die Karten neu zu laden.

## Vergleich mit echten VG25-Grenzen

Je fünf abwechselnde Messungen der alten Berechnung und der gespeicherten Spalte, gleicher isolierter PostGIS-Cluster, geleerter Anwendungscache. PostgreSQL läuft mit `postgres --single`; jede Messung enthält Prozessstart, SQL-Ausführung und Dekodierung. OS-Caches wurden nicht geleert. Dies sind **keine HTTP- oder Browserladezeiten**. Der Messcluster enthält die echten Bundeslandsgeometrien; Kreis-/Gemeindegeometrien und das vollständige Laufzeitrollenmodell werden dadurch nicht geprüft.

| Auswahl | Median vorher | Median nachher | Zellen |
|---|---:|---:|---:|
| Deutschland | 1.103,1 ms | 277,5 ms | 1.062 |
| Schleswig-Holstein | 131,9 ms | 76,2 ms | 90 |
| Schleswig-Holstein + Hamburg | 136,6 ms | 77,6 ms | 92 |
| Ausschnitt | 968,8 ms | 151,1 ms | 63 |
| Schleswig-Holstein mit Ausschnitt | 129,0 ms | 107,4 ms | 35 |

Die Deutschlandberechnung benötigt damit rund **75 % weniger Zeit**. In allen fünf Fällen sind die vollständigen Rasterantworten identisch, einschließlich Zellreihenfolge, Mittelpunkten, viewBox und geografischen Grenzen. Der Test prüft außerdem die Aktualisierung der generierten Spalte nach einer Quelländerung sowie Downgrade und erneutes Upgrade der Migration. Einzelmessungen: [initial-load-performance.json](reports/initial-load-performance.json).

Reproduzierbarer Aufruf, ausschließlich mit temporärer Datenbank:

```sh
PYTHONPATH=apps/api .venv/bin/python scripts/measure-initial-load-offline.py
```

Zusätzlich wurde die Produktions-SQL mit allen **45.858 Ortsobjekten** geprüft: 1.006 belegte und 1.062 gezeichnete Zellen, identische zehn Gesamtzahlen, Zellzähler und Nenner gegen eine unabhängige Python-Auswertung. Bericht: [grid-sql-check.json](reports/grid-sql-check.json). Alle 42 Frontend-Tests einschließlich Validierung dieses echten SQL-Exports und 34 Python-Tests sind erfolgreich. 20 reguläre PostGIS-/Rechtetests bleiben ohne erreichbare Laufzeitdatenbank übersprungen. Typprüfung, Produktionsbuild und serverseitige HTML-Ausgabe sind erfolgreich.

Neue Browserregressionen prüfen das Laden bei verzögerter und ausgefallener Regionsliste. Sie wurden aufgelistet, konnten hier aber nicht ausgeführt werden: Der Testserver erreicht die lokale Datenbank nicht (`psycopg.OperationalError`). Auch das Anwenden der Migration auf die laufende lokale Datenbank scheiterte an der nicht verfügbaren Verbindung. Die Migration wurde ausschließlich in den Wegwerfclustern angewendet und geprüft. Sichtbare Gesamtladezeit, HTTP-Übertragung und Browserrendering sind daher noch nicht gemessen.

Für die laufende Installation mit erreichbarer Datenbank zuerst alle Migrationen über die konfigurierte Eigentümerverbindung ausführen, danach die Anwendung mit dem neuen Build neu starten:

```sh
uv run alembic upgrade head
pnpm build
pnpm preview:local
```

`MIGRATION_DATABASE_URL` muss dabei auf die Eigentümerverbindung zeigen; die bestehende `.env` wird gelesen. `/health/ready` und der Einrichtungshelfer prüfen nun auch das Vorhandensein von `display_geom`.
