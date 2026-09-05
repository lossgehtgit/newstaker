---
title: "Datenbank"
type: database
project: newstaker
updated: 2026-09-05
---

# Datenbank

SQLite, Datei `var/news.db` (nicht im Repo, `.gitignore`), WAL-Modus,
Fremdschlüssel aktiv. Schema lebt komplett als String in
`newstaker/store.py::SCHEMA`, kein ORM, keine Migrationsdateien — kleine,
manuelle `_migrate()`-Funktion für nachträglich hinzugekommene Spalten
(aktuell: `item.feed_rank`).

## Tabellen

| Tabelle | Zweck |
|---|---|
| `source` | Quellen-Stammdaten (`key`, `name`, `tier`, `lang`, `home`) — synchronisiert aus `config.SOURCES` bei jedem `store.init()` |
| `item` | Eine Meldung. PK `id = sha256(canonical_url)`. Siehe unten für die heiklen Spalten. |
| `state` | Gelesen/Gemerkt je `item_id` (nur relevant für die lokale Live-Version — die Cloud-Version nutzt `localStorage`) |
| `cluster` / `cluster_item` | Bei jedem Rebuild komplett neu berechnet (`DELETE` + `INSERT`), kein Upsert |
| `raw_fetch` | Rohantworten je Feed-Abruf — Grundlage für `run.py rebuild` ohne Netz. Aufgeräumt über `RAW_RETENTION_DAYS` (7 Tage), behält aber immer die neueste Zeile je Feed |
| `feed_state` | Letzter bekannter ETag/Last-Modified/Hash je Feed, für conditional GET |
| `og_cache` | Ergebnis der `og:image`-Stufe je URL, damit eine blockierte Seite nie zweimal angefasst wird |
| `weather` | PK `(city, day)`, TTL-gesteuert über `weather_age_minutes()` |
| `market` | ETF/Aktien-Kennzahlen, **voller Ersatz** bei jedem erfolgreichen Refresh (siehe Falle unten) |
| `meta` | Key-Value, u. a. `last_fetch_at` (JSON-kodierter Wert) |
| `item_fts` | FTS5 virtual table für Volltextsuche, siehe unten |

## `item` — die heiklen Spalten

- `id` = `sha256(canonical_url)` — die kanonische URL (ohne Tracking-Parameter,
  siehe `normalize.canonical_url`) ist die **Identität** einer Meldung, nicht
  Titel oder GUID des Feeds.
- `feed_rank` — Position des liefernden Feeds in `config.all_feeds()`. Bei
  einem Update gewinnt bei `topic`/`feed_url` immer der Feed mit dem
  **kleineren** `feed_rank`, unabhängig von der Abrufreihenfolge (siehe
  `store.upsert_item()` — die `CASE WHEN ? < feed_rank`-Klauseln). Das ist der
  Fix für einen echten Bug: dieselbe Meldung stand oft in mehreren Feeds einer
  Quelle mit unterschiedlichem Thema, "letzter Feed gewinnt" machte das
  Ergebnis von der Abrufreihenfolge abhängig.
- `published_at` wird bei einem Update **nur** überschrieben, wenn der Feed
  wirklich ein Datum lieferte (`has_date`) — sonst würde ein Ersatzdatum bei
  jedem Durchlauf neu gesetzt und das Board wäre nicht mehr reproduzierbar.
- `feed_pos` wird bei einem Update nur **verbessert** (`MIN`), nie
  verschlechtert — ein Artikel behält die beste Platzierung, die er je in
  irgendeinem Feed hatte.
- `image_url`/`image_kind` werden bei einem Update nur überschrieben, wenn der
  neue Wert nicht leer ist (kein Zurücksetzen auf "kein Bild").

## Cluster

`cluster`/`cluster_item` werden bei jedem `rebuild_clusters()`-Lauf komplett
verworfen und neu geschrieben (`store.replace_clusters()`: `DELETE` beider
Tabellen, dann `INSERT`). Es gibt keine stabile Cluster-Identität über zwei
Läufe hinweg — die `cluster.id` ist pro Lauf neu.

## `raw_fetch` / Determinismus

`store.items_in_window()` und `store.items_missing_image()` akzeptieren beide
ein optionales `now:` — **immer explizit durchreichen**, sonst verschiebt sich
das Zeitfenster bei jedem Aufruf um ein paar Sekunden und Board-Fingerabdrücke
werden zwischen zwei `rebuild()`-Läufen instabil (siehe architecture.md,
Abschnitt Determinismus). Beide Funktionen sortieren zusätzlich nach `id`,
nicht nach Einfügereihenfolge — das macht Union-Find im Clustering
reproduzierbar.

## Suchindex (`item_fts`, FTS5)

Indiziert wird **gefalteter** Text (`normalize.fold()`: äöü→aeoeue, ß→ss),
nicht der Originaltext. Grund: FTS5s eingebaute `remove_diacritics 2` macht
aus "ö" nur "o", unsere Faltung macht "oe" daraus — würden Original und
gefaltete Suchanfrage gemischt, fände "Zölle" das indizierte "zolle" nie.
Deshalb wird beidseitig (Index **und** Suchanfrage, siehe
`pipeline._fts_query()`) dieselbe Faltung angewendet, und der Index wird
explizit in `store.index_item()` gepflegt (kein Trigger, weil Trigger die
Python-Faltungsfunktion nicht ausführen könnten).

## Bekannte Falle: `market`

`store.save_markets()` macht einen **vollen Ersatz** (`DELETE` + `INSERT`) statt
Upsert je Symbol — damit ein Titel, der aus der Kandidatenliste fällt (z. B.
weil er jetzt Dividende zahlt), nicht als veralteter Datensatz liegen bleibt.
**Aber:** bei einem *Totalausfall* der Datenquelle darf `markets.refresh()`
NICHT mit leeren Listen aufrufen — das würde den letzten guten Stand
ersatzlos löschen (war ein echter, behobener Bug, siehe
`test_markets_totalausfall_erhaelt_alten_stand`). Wer `markets.py` ändert:
diese Unterscheidung (leeres Ergebnis wegen "kein Titel qualifiziert" vs.
"API komplett nicht erreichbar") bewusst erhalten.
