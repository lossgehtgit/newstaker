# News-Taker — Sitzungsbericht

Zusammenfassung der gesamten Konversation, chronologisch, mit dem, was am Ende
tatsächlich läuft und was noch von Liv kommen muss. Geschrieben am Ende der
Bausitzung als Übergabedokument — kein Ersatz für `README.md` (die bleibt die
Bedienungsanleitung), sondern die Geschichte dahinter.

---

## 1. Auftrag

Liv hatte in Claude Design zwei Entwürfe für einen persönlichen Newstracker
gebaut (`News-Board.dc.html`, Varianten **1a Raster** und **1b Redaktion**)
und wollte daraus eine echte, funktionierende App machen:

- **Basis 1a**, mit vier Abweichungen: Wetterkarte aus 1b, Cluster-Übersicht
  aus 1b oben im Board, Themen-Pills aus 1b, **keine** Nummerierung vor den
  Meldungen, dafür **ein Bild bei jeder Schlagzeile**.
- **Deterministisch, kein KI-Agent** — keine Zusammenfassung, kein Ranking,
  keine Übersetzung durch ein Modell.
- **Pflichtquellen:** Handelsblatt, Tagesschau, Spiegel, dazu vergleichbar
  kreditible internationale Quellen.
- Aufklappbare Teaser, serverseitiger Gelesen/Gemerkt-Status, Volltextsuche.
- Betrieb: lokal auf dem Mac, mit automatischem Abruf.

## 2. Recherche vor dem Bau (Plan-Modus)

Bevor Code geschrieben wurde, wurde die Umgebung und jede Datenquelle live
geprüft, nicht angenommen:

- **Umgebung:** Python 3.14, `requests`+`certifi`, SQLite 3.50 mit FTS5 —
  aber **kein Node, kein npm, kein Docker**. Damit war der Stack
  vorgezeichnet: Python-Backend, statisches Frontend, kein Buildstep.
- **SSL-Falle gefunden:** `urllib.request` scheitert auf dieser Maschine an
  `CERTIFICATE_VERIFY_FAILED` (kein CA-Bundle verdrahtet). `requests`
  funktioniert. Ohne dieses Wissen hätte kein einziger Feed geladen.
- **47 Feeds über 21 Quellen einzeln getestet** (HTTP-Status, Item-Zahl,
  Bildquote): Handelsblatt, Tagesschau, Spiegel liefern zuverlässig; dazu
  FAZ, ZEIT, SZ, heise, BBC, NYT, Guardian, FT, WSJ, Al Jazeera, NPR,
  Economist, CNBC, Nature, Science, Quanta, Phys.org, Ars Technica.
  **Reuters und AP haben ihre öffentlichen RSS-Feeds abgeschaltet** (404/401)
  — anders als die Beispieldaten im Entwurf suggerierten.
- **Clustering-Schwelle kalibriert** an 484 echten Meldungen aus sieben
  deutschen Quellen: 0.34 ergab sich als der Wert, bei dem ausschließlich
  korrekte Mehr-Quellen-Gruppen entstehen.
- **Cross-Language-Clustering getestet und verworfen:** ein
  Eigennamen-Overlap-Verfahren über 302 deutsche und 247 englische Meldungen
  ergab 7 Kandidaten, davon nur 2 korrekt — der Rest Namenskoinzidenzen
  ("Donald Trump" an einem Tag in drei unabhängigen Geschichten). Deshalb
  clustert die App nur innerhalb einer Sprache.

Diese Rechercheergebnisse gingen unverändert in `config.py` und die
Code-Kommentare ein, damit die Begründung für jede Zahl nachvollziehbar
bleibt.

## 3. Backend (deterministische Pipeline)

Aufgebaut in `newstaker/`:

