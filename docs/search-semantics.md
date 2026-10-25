# Suchvertrag v1

Alle Datenendpunkte erhalten denselben `q`-Parameter: ein JSON-serialisiertes `Filter`-Objekt. Definition in OpenAPI und unter `/api/v1/filter-schema`. Beispiel:

```json
{"schema_version":1,"dataset":"bkg-2024","groups":[{"id":"a","title":"ach ohne bach","color":"#126b61","patterns":[{"mode":"suffix","value":"ach"}],"exclusions":[{"mode":"suffix","value":"bach"}]}],"regions":["state:01"],"kinds":[],"bbox":null}
```

`suffix`, `prefix`, `contains`, `exact` vergleichen vollständige Namen. Gruppeneinträge sind ODER-verknüpft. Ein Ausschluss trifft, wenn **irgendein** Original- oder Alternativname **irgendeinem** Ausschlussmuster entspricht. Die ganze Ortsidentität entfällt dann nur für diese Gruppe. Zwischen Gruppen gilt ODER. Die Gruppensumme kann größer als die eindeutige Ortszahl sein.

Auch ohne eingetragene zusätzliche Endungsmuster (`variants: []` im Ansichtslink) werden die alternativen Ortsnamen aus der Quelle durchsucht. `sted` trifft nicht auf den Hauptnamen „Borgstedt“, aber auf dessen alternativen Namen „Borgsted“. Die Detailtrefferliste und die Auswahl eines Orts zeigen in solchen Fällen `Treffer über „Borgsted“` an. `sted` und `stedt` bleiben getrennte Suffixmuster. Beim lokalen GN250-Bestand `bkg-2024-r3` treffen alle 16 Ergebnisse für `sted` über alternative Ortsnamen; die Hauptnamen enden jeweils auf `stedt`.

Normalisierung `nfc-casefold-ucd15.1-v1`: NFC → Python Unicode Casefold → NFC. Python 3.13 mit Unicode 15.1 ist gepinnt. Keine Transliteration: ä ≠ ae, ö ≠ oe, ü ≠ ue. ß entspricht ss. Originalnamen bleiben erhalten. Klammern, Zusätze, Leerzeichen und Satzzeichen werden weder aus Namen noch aus API-Mustern entfernt. Rein leere Muster und Steuerzeichen sind ungültig. Die API interpretiert keine Minusnotation.

Nur die UI entfernt im Modus „Endet mit“ ein führendes `-` und trimmt die einzelne Eingabe. Die neue Übersicht verwendet eine einfache einzelne Endung je Karte; Kommas bleiben darin literal. Mehrere ODER-Muster sind weiterhin in der API möglich. Wörtliche Kommata oder ein führender wörtlicher Bindestrich sind über die API möglich. Exakte, Präfix- und Enthält-Suche entfernen keinen Bindestrich. `%`, `_` und Backslash werden für LIKE maskiert; alle Werte sind SQL-Parameter. Es gibt keine öffentliche Regexausführung. ing und ingen sind getrennt.

Maximal zehn Gruppen, acht Einschluss- und acht Ausschlussmuster je Gruppe; Muster 1–80 Zeichen, q höchstens 12.000 Zeichen. Bis zwölf Regionsfilter, zwei Ortsarten. Regionsfilter untereinander ODER; Ortsart/Region/Ausschnitt/Namensgruppen miteinander UND. Regionen gelten räumlich nach VG25 `ST_Covers`; Grenzpunkte können in mehreren Regionen liegen. Keine willkürliche Gemeindezuordnung.

Anteile: Nenner umfasst alle Ortsidentitäten mit denselben Datenversions-, Regions-, Ortsart- und expliziten Bounding-Box-Filtern. Der Namensfilter gilt nur im Zähler. Reines Kartenverschieben beeinflusst diesen Nenner nicht. Ausgewiesene regionale Ergebnisse können sich an Grenzpunkten überschneiden.

Einwohnerauswertung: nur der **eigene Gemeindename** der Gemeindeebene; jede Gemeinde einmal. Regionsfilter folgen hierfür amtlichen Hierarchieschlüsseln. Ein explizites bbox wählt schneidende Gemeinden; Ortsartfilter gelten ausschließlich für Ortszahlen. Fehlt bei einer passenden Gemeinde der Einwohnerwert, wird keine vollständige Bevölkerungssumme angegeben. Die Auswertung sagt nichts über die Zahl von Menschen in einzelnen GN250-Ortslagen aus.

Die neue Übersicht speichert `s` als URL-Vertrag **version:2**: genau zehn `endings` in Reihenfolge, `region`, `kind`, explizites `dataset`, `mode: "share"` und `grid: "laea-3035-square-20000-origin-0-v1"`. Die Übersicht bietet nur literale Endungen; die vollständige API behält ihre Suchmodi. Alte version:1-Links werden ausdrücklich als ungültig gemeldet, nicht still umgedeutet. Die Methodenseite und der Rückweg zur Übersicht erhalten den Linkzustand. Laden validiert Grenzen und Struktur. Ein nicht verfügbarer expliziter Datenstand ergibt HTTP 410 und eine sichtbare Meldung; es gibt keinen automatischen Standwechsel.

Pagination: Name in PostgreSQL-C-Kollation, danach stabile öffentliche UUID; Offset 0–1.000.000, Limit 1–100. Statistik unabhängig von Pagination. CSV/GeoJSON maximal 10.000 Orte, darüber 413 ohne Teildatei. CSV schützt führende Formelzeichen (auch nach Leerraum) durch Apostroph. GeoJSON liefert WGS84-Länge/Breite, eindeutige IDs, Gruppenzugehörigkeiten und Quellenmetadaten.

„Kirchbach“ passt sowohl zu `ach` als auch zu `bach`. Die zehn Karten sind unabhängige, überlappende Muster; keine Summe als vermeintlich eindeutige Ortszahl. Die Basiszahl oben zählt sämtliche berücksichtigten Orte ohne Endungsfilter.

Die Rasterendpunkte verwenden denselben Filtercompiler. `grid/values` fordert ein einzelnes Suffixmuster je Karte (bis zehn). Der Zähler jeder Zelle verwendet ein EXISTS über Namen, der Nenner alle eindeutigen Ortsobjekte derselben Zelle und Grundfilter. Fehlender Zellwert bedeutet Nenner 0/keine Daten, ein vorhandener Wert mit count 0 bedeutet 0 %. `grid/cells/{cell}/places` liefert Anteil, Zähler, Nenner und stabile paginierte Namen einschließlich passender Varianten erst bei Bedarf.
