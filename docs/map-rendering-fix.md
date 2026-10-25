# Fehlende Rasterpunkte: Befund und Korrektur

Prüfung vom 21.10.2026 über `http://127.0.0.1:8080`.

## Beobachteter Zustand

Die im Hostterminal ausgeführte Browserdiagnose lieferte echte HTTP-200-Antworten: `bkg-2024-r3`, 45.858 Orte, 1.006 belegte Zellen und 1.062 Geometriezellen. Die Werteantwort enthielt Grundgesamtheiten und alle zehn Zähler pro Zelle. Jede Desktopkarte hatte 1.062 Kreise mit endlichen Attributen und positivem Radius innerhalb derselben viewBox. Die SVGs waren 234 × 313,45 CSS-Pixel groß; JavaScriptfehler wurden nicht gemeldet.

Screenshots der einzelnen SVGs enthielten tatsächlich gezeichnete Pixel in den Farben ihrer Treffermengen: zwischen 213 (-by) und 12.918 (-dorf). Der Desktop-Screenshot wurde hier visuell geöffnet und bestätigt die geografischen Verteilungen. Der Nutzer bestätigte anschließend sichtbare Punkte auch im ursprünglich betroffenen Tab nach Neuladen. [Gesicherter Hostbefund](reports/maps-host-initial-diagnosis.json).

Die ursprüngliche leere Darstellung war damit nicht mehr reproduzierbar. Eine konkrete fehlerhafte Antwort aus dem ursprünglich betroffenen Browsercache wurde nicht aufgezeichnet. Die unten belegte Schwachstelle darf deshalb nicht als rückwirkend bewiesener Cacheinhalt dieses Tabs dargestellt werden.

Die erste Mobilmessung traf abgetrennte Elemente mit leeren CSS-Werten und Nullgrößen; der anschließende Screenshot zeigte einen neuen Ladevorgang. Während dieser Diagnose wurden die Quelldateien noch geändert. Das belegt keine dauerhafte fehlerhafte Mobilprojektion. Die überarbeitete Diagnose wartet nach Größenänderung und Neuladen auf abgeschlossene Anfragen und geladene Kartendaten.

## Belegter Fehler im Datenvertrag

Die frühere Polygongeometrie und die jetzigen Kreismittelpunkte verwendeten dieselbe API-Adresse, Rasterkennung und Datenversion. Zugleich wurden Geometrieantworten für 24 Stunden als `immutable` ausgeliefert. Der Client prüfte nur Daten- und Rasterkennung; TypeScript prüft kein tatsächliches JSON. Eine alte Zelle mit `{id,path}` konnte deshalb als `{id,cx,cy}` verwendet werden. Bei fehlenden Mittelpunkten lässt Vue die Attribute weg. SVG verwendet den Ursprung (0,0), außerhalb des metrischen Deutschlandausschnitts. Trefferzahlen und Legenden konnten dabei korrekt aussehen. Der Regressionstest rekonstruiert diesen alten Vertrag mit korrekten Gesamtzahlen und fehlenden Mittelpunkten.

Die Darstellung hat jetzt eine eigene Version `circle-centers-v1`, unabhängig von der unveränderten metrischen Rasterkennung. Der Client fordert sie als Queryparameter an und trifft damit keine alten unveränderlichen Cacheeinträge. Er fordert zusätzlich Revalidierung an. Geometrieantworten erhalten `private, max-age=0, must-revalidate` und `X-Grid-Representation`.

## Zellprüfung und Größenberechnung

Vor der Freigabe aller zehn Karten prüft der Client tatsächliche Koordinaten, Rasterdefinition, positive viewBox-Abmessungen, eindeutige Zellen und vollständig innerhalb der viewBox liegende Kreise. Die Werteprüfung kontrolliert Datenstand, Gruppenreihenfolge, Zellabdeckung, Grundgesamtheiten, Zählergrenzen und die Übereinstimmung aller Zell- und Gesamtzahlen. Fehlende Zellen lösen eine Meldung zur Datenversion und Orts-Zell-Zuordnung aus. Ungültige Antworten erscheinen nicht als erfolgreich geladen und bleiben nicht im Geometriecache. Ladezustand, Datenfehler, keine erfassten Orte und keine passenden Endungen sind getrennt sichtbar.

