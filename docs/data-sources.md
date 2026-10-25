# Datenquellen und Quellenprüfung

Verbindliche Kombination: **VG25** (Grenzen), **VG250-EW** (Einwohner), **GN250** (Ortsnamen). Kein Produkt „VG25-EW“. Abgerufen bzw. geprüft am 2026-10-21. Die API nennt die tatsächlich freigeschalteten Stände; Prüfungen/Importresultate stehen in `test-results.md`.

## Offizielle Bezugsadressen

Gewählter gemeinsamer Verwaltungsgebietsstand: **31.12.2024**, Einwohnerstichtag **31.12.2024**, GN250-Produktstand **2024-12**. Die nachstehenden versionierten Adressen vermeiden einen unkontrollierten `aktuell`-Wechsel:

| Produkt | Datei | Original-CRS | Lizenz laut Archiv |
|---|---|---|---|
| VG25 | [GeoPackage-ZIP 2024-12](https://daten.gdz.bkg.bund.de/produkte/vg/vg25_ebenen/2024-12/vg25.utm32s.gpkg.zip) | EPSG:25832 | CC BY 4.0 |
| VG250-EW | [GeoPackage-ZIP 2024](https://daten.gdz.bkg.bund.de/produkte/vg/vg250-ew_ebenen_1231/2024/vg250-ew_12-31.utm32s.gpkg.ebenen.zip) | EPSG:25832 | dl-de/by-2-0 |
| GN250 | [CSV-ZIP 2024](https://daten.gdz.bkg.bund.de/produkte/sonstige/gn250/2024/gn250.utm32s.csv.zip) | EPSG:25832 | dl-de/by-2-0 |

Offizielle Dokumentationen: [VG25](https://sgx.geodatenzentrum.de/public/gdz/dokumentation/deu/vg25.pdf), [VG250/VG250-EW](https://sgx.geodatenzentrum.de/public/gdz/dokumentation/deu/vg250.pdf), [GN250](https://sgx.geodatenzentrum.de/public/gdz/dokumentation/deu/gn250.pdf). Diese Webdokumentationen können bereits neuere Produkte beschreiben. Deshalb werden zusätzlich die mitgelieferten `aktualitaet.txt`, Produktbeschreibungen und Lizenzhinweise der fixierten Archive geprüft. Jährliche Fortführung der Verwaltungsprodukte; GN250 nach verfügbarem Produktstand. Keine automatische Aktualisierung ohne erneute Schemavalidierung, neuen Qualitätsbericht und Freischaltung.

## Geprüftes Schema und Auswahl

GN250-CSV: UTF-8 mit BOM, Semikolon; geprüft wurden NNID, NAME, NAME2, OBA, OBA_WERT, AGS, ARS, GEMTEIL, VIRTUELL, RECHTS, HOCH sowie die weiteren gelieferten Felder. NNID ist die nationale Namenskennung. Nur **AX_Ortslage** ohne `VIRTUELL=Ja` wird übernommen; `GEMTEIL=Ja` bedeutet Gemeindeteil, sonst Ortslage. Keine erfundene Stadt-/Dorfklassifikation. Gewässer, Relief, Vegetation, Verwaltungsnamen und andere Objektklassen bleiben ausgeschlossen. NAME2 ergänzt den Namen derselben Identität. Einwohnerfelder aus GN250 werden nicht als Siedlungsbevölkerung verwendet.

Der GN250-Produktstand wird aus der mitgelieferten Aktualitätsdatei als 31.12.2024 übernommen. Einzelne `DATUM`-Attribute des tatsächlich gelieferten Archivs nennen jedoch Bearbeitungen aus 2026. Die fixierte Prüfsumme macht diesen konkreten Lieferzustand reproduzierbar; der Atlas behauptet deshalb **keinen ausschließlich historischen Siedlungsbestand von 2024**. Das ist von den miteinander passenden VG25-/VG250-EW-Gebietsständen zu unterscheiden. Mögliche GN250-Schlüssel-/Lagekonflikte werden geprüft und nicht stillschweigend zugunsten einer Gemeinde aufgelöst.

VG25: Verwaltungsflächen der Ebenen Land, Kreis, Gemeinde; Attribute AGS, ARS, GEN, IBZ und GF. AGS und ARS bleiben Zeichenketten. Geometrien sind MultiPolygone. Teilflächen mit derselben Ebene und demselben Schlüssel werden zu einer Verwaltungsfläche verbunden; sie zählen als eine Einheit. Hierarchie aus den dokumentierten amtlichen Schlüsseln. Staat, Regierungsbezirk und Verwaltungsgemeinschaft sind im Ausgangsprodukt enthalten, werden im MVP nicht als zusätzliche Analyseebenen importiert.

VG250-EW: ausschließlich Gemeindeattribute AGS, GF und EWZ für die Bevölkerungsverknüpfung. Bevölkerung der GF=4-Zeile einmalig übernehmen, keine Summierung über Teilflächen oder Ebenen. Fehlende und negative Fehlwertkennzeichen werden NULL. Mehrdeutige GF=4-Verknüpfungen blockieren die Freischaltung. Abweichende Verwaltungsstände führen zum Abbruch.

Tatsächlich geprüft: `vg25_lan`, `vg25_krs`, `vg25_gem` sowie `vg250_gem`, jeweils EPSG:25832. VG25 enthält 25 zusätzliche gemeindeähnlich strukturierte BSG=2-Flächen des gemeinschaftlichen deutsch-luxemburgischen Hoheitsgebiets. Laut Abschnitt 2.3.5 der mitgelieferten Dokumentation sind diese **keiner Gemeinde und keinem Kreis zugeordnet**. Alle BSG=2-Zeilen werden deshalb mit Grund und Schlüssel im Importbericht ausgeschlossen, ebenso BSG=9-Bodenseeflächen ohne Verwaltungsstruktur. Es werden keine EW-Fehlwerte dafür erfunden. Reguläre gemeindefreie Gebiete bleiben über BSG=1 und ihren tatsächlichen IBZ erhalten. Zusätzliche BSG=1/GF=8-Landesflächen werden mit dem zugehörigen Land vereinigt.

Lagekonversion erfolgt mit GDAL von ETRS89/UTM32 nach EPSG:4326; PostGIS transformiert für die Karte nach 3857. Die Quellen behalten ihr Original-CRS im Metadatensatz. GN250-Punkte sind maßstabsbezogene Repräsentationen, keine katastergenauen Ortsmittelpunkte. Grenzkonflikte werden ausdrücklich protokolliert.

GeoJSONSeq wird mit `COORDINATE_PRECISION=15` ausgegeben, weil die Standardrundung auf sieben Nachkommastellen dichte Verwaltungsringe beschädigen kann. Der erste tatsächliche Deutschlandversuch wurde deswegen ohne Freischaltung abgebrochen. Es erfolgt keine versteckte Geometriereparatur. Bei großen Datenbeständen benötigt die vollständige Validierung und punktweise Zuordnung mehrere Minuten; das CLI läuft unabhängig von öffentlichen HTTP-Anfragen.

## Download und Manifest

```sh
mkdir -p data
curl --fail --location --retry 8 --retry-all-errors --continue-at - https://daten.gdz.bkg.bund.de/produkte/vg/vg25_ebenen/2024-12/vg25.utm32s.gpkg.zip -o data/vg25.zip
curl --fail --location --retry 8 --retry-all-errors --continue-at - https://daten.gdz.bkg.bund.de/produkte/vg/vg250-ew_ebenen_1231/2024/vg250-ew_12-31.utm32s.gpkg.ebenen.zip -o data/ew.zip
curl --fail --location --retry 8 --retry-all-errors --continue-at - https://daten.gdz.bkg.bund.de/produkte/sonstige/gn250/2024/gn250.utm32s.csv.zip -o data/gn.zip
unzip -t data/vg25.zip
unzip -t data/ew.zip
unzip -t data/gn.zip
unzip data/vg25.zip -d data/vg25
unzip data/ew.zip -d data/ew
unzip data/gn.zip -d data/gn
python3 scripts/create-bkg-manifest.py data
PYTHONPATH=apps/api uv run python -m atlas.cli prepare-bkg data/manifest.json data/bkg-2024.json
```

Der Manifesthelfer berechnet SHA-256 selbst aus vollständigen Archiven und verweigert nicht geprüfte Stichtagsdateien. Beispielstruktur (konkrete Prüfsummen werden aus den tatsächlich bezogenen Dateien erzeugt):

```json
{
  "id":"bkg-2024",
  "label":"BKG · Deutschland · 2024",
  "scope":"Deutschland",
  "population_geometry_date":"2024-12-31",
  "sources":[
    {"id":"gn250-2024","product":"GN250","version":"2024-12","data_date":"2024-12-31","retrieved_at":"ABRUFDATUM","url":"ORIGINALADRESSE","sha256":"BERECHNETER_SHA256","license":"dl-de/by-2-0","attribution":"QUELLENVERMERK_LAUT_ARCHIV","original_crs":"EPSG:25832","archive":"gn.zip","path":"gn/gn250/GN250.csv"}
  ]
}
```

`sources` muss zusätzlich VG25 und VG250-EW mit vollständigen Metadaten und den geprüften entpackten GPKG-Pfaden enthalten. `municipalities` kann explizite achtstellige AGS für einen Prüfausschnitt enthalten; dafür eine eigene Kennung, Bezeichnung und sichtbare `scope` setzen. Ohne diese Option wird Deutschland vorbereitet. Ein Ausschnitt darf nicht als vollständiger Deutschlandbestand freigeschaltet werden.

## Lizenz und Grenzen

Die Produktarchive enthalten die maßgeblichen Nutzungsbedingungen und Quellenvermerke. GN250 2024-12 und VG250-EW verlangen Datenlizenz Deutschland Namensnennung 2.0; VG25 2024 verlangt **CC BY 4.0**. Jeweils werden BKG und die zutreffende Lizenz verlinkt, Quellenvermerk, Datenquellen-PDF und Änderungshinweis angezeigt. Quellenhinweise und Bezugsjahr werden je Quelle gespeichert; die Anwendung nennt Bearbeitung durch Auswahl, Projektion und räumliche Zuordnung. Die tatsächlich gelesenen Lizenzdokumente stammen vom 26.08.2026 (GN250), 06.08.2025 (VG25) und 19.08.2025 (VG250-EW).

Kleine reale Fixtures behalten ihre Quellenmetadaten, SHA-256 der Ursprungsarchive und einen dokumentierten Auswahl-/Änderungsweg. Synthetische Sonderfälle sind separat gekennzeichnet und CC0. Vollständige Archive und Dumps gehören nicht ins Repository.

Die sozialen Inspirationen und toponymischen Referenzkarten aus dem Auftrag wurden nicht erneut auf sämtliche Kommentare untersucht. Es wird keine Vollständigkeit ihrer Diskussionen oder fachliche Prüfung dortiger Etymologien behauptet. Produktanforderungen folgen dem Auftrag; die technische Datenintegration folgt den offiziellen BKG-Quellen.
