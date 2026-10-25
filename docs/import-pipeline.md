# Importpipeline

Die CLI liegt in `apps/api/atlas/cli.py`. Import und API verwenden dieselben Normalisierungs- und Datenmodelle. Kein Importendpunkt im Web.

```sh
export PYTHONPATH=apps/api
uv run python -m atlas.cli download OFFIZIELLE_HTTPS_URL data/produkt.zip --sha256 BEKANNTE_PRUEFSUMME
uv run python -m atlas.cli inspect data/produkt.zip
unzip data/produkt.zip -d data/produkt
uv run python -m atlas.cli inspect data/produkt/DATEI.gpkg
uv run python -m atlas.cli prepare-bkg data/manifest.json data/bkg-2024.json
uv run python -m atlas.cli import data/bkg-2024.json
uv run python -m atlas.cli report bkg-2024
uv run python -m atlas.cli publish bkg-2024
```

Die genauen BKG-Adressen und das Manifestformat stehen in `data-sources.md`. `inspect` zeigt CSV-Spalten/Beispiel, GPKG-Ebenen oder ZIP-Inhalt. Vor einem neuen Produktschema Dokumentation und tatsächlich gelieferte Attribute prüfen. Der Adapter verweigert fehlende Pflichtfelder und ein abweichendes CRS; keine unkontrollierte Feldnamenheuristik.

Das vorbereitete Bundle enthält Quellenmetadaten, Verwaltungsflächen, Einwohnerzeilen und GN250-Namensobjekte. Dieses Format ist auch der explizite Vertrag für kleine Fixtures. Archive und vollständige Bundles bleiben unter ignoriertem `data/`. Der Adapter kontrolliert SHA-256 der Archive. Der Import erfasst zusätzlich die Prüfsumme des tatsächlich verarbeiteten Bundles. Änderungen derselben Datenkennung sind verboten.

Staging erfolgt als isolierter Datenbestand mit Status `staging`. Quellen/Importhülle werden zuerst protokolliert; sämtliche fachlichen Zeilen entstehen anschließend in einer einzigen Transaktion. Jeder öffentliche Lesezugriff verlangt `published`. Ein Advisory Lock serialisiert Import-/Freischaltungsschritte. Fehler rollen alle fachlichen Änderungen zurück und speichern einen Fehlerbericht an der Importhülle. Der aktive Zeiger bleibt erhalten. Ein identischer bereits validierter/veröffentlichter Import ist idempotent. Ein fehlgeschlagener oder nach Prozessabbruch unvollständiger Versuch verlangt eine neue Importkennung; kein scheinbar erfolgreicher Wiederholungsaufruf.

Prüfungen: Produkt-/Stichtagskonsistenz, gültige Textschlüssel, eindeutige Verwaltungseinheiten, valide Geometrien ohne stille Reparatur, gezielte AX_Ortslage-Auswahl, virtuelle Ortslagen, fehlende Namen, doppelte NNID, Dublettenverdacht, räumliche Gemeindezuordnung und Quellenkonflikte, getrennte Einwohnerverknüpfung. GN250-AGS wird bevorzugt, wenn die zugehörige Fläche den Punkt abdeckt. Bei Widerspruch bleibt die Zuordnung offen. Ohne geeigneten Quellschlüssel wird nur bei genau einer bedeckenden Fläche zugeordnet.

Der Bericht enthält Quell-/Übernahme-/Ausschlusszahlen samt Gründen, ungültige Namen/Geometrien, Dublettenverdacht, offene/mehrdeutige Zuordnung, Quellen-/Lagekonflikte, fehlende/mehrdeutige Einwohnerwerte, nicht verknüpfte Einwohnerzeilen, Differenz zum vorigen Ortsumfang und weggefallene öffentliche Identitäten. Mehrdeutige Einwohnerverknüpfungen blockieren die Freischaltung. Fehlende Einwohnerwerte bleiben NULL und werden in der Anwendung offengelegt.

Noch innerhalb der Staging-Transaktion wird `ANALYZE admin_area` vor der Ortszuordnung ausgeführt. Autovacuum kann unveröffentlichte neue Zeilen vorher nicht analysieren. Ein tatsächlich untersuchter Plan ohne diese Statistiken nutzte ausschließlich den Datenversionsindex und prüfte sämtliche Gemeindeflächen pro Punkt; der zweite Deutschlandversuch wurde deshalb kontrolliert abgebrochen. Fortschrittsmeldungen nennen Phase und verarbeitete Anzahl, ohne eine vorzeitige Veröffentlichung vorzutäuschen.

`publish` akzeptiert nur `validated` oder bereits `published`, aktualisiert Status und Zeiger atomar. Alte Veröffentlichungen bleiben explizit adressierbar. Rollback ist dieselbe Freischaltung eines vorherigen Bestands. Ein Datenimport löscht niemals den funktionierenden Bestand. Eine automatische Bereinigung alter Versionen ist bewusst nicht enthalten.