| Datei | Zweck |
|---|---|
| `config.py` | Quellen-Registry, Themen, Ranking-Gewichte, Cluster-Schwellen, Marktkandidaten |
| `fetch.py` | HTTP über `requests`, conditional GET (ETag/Last-Modified), Höflichkeitspause pro Host |
| `feedparse.py` | RSS 2.0, Atom **und** RSS 1.0/RDF (für Nature/Science, nachträglich ergänzt, als der erste Test dort 0 Items lieferte) |
| `normalize.py` | Kanonische URL, Kicker-Strip, Umlautfaltung, leichte Endungsnormalisierung fürs Clustering |
| `cluster.py` | IDF-gewichtete Jaccard-Ähnlichkeit + Containment-Kriterium + Union-Find |
| `rank.py` | Fünf-Komponenten-Scoring (Quellen-Tier, Cluster-Größe, Feed-Position, Aktualität, Thema) |
| `images.py` | Dreistufige Bildgarantie: Feed-Bild → `og:image` → generierte SVG-Kachel |
| `weather.py` | Open-Meteo, WMO-Code → Symbol |
| `markets.py` | ETFs/Aktien-Kennzahlen (siehe Abschnitt 8) |
| `store.py` | SQLite-Schema, FTS5-Suche, Status-Persistenz |
| `pipeline.py` | Verdrahtet alles zu `refresh()`/`rebuild()`/`build_board()` |
| `server.py` | JSON-API + statische Auslieferung für die lokale Live-Version |
| `export.py` | Statischer Export nach `docs/` für die Cloud-Version (kam später dazu, siehe Abschnitt 7) |

**Zwei echte Bugs wurden während des Baus gefunden und behoben, nicht nur
behauptet:**

1. Dieselbe Meldung stand oft in mehreren Feeds einer Quelle (z. B.
   Tagesschau `index` und `ausland`) mit unterschiedlichem Thema. "Letzter
   Feed gewinnt" machte das Ergebnis von der Abrufreihenfolge abhängig —
   `fetch` und `rebuild` kamen zu verschiedenen Boards. Behoben durch einen
   festen `feed_rank` aus der Konfiguration statt Verarbeitungsreihenfolge.
2. `strip_kicker()` zerschnitt echte Inhalte: aus "Waldbrände in Frankreich:
   110.000 evakuiert" wurde "110.000 evakuiert", wodurch die Meldung ihre
   Geschwister im Clustering nicht mehr fand. Behoben, indem nur noch
   Ein-bis-Zwei-Wort-Präfixe (echte Ressortkürzel) abgeschnitten werden.

Beide Fehler wurden durch einen echten Determinismus-Test aufgedeckt
(`fetch` zweimal gegen `rebuild` verglichen), nicht durch Code-Lesen.

## 4. Frontend

`web/index.html` + `web/app.css` + `web/app.js`, vanilla JS ohne Buildstep.
Maße, Farben, Typografie 1:1 aus `News-Board.dc.html` (1a) übernommen:
Fläche `#f0eee9`, Karte `#fff`, Akzent `#2f5d3a`, Mono `IBM Plex Mono`.
Wetterkarte und Themen-Pills aus 1b übernommen. Bild bei jedem Aufmacher
(16:10) und jeder Kurzmeldung (72×72), keine Nummerierung.

Im Browser (Claude-Browser-Pane) durchgeklickt und dabei zwei
Layout-Bugs gefunden und behoben:
- `[hidden]` wurde von einer späteren `display:flex`-Regel überschrieben →
  Suchansicht blieb sichtbar. Fix: `[hidden]{display:none!important}` an
  den Anfang des Stylesheets.
- Die Kurzmeldungen-Zeile (86px Bild + zwei 36px-Aktionsspalten) ließ zu
  wenig Platz für die Schlagzeile. Fix: Aktionsknöpfe in die Metazeile
  verschoben, Bild auf 72px verkleinert.

## 5. Tests

`tests/test_newstaker.py`, aktuell 61 Tests, keine Netzabhängigkeit im
Testlauf. Deckt unter anderem ab: Reproduzierbarkeit des Boards (fester
`now=`-Zeitpunkt, da die Aktualitätskomponente sich sonst zwischen zwei
Läufen legitim ändert), die live kalibrierten Cluster-Positivfälle, den
Negativfall "zwei unabhängige Trump-Meldungen dürfen nicht verschmelzen",
die Bildgarantie, Vollständigkeit des WMO-Codes, Umlaut-Suche, und (später
ergänzt) die Dividenden-/Historie-Filter der Marktübersicht.