Die API liefert metrische Mittelpunkte, keine Gradangaben oder Rasterindizes als Zeichenkoordinaten. Für `216_134` ist der Mittelpunkt `(4.330.000, -2.690.000)` Meter. Die gemeinsame viewBox ist ebenfalls metrisch. Die Y-Achse ist bereits für SVG gespiegelt; eine zweite Spiegelung wäre falsch. SVG skaliert den Ausschnitt mit `preserveAspectRatio` in die Karte. Die Prüfung umfasst jeden vollständigen Kreis mit Radius 8.200 m.

Die Kartenfläche erhält ihre Höhe aus Breite und `aspect-ratio`, ohne Flex-Wachstum. Das SVG füllt sie absolut positioniert. Dadurch gibt es keine zyklische Abhängigkeit zwischen prozentualer SVG-Höhe und unbestimmter Flexhöhe. Es wird keine anfängliche Containergröße gespeichert. Später eintreffende Daten werden reaktiv eingesetzt; Größenänderungen übernimmt SVG. Das Zehn-Karten-Grid bleibt erhalten.

Migration 0002, Importdaten und Veröffentlichungszeiger wurden nicht geändert. Die SQL-Prüfung verwendet ausschließlich einen separaten temporären PostGIS-Cluster.

## Prüfungen wiederholen

Aktueller zusammengefasster Prüfstand: [map-rendering-validation.json](reports/map-rendering-validation.json). Die lokalen Tests bestehen: 35 JavaScript-Tests einschließlich tatsächlicher Hostantwort, 21 Python-Tests (20 DB-Tests ohne Testdatenbank übersprungen), Typprüfung, Produktionsbuild, SSR und die isolierte echte PostGIS-Prüfung. Die neuen HTTP-Antworten über nginx bestätigen außerdem die Formatversion, Cache-Header und vollständig innerhalb der viewBox liegende Kreise: [Host-API-Prüfung](reports/maps-host-api-check.json).

```sh
# Echte Produktionsabfragen im isolierten PostGIS, ohne laufende DB zu ändern:
ATLAS_GRID_CHECK_EXPORT=/tmp/atlas-map-render-input.json PYTHONPATH=apps/api \
  .venv/bin/python scripts/check-grid-offline.py --real
ATLAS_GRID_CHECK_EXPORT=/tmp/atlas-map-render-input.json pnpm test
.venv/bin/python -m pytest -q
pnpm typecheck
pnpm build
node scripts/check-ssr.mjs

# Browserprüfung am tatsächlichen nginx:
pnpm local:stop
pnpm exec playwright test --config playwright.real.config.ts

# Kurzer Export beider Übersichten in CSS-Auflösung, ohne vorherige Fokustests:
pnpm exec playwright test --config playwright.real.config.ts capture.spec.ts

# Lesende Diagnose einer bereits laufenden Anwendung:
pnpm local:diagnose-maps
```

Die Browserprüfung kontrolliert direkten Aufruf, Neuladen, Größenänderungen, beide Farbmodi, Regionswechsel, Endungsänderung mit Variante sowie Hover/Touch und echte Ortsnamen. Auf jeder Karte werden SVG-Größe, Kreiskoordinaten und tatsächlich gemalte Kreispixel geprüft. Ein leeres SVG genügt nicht. Die Diagnose erstellt außerdem Desktop- und Mobilbilder vor und nach Neuladen.

Der erste Host-Testlauf scheiterte an einem bestehenden Testselektor für das Auswahlfeld „Farbmodus“. Die Auswahlfelder werden nun über ihre tatsächliche Combobox-Rolle gefunden. Außerdem erhält der Test-Projektmanager beim Aufräumen `SIGTERM` mit 15 Sekunden Zeit; Playwrights voreingestelltes `SIGKILL` würde seine Bereinigung der selbst gestarteten Dienste umgehen. Beide Korrekturen betreffen den Testablauf, nicht die Ortsdaten. Der neue Lauf schreibt seinen maschinenlesbaren Bericht nach `artifacts/maps-playwright-results.json`.

Vorgesehener Start: `pnpm preview:local` nach `pnpm build`. URL: `http://127.0.0.1:8080`.
