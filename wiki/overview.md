---
title: "Überblick"
type: overview
project: newstaker
updated: 2026-09-05
---

# News-Taker — Überblick

Persönlicher, **deterministischer** Nachrichtentracker für Liv. Kein KI-Agent
im Datenpfad: nichts wird von einem Modell zusammengefasst, sortiert, geclustert
oder übersetzt. Dieselben Rohdaten ergeben immer dasselbe Board (verankert in
`tests/test_newstaker.py::test_cli_rebuild_ist_reproduzierbar`).

Repo: `github.com/lossgehtgit/newstaker` (öffentlich, wegen kostenlosem
GitHub Pages + Actions). Live-Seite: `https://lossgehtgit.github.io/newstaker/`.

## Tech-Stack

- **Sprache:** Python 3 (Standardbibliothek so weit möglich).
- **Einzige externe Abhängigkeit:** `requests` (`requirements.txt`) — wegen
  einer lokalen SSL-Falle: `urllib.request` scheitert auf der Zielmaschine an
  `CERTIFICATE_VERIFY_FAILED` (kein CA-Bundle verdrahtet). `requests` bringt
  `certifi` mit. **Jeder Netzcode muss über `fetch.py`/`requests` laufen,
  nicht über `urllib`.**
- **Datenbank:** SQLite (`var/news.db`, nicht im Repo), WAL-Modus, FTS5 für
  Volltextsuche. Kein ORM.
- **Frontend:** Vanilla HTML/CSS/JS, **kein Node, kein Buildstep**, zwei
  parallele Kopien (`web/` lokal-live, `docs/` statisch für GitHub Pages).
- **CI/Cron:** GitHub Actions (`.github/workflows/update.yml`), alle 30 Minuten.

## Einstiegspunkte

| Datei | Rolle |
|---|---|
| `run.py` | CLI-Einstiegspunkt: `init \| fetch \| serve \| rebuild \| export \| status` |
| `newstaker/server.py` | HTTP-Server (JSON-API + Auslieferung von `web/`) für die lokale Live-Version |
| `newstaker/export.py` | Statischer Export nach `docs/` für GitHub Pages |
| `newstaker/pipeline.py` | Verdrahtet die gesamte Pipeline (`refresh()`, `rebuild()`, `build_board()`) — zentrale Orchestrierung |
| `newstaker/config.py` | Alle Stellschrauben an einem Ort: Quellen, Themen, Ranking-Gewichte, Cluster-Schwellen, Marktkandidaten |

Details zum Datenfluss: siehe [architecture.md](architecture.md).
Details zum Schema: siehe [database.md](database.md).

## Befehle

```bash
python3 run.py init && python3 run.py fetch -v && python3 run.py serve
```

| Befehl | Wirkung |
|---|---|
| `python3 run.py init` | Datenbank anlegen |
| `python3 run.py fetch -v` | Feeds abrufen, Bilder, Cluster, Wetter, Märkte — mit Tabelle je Feed |
| `python3 run.py serve` | Board unter `localhost:8787` ausliefern |
| `python3 run.py rebuild` | Neu berechnen aus gespeicherten Rohantworten, **ohne Netz** |
| `python3 run.py export -v` | Abrufen + statischen Export nach `docs/` schreiben (für GitHub Pages) |
| `python3 run.py status` | Zustandsbericht, zeigt auch stumme Feeds |

**Tests** (63 Stück, keine Netzabhängigkeit):

```bash
python3 -m unittest discover -s tests -v
```

Kein Node/npm-Befehl nötig — es gibt keinen Buildstep.

## Verzeichnisstruktur

```
run.py                CLI
newstaker/            Backend-Paket (Pipeline, Server, Export, Config)
web/                  Frontend, lokale Live-Version (liest die JSON-API von server.py)
docs/                 Frontend, statische Cloud-Version + generierte Daten (data/, tiles/) — von GitHub Pages ausgeliefert
tests/test_newstaker.py  63 Tests, ohne Netzzugriff
.github/workflows/    update.yml — 30-Minuten-Cron, exportiert nach docs/ und pusht zurück
scripts/              com.newstaker.fetch.plist.template — Vorlage für lokalen launchd-Auto-Abruf (macOS)
var/                  Datenbank + Logs, NICHT im Repo (.gitignore)
wiki/                 dieses Wiki (für Claude Code als externes Gedächtnis)
```

## Zwei Betriebsarten (wichtig für jede Änderung)

1. **Lokal, live** (`web/` + `server.py`) — Gelesen/Gemerkt liegt serverseitig
   in SQLite, Mac und iPhone sehen denselben Stand.
2. **Cloud, statisch** (`docs/` + `export.py`) — GitHub Actions holt alle
   30 Min. frische Feeds auf einem Runner, exportiert dieselbe deterministische
   Pipeline als JSON. Gelesen/Gemerkt liegt hier pro Gerät in `localStorage`.

**Jede Backend-Änderung, die die Board-Struktur betrifft, muss in beiden
Frontends (`web/app.js` und `docs/app.js`) berücksichtigt werden** — sie sind
funktional identische, aber getrennt gepflegte Kopien.

## Bewusste Nicht-Ziele

- Keine Zusammenfassungen, keine Übersetzung, keine Artikelanzeige in der App.
- Kein Cluster-Merge über Sprachgrenzen (De/En getrennt, bewusst getestet und verworfen — siehe README).
- Marktübersicht ist **keine Anlageempfehlung**, nur berechnete Kennzahlen.

## Wo weiterlesen

- `README.md` — ausführliche Nutzerdokumentation (Quellen, Kalibrierung, Bedienung).
- `SESSION_REPORT.md` — Entstehungsgeschichte, gefundene Bugs, Audit-Ergebnis (historisch, nicht laufend gepflegt).
- [architecture.md](architecture.md) — Pipeline-Stufen, Modulverantwortung, Determinismus-Mechanik.
- [database.md](database.md) — SQLite-Schema im Detail.
