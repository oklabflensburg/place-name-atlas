# ortsnamenatlas.oklabflensburg.de mit systemd und nginx betreiben

Diese Anleitung richtet die bereits importierte/veröffentlichte Anwendung auf einem bestehenden Debian-/Ubuntu-Webserver ein: Benutzer `oklab`, Repository `/opt/git/place-name-atlas`, vorhandene `.env`, PostgreSQL und nginx. Datenbankverbindungen, Rollen, Daten und andere Anwendungen bleiben unverändert.

Das eigene Profil [infra/systemd/production.json](../infra/systemd/production.json) legt die Bindungen fest:

| Bestandteil | Adresse |
|---|---|
| FastAPI | `127.0.0.1:8015` |
| Gebautes Nuxt-Frontend | `127.0.0.1:3015` |
| Öffentliche Domain | `ortsnamenatlas.oklabflensburg.de` |

Die belegten Ports 8000 (`hackathonhub-api.service`) und 3000 (`packages-registry-frontend.service`) werden nicht verwendet. Auch der von einem anderen Dienst belegte Port 8080 wird hier nicht benötigt. `infra/local.json` bleibt das separate Entwicklungsprofil; frühere Änderungen dort müssen für diesen Betrieb nicht zurückgesetzt werden.

## 1. Voraussetzungen und Build

Die Domain muss per DNS auf den Webserver zeigen. Auch ein vorhandener AAAA-Eintrag muss zum richtigen Server führen. Port 80 muss für eine neue HTTP-01-Zertifikatsvalidierung und Port 443 für HTTPS erreichbar sein. DNS und Zertifikatsausstellung werden vom Generator nicht verändert oder als erledigt ausgegeben.

Als `oklab`:

```sh
cd /opt/git/place-name-atlas
sudo ss -ltnp '( sport = :8015 or sport = :3015 )'
UV_LINK_MODE=copy uv sync --locked
pnpm install --frozen-lockfile
pnpm build
```

Bei einem Listener auf 8015/3015 zuerst dessen Zuordnung klären; keine fremden Prozesse beenden. Sind Abhängigkeiten und Produktionsbuild bereits aktuell, entfällt deren erneute Erstellung. Der Build liegt unter `apps/web/.output/server/index.mjs`; sein Spitzenverbrauch ist hier nicht gemessen. Python-/Node-Versionen stehen im [README](../README.md).

## 2. Vollständige Konfiguration erzeugen

```sh
uv run --locked python scripts/render-systemd.py --user oklab
systemd-analyze verify --man=no artifacts/systemd/*.service
```

Der Generator schreibt standardmäßig ausschließlich nach `artifacts/systemd/` und erzeugt:

- `place-name-atlas-api.service` und `place-name-atlas-web.service`;
- `nginx-locations.conf` für API, Frontend und deren Healthchecks;
- `nginx-site.http.conf` als vollständigen HTTP-vHost für Erstprüfung/ACME;
- `nginx-site.https.conf` mit HTTPS-vHost, HTTP-Weiterleitung und ACME-Ausnahme;
- `certbot-deploy-hook.sh`, der nginx nach Erneuerung genau dieses Zertifikats prüft und neu lädt.

Die Units verwenden absolute Pfade und die tatsächlich in der aktuellen Shell ausgewählte Node-Binärdatei (auch bei nvm/asdf/mise). Das Backend erhält den absoluten Profilpfad über `ATLAS_LOCAL_CONFIG`, beide Prozesse verwenden dieselben Profilports. Die bestehende `.env` wird als `EnvironmentFile` gelesen; bekannte Datenbankzugangsdaten werden aus der Frontendumgebung entfernt. `PORT`, `HOST` und `PYTHONPATH` einer anderen Shellkonfiguration können die expliziten Startparameter nicht überschreiben. Es laufen je ein Backend-/Frontendprozess, keine Entwicklungsserver und keine Installation, Migration oder Veröffentlichung beim Dienststart.

Standardmäßig verwendet HTTPS die Certbot-Pfade `/etc/letsencrypt/live/ortsnamenatlas.oklabflensburg.de/fullchain.pem` und `privkey.pem`. **Existiert bereits ein gültiges Zertifikat**, dessen bestehende Pfade verwenden und die Neuausstellung in Schritt 5 überspringen:

```sh
uv run --locked python scripts/render-systemd.py --user oklab \
  --tls-certificate /PFAD/ZUM/BESTEHENDEN/fullchain.pem \
  --tls-certificate-key /PFAD/ZUM/BESTEHENDEN/privkey.pem
```

Beide Pfade müssen zusammen angegeben werden. Der Generator liest/kopiert keine privaten Schlüssel. nginx muss den Schlüssel beim Prüfen/Laden lesen können. Weitere Optionen: `--project-dir`, `--node`, `--config`, `--domain`, `--nginx-snippet`, `--acme-webroot`, `--output`. Ein eigenes Profil enthält `host`, `apiPort`, `webPort` und `domain`.

## 3. Nur die Atlas-Dienste installieren/starten

```sh
sudo install -m 0644 artifacts/systemd/place-name-atlas-api.service /etc/systemd/system/
sudo install -m 0644 artifacts/systemd/place-name-atlas-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl reset-failed place-name-atlas-api.service place-name-atlas-web.service
sudo systemctl enable place-name-atlas-api.service place-name-atlas-web.service
sudo systemctl restart place-name-atlas-api.service place-name-atlas-web.service

systemctl status --no-pager place-name-atlas-api.service place-name-atlas-web.service
curl --fail http://127.0.0.1:8015/health/ready
curl --fail http://127.0.0.1:3015/health/web
```

`reset-failed` hebt auch die nach früheren Portkonflikten erreichte Startsperre dieser beiden Units auf. Andere Dienste werden nicht gestoppt oder neu gestartet. Die Healthchecks prüfen zusätzlich zum laufenden Prozess die API-Bereitschaft bzw. Frontenderreichbarkeit.

## 4. nginx-vHost installieren

Zuerst prüfen, ob die Domain bereits in einer aktiven Konfiguration vorkommt:

```sh
sudo grep -RlnF 'ortsnamenatlas.oklabflensburg.de' /etc/nginx/sites-enabled /etc/nginx/conf.d
```

Für die Domain genau einen aktiven vHost verwenden. Eine bereits vorhandene ausschließlich dieser Anwendung gehörende Datei vor dem Ersetzen sichern und weiterverwenden. Enthält eine Datei weitere Anwendungen, nur die zugehörigen Atlas-Serverblöcke ersetzen. Keine andere Site deaktivieren und keinen zweiten konkurrierenden `server_name` anlegen. Die folgenden Dateinamen sind der vollständige Weg für eine neue Atlas-Site.

```sh
sudo install -d -m 0755 /etc/nginx/snippets /var/lib/place-name-atlas/acme
sudo install -m 0644 artifacts/systemd/nginx-locations.conf /etc/nginx/snippets/place-name-atlas.locations.conf
```

**Mit vorhandenem gültigem Zertifikat** direkt die endgültige Konfiguration aus Schritt 6 verwenden. **Ohne Zertifikat** zunächst den vollständigen HTTP-vHost installieren:

```sh
sudo install -m 0644 artifacts/systemd/nginx-site.http.conf /etc/nginx/sites-available/ortsnamenatlas.oklabflensburg.de
sudo ln -s /etc/nginx/sites-available/ortsnamenatlas.oklabflensburg.de /etc/nginx/sites-enabled/ortsnamenatlas.oklabflensburg.de
sudo nginx -t && sudo systemctl reload nginx
curl --fail --resolve ortsnamenatlas.oklabflensburg.de:80:127.0.0.1 \
  http://ortsnamenatlas.oklabflensburg.de/health/ready
```

Der Link wird nur beim erstmaligen Aktivieren angelegt; einen bestehenden korrekten Link beibehalten. Die Konfiguration wird nur nach erfolgreicher Prüfung neu geladen. Das Location-Snippet routet `/api/v1/` und `/health/` zum Backend, `/health/web` und alle übrigen Seiten zum Frontend. Es enthält selbst keinen `server_name` und wird innerhalb des erzeugten vHosts eingebunden. Gleichnamige Locations und Headerpuffer nicht zusätzlich manuell duplizieren.

## 5. Neues Zertifikat ohne nginx-Stopp beziehen

