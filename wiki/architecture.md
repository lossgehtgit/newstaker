---
title: "Architektur"
type: architecture
project: newstaker
updated: 2026-09-05
---

# Architektur

## Pipeline (siehe `newstaker/pipeline.py`)

```
fetch.py  --HTTP-->  feedparse.py  --Items-->  normalize.py  --Docs-->  cluster.py  --Cluster-->  rank.py --Score-->  build_board()
   |                                                                                       |
   v                                                                                       v
store.py (raw_fetch, item, feed_state)                                           images.py + weather.py + markets.py
```

1. **Abruf** (`fetch.py`) — conditional GET über ETag/Last-Modified, sonst
   Inhalts-Hash-Vergleich. Läuft **ausschließlich über `requests`**, nicht
   `urllib` (SSL-Falle, siehe overview.md). Rohantworten landen in
   `raw_fetch`, damit jeder Board-Stand ohne Netz rekonstruierbar ist.
2. **Einlesen** (`feedparse.py`) — RSS 2.0, Atom, RSS 1.0/RDF (für
   Nature/Science). Bildextraktion inklusive.
3. **Normalisieren** (`normalize.py`) — kanonische URL (ohne Tracking-Parameter,
   Basis der Item-Identität via `sha256`), Kicker-Strip, Umlautfaltung (`fold()`,
   für Clustering und Suche gleichermaßen), Themen-Zuordnung.
4. **Clustern** (`cluster.py`) — IDF-gewichtete Jaccard-Ähnlichkeit über
   Titel-Wörter, Single-Linkage per Union-Find, plus ein
   Containment-Kriterium für unterschiedlich ausführliche Titel. Schwellen in
   `config.py` (`CLUSTER_THRESHOLD` etc.), kalibriert an echten Daten — **nicht
   ohne neue Kalibrierung ändern**. Kein Merge über Sprachgrenzen (bewusst).
5. **Ranken** (`rank.py`) — fünf gewichtete Komponenten (`config.RANK_WEIGHTS`):
   Quellen-Tier, Anzahl unabhängiger Quellen im Cluster, Feed-Position,
   Aktualität (Halbwertszeit), Themen-Boost.
6. **Bilder** (`images.py`) — dreistufig: Feed-Bild → `og:image` der
   Artikelseite → deterministisch generierte SVG-Kachel (immer verfügbar,
   kein Netz nötig).
7. **Wetter/Märkte** (`weather.py`, `markets.py`) — Open-Meteo bzw. inoffizielle
   Yahoo-Finance-Chart-API, mit TTL-Caching in der DB; bei Totalausfall bleibt
   der letzte gute Stand stehen (siehe `store.save_markets`, absichtlich kein
   Löschen bei leerem Ergebnis — Regressionstest
   `test_markets_totalausfall_erhaelt_alten_stand`).
   - `weather.py` holt in *demselben* Open-Meteo-Request zusätzlich zur
     Tagesübersicht ein `hourly`-Feld (`temperature_2m,weather_code`,
     `forecast_days=1`) und behält davon nur die Stunden des heutigen Tages
     (`store.weather_hour`, PK `(city, hour)`, voller Ersatz je Refresh wie
     bei `weather`). `board_payload()` liefert das zusätzlich als `hours`
     (mit `isNow`-Flag fürs Hervorheben der aktuellen Stunde).
   - `markets.py` speichert seit dem Sparkline-Feature zusätzlich eine
     downgesampelte Kursreihe je Titel (`_downsample()`, `config.
     MARKETS_SPARK_POINTS` Stützstellen, Anfang/Ende bleiben erhalten) als
     JSON in `market.spark` (Migration in `store._migrate`). `board_payload()`
     gibt sie unverändert als `spark`-Liste je Eintrag weiter.
8. **Board bauen** (`pipeline.build_board()`) — SQL-Join über `item`, `source`,
   `state`, `cluster`; wählt je Cluster einen Aufmacher (bestes Tier, dann
   frühestes Datum, dann `id`), berechnet Live-Score, sortiert, filtert
   (Cluster/Thema/Gelesen), deckelt auf `config.BOARD_LIMIT`.

Alle Stufen sind **idempotent**. `pipeline.rebuild()` reprozessiert
ausschließlich bereits gespeicherte `raw_fetch`-Zeilen — kein Netz nötig.

## Determinismus — die zentrale Invariante

Das Projekt hat ein hartes Versprechen: `run.py rebuild` zweimal auf demselben
Datenbestand muss denselben `pipeline.board_digest()`-Fingerabdruck liefern,
egal wie viel reale Zeit dazwischen liegt. Mechanik:

- **`now=` wird explizit durchgereicht**, nie implizit `datetime.now()`
  aufgerufen, an jeder Stelle, die das Ranking oder ein Zeitfenster berührt:
  `build_board()`, `rebuild_clusters()`, `store.items_in_window()`,
  `images.backfill()`/`store.items_missing_image()`. `cmd_rebuild()` in
  `run.py` verankert `now` an `last_fetch_at` (Zeitpunkt des letzten
  *echten* Abrufs), nicht am Moment des CLI-Aufrufs.
- **`feed_rank`** (Position in `config.all_feeds()`) statt Verarbeitungs-
  reihenfolge entscheidet, welcher Feed Thema/URL einer Meldung gewinnt, die
  in mehreren Feeds derselben Quelle auftaucht.
- **Sortierung nach `id`** in `store.items_in_window()` und anderen Abfragen,
  damit Union-Find (Clustering) reproduzierbar läuft.