Ein Satz Tests mit hartcodiertem Datum (`Sat, 25 Jul 2026`) fing an,
grundlos zu scheitern, als das reale Datum vier Tage weiterrückte (das
48-Stunden-Board-Fenster fiel aus dem Fixture-Zeitraum). Behoben, indem die
Feed-Fixtures ihr Datum relativ zur tatsächlichen Ausführungszeit erzeugen
statt es fest einzuprogrammieren.

## 6. Automatischer Abruf, lokal

`scripts/com.newstaker.fetch.plist` — launchd-Job, alle 30 Minuten,
`RunAtLoad`. Liv hat ihn selbst installiert (bestätigt über
`launchctl list` und den Zeitstempel in `var/fetch.log`).

## 7. Umstellung: Cloud-Aktualisierung

Liv fragte, ob sich die News auch aktualisieren, wenn der Mac schläft.
Nach Abwägung dreier Optionen (Mac wachhalten / eigener Server / GitHub
Actions) entschied sie sich für **GitHub Actions als Cron-Abruf**:

- `newstaker/export.py` — neues Modul, schreibt dieselbe deterministische
  Pipeline als statisches JSON (`docs/data/board.json`,
  `weather.json`, `markets.json`, `search.json`, `meta.json`) plus
  vorgerenderte SVG-Kacheln unter `docs/tiles/`. Prunet dabei alte Kacheln
  außerhalb des 7-Tage-Suchfensters, damit das Verzeichnis nicht über Monate
  unbegrenzt wächst.
- `docs/index.html` + `docs/app.css` + `docs/app.js` — funktional identische
  zweite Frontend-Variante, die statt API-Aufrufen die JSON-Dateien liest
  und Gelesen/Gemerkt in `localStorage` statt in einer Datenbank hält (**der
  bewusste Kompromiss:** Mac und iPhone zeigen auf der Cloud-Version nicht
  mehr denselben Status).
- `.github/workflows/update.yml` — Cron alle 30 Minuten + manueller Trigger
  + Trigger bei Code-Push, committet `docs/` zurück ins Repo, nur wenn sich
  etwas geändert hat.
- `requirements.txt` für den GitHub-Runner.

Beide Frontend-Varianten wurden im Browser gegeneinander geprüft (identisches
Bild, keine Konsolenfehler).

## 8. Marktübersicht (nachträgliche Anforderung)

Mitten im Bau kam ein neuer Wunsch: die "Themen des Tages"-Übersicht oben im
Board fand Liv unverständlich und wollte stattdessen eine kleine
Aktienübersicht — ETFs in einer Box, Einzelaktien in der anderen, mit Fokus
auf Wachstum, passend zu ihrem Anlagestil (langfristig, nicht-dividenden-
ausschüttend).

**Wichtige Einschränkung von mir aus, klar kommuniziert:** "vielversprechend
für die Zukunft" ist eine Prognose, die weder deterministisch berechenbar
noch etwas ist, das ich als Empfehlung aussprechen darf. Stattdessen: reine,
berechnete Kennzahlen aus echten Kursdaten (Tagespreis + Veränderung über
`MARKETS_LOOKBACK_YEARS`, aktuell 3 Jahre), **keine Bewertung, keine
Kaufempfehlung**.

- Datenquelle: die inoffizielle Yahoo-Finance-Chart-API (kein Key nötig,
  aber auch keine dokumentierte, garantierte Schnittstelle — ein
  `quoteSummary`-Endpunkt wurde zuerst versucht, verlangt inzwischen Auth
  (401) und wurde verworfen zugunsten des funktionierenden Chart-Endpunkts).
- **"Regelbasiert" heißt konkret:** `newstaker/markets.py` prüft bei jedem
  Abruf die tatsächliche Dividendenhistorie der letzten drei Jahre
  (`events=div`) gegen `config.CANDIDATE_ETFS`/`CANDIDATE_STOCKS` — zahlt
  ein Titel auch nur einmal Dividende, fliegt er automatisch raus. Live
  getestet: EQQQ, VFEM, ASML, BKNG, CRM und INTU wurden dadurch korrekt
  ausgeschlossen (sie zahlen inzwischen Dividende — reines Gedächtnis hätte
  das nicht zuverlässig erfasst, z. B. begannen Meta/Alphabet erst 2024
  damit).
- Ranking: je Box die `MARKETS_TOP_N` (5) mit der größten 3-Jahres-Kurs-
  steigerung unter den verbliebenen, tatsächlich dividendenfreien Titeln.
