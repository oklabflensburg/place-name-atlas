# Datenmodell

| Tabelle | Verantwortung |
|---|---|
| source_version | Produkt, Version, Stichtag, Abrufdatum, Originaladresse, SHA-256, Lizenz, Attribution, Quell-CRS, Status, Importerversion |
| dataset | Unveränderliche Kombination der drei Quellen, getrennte Geometrie-/Einwohnerstichtage, Geltungsgebiet, synthetischer Status, Importbericht, Bundle-Prüfsumme |
| publication | Einzelner atomar umstellbarer Zeiger auf den aktiven veröffentlichten Bestand |
| place_identity | Stabile interne UUID aus GN250-NNID, ursprüngliche Kennung und numerische Feature-ID |
| place_record | Versionsbezogene Ortslage, Originalname, Ortsart, Punkt, Gemeindezuordnung, Qualität und Kandidaten; generierte EPSG:3035-Zellindizes grid_x/grid_y (20 km, Ursprung 0) |
| place_name | Unveränderter Original-/Alternativname, NFC-Casefold-Suchform, umgekehrte Suchform |
| admin_identity | Ebene und amtlicher Textschlüssel |
| admin_area | Geometrie/Name/Hierarchie je Bestand, AGS/ARS, IBZ, Quellkennung; eine originale MultiPolygon-Geometrie je Identität und automatisch gespeicherte Darstellungsgeometrie display_geom (EPSG:3035, 150 m vereinfacht) |
| population | Ein Einwohnerwert pro Gemeinde und Kombination, Stichtag, VG250-EW-Quellenbezug und Verknüpfungsqualität |

AGS und ARS sind Text. Gemeinden werden über die Gemeindeebene und ihren vollständigen achtstelligen AGS verknüpft. Landes-/Kreisschlüssel werden nicht mit Gemeindezeilen zusammengezählt. Nachgewiesene getrennte Geometriezeilen derselben Identität werden geometrisch vereinigt; Einwohner werden dabei nicht addiert. Widersprüchliche Attribute führen zum Importabbruch.

VG250-EW-Einwohner werden nur aus der dokumentierten GF=4-Zeile der Gemeinde übernommen. Keine Zeile und NULL bedeuten fehlend. Mehrere GF=4-Zeilen bedeuten mehrdeutig und verhindern eine Freischaltung. GF=2-Teilflächen vervielfachen keine Bevölkerung. Gemeindefreie Gebiete bleiben als Verwaltungseinheiten mit IBZ erhalten; unbekannte Einwohnerwerte werden nicht als 0 interpretiert. Ein ausdrücklich gelieferter Wert 0 bleibt 0.

BSG=2-Sonderflächen des deutsch-luxemburgischen Hoheitsgebiets sind laut Quelle keine zugeordneten Gemeinden und werden mit Ausschlussgrund protokolliert, nicht als fehlende Einwohnerverknüpfungen ausgegeben. BSG=9-Bodenseeflächen ohne Struktur werden ebenfalls ausgeschlossen. BSG=1/GF=8-Landesflächen werden nur bei identischen Schlüsseln und Attributen vereinigt.

Ortsidentitäten werden niemals anhand gleicher Namen verschmolzen. Gleiche NNID mehrfach in einem Import ist ein Fehler. Gleicher normalisierter Name und gerundeter Punkt wird als Verdacht berichtet, nicht automatisch zusammengeführt. GN250 NAME2 ist ein Alternativname desselben Objekts. AX_Gemeinde wird nicht zusätzlich zur Ortslage als Siedlung gezählt; virtuelle Ortslagen werden ausgeschlossen.

Verwaltungsidentitäten folgen amtlichen Schlüsseln, nicht einer behaupteten historischen Kontinuität. Umbenennungen/Gebietsänderungen mit neuen Schlüsseln bleiben nachvollziehbar. Das Modell enthält keinen erfundenen Ortsteil-Bevölkerungswert.

Ein späteres Etymologiemodul könnte Aussagen getrennt als `claim(place_id, text, bibliography, reviewed_at, review_status)` führen. Suchgruppen dürfen diese fachliche Prüfung nicht ersetzen.
