# ADR 0001: Modularer Monolith und unveränderliche Veröffentlichungen

Status: angenommen, 2026-10-21.

FastAPI/PostGIS und Nuxt hinter nginx erfüllen Suche, Statistik und MVT ohne zusätzliche Dienste. Synchrone SQLAlchemy-Sessions passen zu Import-CLI und CPU-/DB-lastigen Endpunkten. FastAPI übernimmt die Threadpool-Ausführung.

Neue Daten entstehen versionsisoliert. Eine erfolgreiche Importtransaktion und eine getrennte explizite Freischaltung verhindern gemischte Zwischenstände. UUIDs aus GN250-NNID bleiben über Datenversionen stabil. Der aktive Zeiger kann ohne Datenlöschung zurückgestellt werden.

Ein JSON-Filtervertrag wird für alle Abfragen und URL-Zustände verwendet. LIKE ist maskiert, Regex nicht öffentlich verfügbar. Regionale Ortsanteile und gemeindenamensbezogene Bevölkerung bleiben getrennte Größen.

Der erste BKG-Adapter ist für tatsächlich geprüfte CSV-/GPKG-Schemata und EPSG:25832 bestimmt. Schemaänderungen verlangen Prüfung und einen Adapterwechsel. Keine vorgespielte Generalisierung unbekannter Attribute oder Siedlungsklassen.