- Die alte Cluster-Strip-UI (HTML/CSS/JS) wurde in **beiden** Frontend-
  Varianten vollständig entfernt und durch die zwei Markt-Boxen ersetzt; die
  "+N Quellen"-Badges pro Artikel blieben erhalten, nur die eigenständige
  Themen-Übersicht ganz oben ist weg.

## 9. Git-Repository

Lokal initialisiert, ein Commit (`d38a86e`, 296 Dateien), Branch `main`,
Arbeitsverzeichnis sauber. **Kein Remote gesetzt, nichts gepusht** — auf
diesem Mac sind keine GitHub-Zugangsdaten hinterlegt (kein `gh`, keine
SSH-Keys, kein Keychain-Eintrag für github.com; geprüft, nicht vermutet).
Das ist der aktuelle Stillstandspunkt: Liv hat ein Repo unter dem Namen
`livanderson-sketch` (bestätigt als ihr GitHub-Nutzername) angelegt, aber
weder den genauen Repo-Namen noch Öffentlich/Privat mitgeteilt — die
öffentliche GitHub-API listet unter diesem Nutzernamen aktuell keine
öffentlichen Repos.

## 10. Was fehlt, um vollständig zu funktionieren

Zwei Kategorien: was nur Liv erledigen kann, und was ein bekanntes,
akzeptiertes Restrisiko ist.

**Nur von Liv (kein Zugang, keine Berechtigung, die ich umgehen dürfte):**

1. Exakten Repo-Namen und Sichtbarkeit (öffentlich/privat) mitteilen, oder
   direkt selbst pushen:
   ```
   git remote add origin https://github.com/livanderson-sketch/<repo-name>.git
   git branch -M main
   git push -u origin main
   ```
2. **Settings → Pages** → Branch `main`, Ordner `/docs` — sonst liefert
   GitHub nichts aus.
3. **Settings → Actions → General** → "Read and write permissions" — sonst
   darf der Cron-Job `docs/` nicht zurückschreiben, jeder Lauf schlägt beim
   Push-Schritt fehl.
4. Falls das Repo privat ist: entweder auf öffentlich stellen (GitHub Pages
   und Actions sind dann kostenlos) oder einen bezahlten GitHub-Plan nutzen.

**Bekannte Restrisiken (bewusst in Kauf genommen, im README dokumentiert):**

- Die Yahoo-Finance-Chart-API ist inoffiziell — fällt sie aus, bleibt
  einfach der letzte erfolgreiche Marktstand stehen, kein Absturz, aber
  auch keine Garantie.
- Kein Cluster-Merge über Sprachgrenzen (siehe Abschnitt 2) — bewusste
  Präzisionsentscheidung, keine technische Lücke.
- Auf der Cloud-Version ist Gelesen/Gemerkt pro Gerät (localStorage), nicht
  mehr geräteübergreifend synchron.
- GitHub deaktiviert geplante Workflows automatisch nach 60 Tagen
  Repo-Inaktivität — ein beliebiger Commit oder ein manueller Lauf über den
  Actions-Tab reaktiviert den Zeitplan.

## 11. Unabhängiger Audit — Ergebnis

Sechs parallele Prüfungen (Backend-Determinismus, Frontend-Parität,
CI/CD-Bereitschaft, Markt-Feature-Sicherheit, Secrets-Scan, Doku-Genauigkeit),
jede mit echten Kommandos gegen den tatsächlichen Code, nicht nur durch
Lesen. Ergebnis: zwei echte, bestätigte Bugs gefunden — beide inzwischen
behoben, getestet und live gegen die Produktionsdatenbank erneut verifiziert.

**Bug 1 (hoch): `run.py rebuild` hielt das Determinismus-Versprechen nicht
ein.** Drei reale CLI-Läufe hintereinander ergaben drei verschiedene
Board-Fingerabdrücke trotz identischer Rohdaten. Ursache lag an drei
Stellen zugleich: `cmd_rebuild()` rief `build_board()` ohne `now=` auf, und
selbst mit durchgereichtem `now=` verankerten `rebuild_clusters()` und
`images.backfill()` ihr jeweiliges Zeitfenster (`store.items_in_window()`,
`store.items_missing_image()`) weiterhin an einem eigenen, unabhängigen
`datetime.now()`. Schon 17 Sekunden Abstand zwischen zwei Läufen kippten die
Sortierreihenfolge (Recency-Score knapp beieinanderliegender Meldungen).