Nur erforderlich, wenn kein vorhandenes gültiges Zertifikat eingesetzt wird. Für eine neue Certbot-Installation unter Debian/Ubuntu gegebenenfalls `sudo apt-get install certbot` ausführen. Bestehende Zertifikatsverwaltung anderer Domains beibehalten.

```sh
sudo certbot certonly --webroot \
  --webroot-path /var/lib/place-name-atlas/acme \
  --cert-name ortsnamenatlas.oklabflensburg.de \
  --domain ortsnamenatlas.oklabflensburg.de
```

Certbot fragt gegebenenfalls Kontaktdaten und die Zustimmung zu seinen Bedingungen ab. `certonly --webroot` verwendet den laufenden nginx und verändert dessen vHosts nicht. Der Generator hat dafür `/.well-known/acme-challenge/` vorbereitet. Bei fehlgeschlagener Ausstellung die funktionierende HTTP-Konfiguration beibehalten und zuerst DNS/Erreichbarkeit korrigieren; den HTTPS-vHost erst mit vorhandenem Zertifikat aktivieren.

## 6. HTTPS aktivieren und Erneuerung prüfen

```sh
sudo install -m 0644 artifacts/systemd/nginx-site.https.conf /etc/nginx/sites-available/ortsnamenatlas.oklabflensburg.de
```

Bei erstmaliger Einrichtung mit bereits vorhandenem Zertifikat zusätzlich den Link aus Schritt 4 anlegen. Danach:

```sh
sudo nginx -t && sudo systemctl reload nginx
curl --fail --resolve ortsnamenatlas.oklabflensburg.de:443:127.0.0.1 \
  https://ortsnamenatlas.oklabflensburg.de/health/ready
curl --fail https://ortsnamenatlas.oklabflensburg.de/health/ready
```

HTTP leitet jetzt unter Erhalt von Pfad und Query auf HTTPS weiter. Die ACME-Challenge bleibt über HTTP erreichbar. Der erste curl-Aufruf prüft lokalen vHost und Zertifikat mit dem richtigen Hostnamen; der zweite zusätzlich die öffentliche Erreichbarkeit. Zertifikatsprüfung bleibt aktiviert.

Bei Verwendung des oben angelegten Certbot-Zertifikats den auf dessen Verzeichnis begrenzten Deploy-Hook installieren:

```sh
sudo install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
sudo install -m 0755 artifacts/systemd/certbot-deploy-hook.sh /etc/letsencrypt/renewal-hooks/deploy/place-name-atlas-nginx
sudo certbot renew --cert-name ortsnamenatlas.oklabflensburg.de --dry-run
systemctl list-timers --all '*certbot*'
```

Die bestehende Erneuerungsplanung verwenden. Bei einer neuen apt-Installation ohne aktive Zeitplanung kann `sudo systemctl enable --now certbot.timer` diese aktivieren. Andere Zertifikate lösen den Atlas-Hook nicht aus; er beendet keine Dienste. Bei anderer Zertifikatsverwaltung deren vorhandenen Erneuerungs-/Reload-Weg beibehalten, statt zusätzliche Certbot-Hooks zu installieren.

## Logs und Updates

```sh
journalctl -u place-name-atlas-api.service -u place-name-atlas-web.service -n 100 --no-pager
```

Updates/Builds im Wartungsfenster oder in einem separaten Releaseverzeichnis vorbereiten. Nach Änderungen am Profil, Repository-/Node-Pfad oder den Zertifikatspfaden erneut rendern, prüfen und die erzeugten appbezogenen Dateien installieren. Nach geänderten Units `daemon-reload` und nur die beiden Atlas-Dienste neu starten; nach nginx-Änderungen `nginx -t` und Reload. Eine reine `.env`-Änderung erfordert einen Neustart der jeweiligen Atlas-Dienste. Datenbankeinrichtung, Migration, Import und Publish bleiben separate administrative Schritte.

Referenzen: [systemd.service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html), [nginx-Hostnamen](https://nginx.org/en/docs/http/server_names.html), [nginx-HTTPS](https://nginx.org/en/docs/http/configuring_https_servers.html), [Certbot-Webroot und Erneuerung](https://eff-certbot.readthedocs.io/en/stable/using.html).