- `board_digest()` blendet zeitabhängige Felder (`generatedAt`,
  `lastFetchAt`, `score`) explizit aus, bevor gehasht wird.

**Wer hier etwas ändert, das die Verarbeitungsreihenfolge oder eine
`datetime.now()`-Quelle berührt, muss `test_cli_rebuild_ist_reproduzierbar`
grün halten** — zwei frühere Determinismus-Bugs (siehe `SESSION_REPORT.md`
Abschnitt 11) wurden genau hier gefunden, nicht durch Code-Lesen, sondern
durch echte CLI-Läufe mit Pause dazwischen.

## Zwei Auslieferungswege

| | Lokal, live | Cloud, statisch |
|---|---|---|
| Entry Point | `newstaker/server.py` (`run.py serve`) | `newstaker/export.py` (`run.py export`) |
| Frontend | `web/` | `docs/` |
| Transport | JSON-API (`/api/board`, `/api/search`, `/api/state`, …) über `http.server` | statische JSON-Dateien (`docs/data/*.json`) + vorgerenderte SVG-Kacheln (`docs/tiles/`) |
| Gelesen/Gemerkt | serverseitig in SQLite (`state`-Tabelle) | `localStorage`, pro Gerät |
| Filter (Thema/Cluster/Gelesen) | serverseitig (`build_board()`-Parameter) | im Browser (`docs/app.js`), da `board.json` ungedeckelt exportiert wird |
| Auslöser | manuell, `run.py serve` läuft nur bei wachem Mac | GitHub Actions Cron alle 30 Min. (`update.yml`), unabhängig vom Mac |

`server.py`-Routen (JSON, `http.server`-basiert, thread-lokale SQLite-Verbindungen,
`_refresh_lock` verhindert parallele Refreshes):

- `GET /api/board?topic=&hide_read=&cluster=` — Board-Payload
- `GET /api/cluster?id=` — Mitglieder eines Clusters
- `GET /api/search?q=&saved=` — Volltextsuche (FTS5, Umlaut-Faltung)
- `GET /api/weather?city=`, `GET /api/markets`, `GET /api/health`
- `GET /tile/<id>.svg` — generierte Bildkachel
- `POST /api/state` — Gelesen/Gemerkt togglen
- `POST /api/refresh` — manuellen Fetch anstoßen (409 wenn schon einer läuft)

**Wichtig bei Änderungen an der Board-Struktur:** `export.py` baut auf
`pipeline.build_board()` auf (ungedeckelt, `config.BOARD_LIMIT` temporär auf
100000 gesetzt) und muss Bildpfade umschreiben (`_rewrite_tile_urls`,
`/tile/<id>.svg` → `tiles/<id>.svg`, da es keinen Server mehr gibt). Ein neues
Feld im Board-Payload muss ggf. in **beiden** `app.js`-Kopien behandelt werden.

## CI/CD

`.github/workflows/update.yml`: Cron alle 30 Minuten + `workflow_dispatch` +
Push auf `main` (bei Änderungen an Backend/Frontend/CI). Checkt aus, installiert
`requirements.txt`, `run.py init`, `run.py export -v`, committet `docs/` zurück
(nur bei tatsächlicher Änderung), `concurrency`-Gruppe verhindert überlappende
Läufe. **Bekannte Falle:** GitHub deaktiviert geplante Workflows nach 60 Tagen
Repo-Inaktivität automatisch — ein beliebiger Commit oder manueller Lauf
reaktiviert sie.

## Bekannte Fallen (aus echten Bugs, siehe SESSION_REPORT.md §11)

1. `datetime.now()` an einer der oben genannten Zeit-Stellen statt `now=`
   durchzureichen bricht den Determinismus-Test lautlos (kein Crash, nur ein
   anderer Fingerabdruck).
2. `store.save_markets()`/ähnliche "voller Ersatz"-Schreiber dürfen bei einem
   *leeren* Ergebnis (Totalausfall der Datenquelle) NICHT den letzten guten
   Stand löschen.
3. `urllib.request` funktioniert auf der Zielmaschine nicht (SSL) — jeder neue
   Netzcode muss über `requests` gehen.
4. **`main` wird gelegentlich komplett per History-Rewrite überschrieben**
   (privacy-motiviert, z. B. `git filter-repo` zum Entfernen personenbezogener
   Inhalte — bereits zweimal beobachtet, siehe `SESSION_REPORT.md` §11 und
   den Commit „Kommentare neutralisiert (Personenbezug entfernt)"). Danach
   haben **alle** Commits auf `main` neue Hashes, auch der allererste — ein
   `git fetch && git merge`/`git log` zeigt dann „refusing to merge unrelated
   histories" zwischen einem älteren lokalen Klon und `origin/main`.
   **Nie** in diesem Fall den lokalen Stand auf `origin/main` pushen oder
   forcen — das würde die bewusste Bereinigung rückgängig machen. Stattdessen
   lokal `git fetch origin main && git reset --hard origin/main` (nur den
   lokalen Branch-Zeiger korrigieren, `origin/main` ist immer die
   maßgebliche Version). Ein zuvor gemergter PR kann durch so einen Rewrite
   rückwirkend aus `main` verschwinden, obwohl GitHub ihn weiter als
   „merged" anzeigt — nach jedem Rewrite-Verdacht `git log -- <pfad>` auf
   `origin/main` gegenprüfen, statt dem GitHub-PR-Status blind zu vertrauen.