Der eigentliche Design-Fehler: `rebuild` reprozessiert ausschließlich
bereits gespeicherte Rohdaten (kein neuer Fetch) — der richtige
Bezugspunkt für "wie aktuell ist diese Meldung" ist deshalb der Zeitpunkt
des letzten tatsächlichen Abrufs (`last_fetch_at`), nicht der Moment, in
dem der Befehl zufällig getippt wird. Nach der Korrektur: vier echte
CLI-Läufe mit bis zu zehn Sekunden Pause dazwischen liefern denselben
Fingerabdruck. Mit einem Regressionstest verankert, der echte Zeit
zwischen zwei Aufrufen verstreichen lässt
(`test_cli_rebuild_ist_reproduzierbar`).

**Bug 2 (mittel): Marktübersicht löschte bei Totalausfall der Datenquelle
den letzten guten Stand.** `markets.refresh()` rief bei komplettem
Fehlschlag aller Kandidaten (z. B. Yahoo-Finance-API blockiert/down)
`store.save_markets(conn, [], [])` auf — ein unbedingtes DELETE+INSERT, das
den zuletzt erfolgreichen Marktstand ersatzlos löschte, obwohl keine neuen
Daten da waren. Widersprach der eigenen Dokumentation im Modul
("bleibt einfach der letzte erfolgreiche Stand stehen"). Behoben: bei
Totalausfall bleibt der alte Stand jetzt unangetastet, mit
Regressionstest (`test_markets_totalausfall_erhaelt_alten_stand`).

**Zusätzlich gehärtet (niedrig, kein bestätigter Fehler, aber
Verteidigung in der Tiefe):** IDF-Gewichtssummen im Clustering iterierten
über `frozenset`, dessen Reihenfolge theoretisch vom randomisierten
`PYTHONHASHSEED` abhängt. Empirisch an sechs verschiedenen Seeds gegen den
echten 2265-Meldungen-Datenbestand getestet — bit-identisches Ergebnis in
allen Fällen — aber jetzt zusätzlich mit `sorted()` abgesichert, passend zur
übrigen Sortierdisziplin in `cluster.py`.

**Als Fehlalarm geprüft und verworfen:** der Secrets-Scan fand ausschließlich
Wörter wie „secretary"/„tokenomics" aus echten Nachrichtentexten sowie
Code-Kommentare, die ausdrücklich bestätigen, dass **kein** API-Key nötig
ist — kein einziger echter Zugangsdaten-Fund in der gesamten Git-Historie.

**Menschliche Entscheidung, nicht automatisch korrigiert:**
`scripts/com.newstaker.fetch.plist` enthält absolute Pfade mit Livs echtem
macOS-Benutzernamen — kein Passwort, aber jetzt in einem öffentlichen Repo
sichtbar. launchd kennt kein `PATH` und keine Tilde-Expansion, ein absoluter
Pfad ist dafür technisch notwendig; ob das so bleiben soll oder die Datei aus
dem öffentlichen Repo ausgeschlossen wird, ist Livs Entscheidung.

**Dokumentationslücken behoben:** Der Dateibaum im README-Abschnitt „Aufbau"
listete `newstaker/pipeline.py` (das zentrale Orchestrierungsmodul) und den
Ordner `scripts/` nicht — beide ergänzt.

Alle Fixes sind von 63 Tests abgedeckt (vorher 61 — zwei neue
Regressionstests für die beiden gefundenen Bugs), alle grün.

## 12. Veröffentlichung

Repo gepusht nach `https://github.com/livanderson-sketch/newstaker`
(öffentlich, bestätigt über die GitHub-API — alle 297 Dateien angekommen).
GitHub Actions hat direkt nach dem Push automatisch zu laufen begonnen; ein
"pages build and deployment"-Lauf war zum Zeitpunkt dieses Berichts bereits
erfolgreich durchgelaufen, die Live-Seite unter
`https://livanderson-sketch.github.io/newstaker/` antwortet mit HTTP 200.
