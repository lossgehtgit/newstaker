# News-Taker

Persönlicher Nachrichtenüberblick: einmal am Tag draufschauen und sehen, was in
der Welt, in der Wirtschaft und in der Wissenschaft passiert ist — plus Wetter.

**Deterministisch, kein KI-Agent.** Kein Modell fasst zusammen, sortiert oder
übersetzt. Dieselben Feeds ergeben dasselbe Board — das ist als Test verankert
(`run.py rebuild` zweimal auf demselben Stand muss denselben Fingerabdruck
liefern).

Das Frontend setzt den Entwurf **1a (Raster)** aus `News-Board.dc.html` um, mit
den gewünschten Elementen aus **1b**: Wetterkarte und Themen-Pills. Ohne
Nummerierung vor den Meldungen, dafür mit Bild bei jeder Schlagzeile. Oben im
Board steht statt einer Cluster-Übersicht eine **Marktübersicht** (ETFs und
Einzelaktien, siehe unten) — die ursprüngliche Themen-des-Tages-Ansicht wurde
auf Livs Wunsch ersetzt, weil sie ihr beim ersten Blick aufs Board nicht
geholfen hat.

---

## Loslegen

```bash
python3 run.py init && python3 run.py fetch -v && python3 run.py serve
```

Board am Mac unter <http://localhost:8787>. Am iPhone über die lokale IP im
selben WLAN — `run.py serve` zeigt sie beim Start an.

Es wird **nichts installiert**: Python 3, `requests` und SQLite reichen, alles
davon ist auf dem Rechner vorhanden. Kein Node, kein Buildstep.

### Befehle

| Befehl | Wirkung |
|---|---|
| `run.py init` | Datenbank anlegen |
| `run.py fetch -v` | Feeds abrufen, Bilder, Cluster, Wetter — mit Tabelle je Feed |
| `run.py serve` | Board ausliefern |
| `run.py rebuild` | Neu berechnen aus gespeicherten Rohantworten, **ohne Netz** |
| `run.py export -v` | Abrufen + statischen Export nach `docs/` schreiben (für GitHub Pages) |
| `run.py status` | Zustandsbericht, zeigt auch stumme Feeds |

### Automatischer Abruf

Die fertige `.plist` liegt bewusst **nicht** im Repo — sie enthält absolute
lokale Pfade inklusive Benutzername, und das Repo ist öffentlich. Stattdessen
aus der Vorlage `scripts/com.newstaker.fetch.plist.template` mit den eigenen
Pfaden erzeugen (Platzhalter `__PYTHON_BIN__`/`__PROJECT_DIR__`):

```bash
PROJECT_DIR="$(pwd)"
PYTHON_BIN="$(python3 -c 'import sys; print(sys.executable)')"
sed -e "s|__PYTHON_BIN__|$PYTHON_BIN|g" -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
  scripts/com.newstaker.fetch.plist.template > ~/Library/LaunchAgents/com.newstaker.fetch.plist
launchctl load ~/Library/LaunchAgents/com.newstaker.fetch.plist
```

Holt ab dann alle 30 Minuten die Feeds. Protokoll in `var/fetch.log`.
Wieder abschalten:

```bash
launchctl unload ~/Library/LaunchAgents/com.newstaker.fetch.plist
```

---

## Zwei Betriebsarten

**1. Lokal, live** (`web/`) — Python-Server auf dem Mac, Board unter
`localhost:8787`. Gelesen/Gemerkt liegt serverseitig, Mac und iPhone zeigen
denselben Stand. Läuft nur, während der Mac wach ist.

**2. Cloud, statisch** (`docs/`) — für den Fall, dass die News auch aktuell
sein sollen, wenn der Mac schläft. Ein GitHub-Actions-Workflow
(`.github/workflows/update.yml`) holt alle 30 Minuten frische Feeds auf einem
GitHub-Runner (der nie schläft), berechnet dieselbe deterministische Pipeline
wie lokal und schreibt das Ergebnis als statisches JSON nach `docs/`. GitHub
Pages liefert das von dort aus — keine eigene Serverinfrastruktur, keine
Kosten (GitHub Pages und Actions sind für öffentliche Repos kostenlos).

Der Preis dafür: eine statische Seite kann nichts speichern. Gelesen/Gemerkt
liegt deshalb in dieser Variante in `localStorage` **je Gerät** — Mac und
iPhone zeigen nicht mehr denselben Stand. Alles andere (Board, Wetter,
Marktübersicht, Suche) ist identisch zur lokalen Version.

Export von Hand anstoßen (z. B. um `docs/` vor einem Push zu prüfen):

```bash
python3 run.py export -v
```

### Einrichtung auf GitHub (einmalig, von Dir)

Auf diesem Rechner sind keine GitHub-Zugangsdaten hinterlegt — das Erstellen
des Repos und der erste Push müssen deshalb von Dir kommen. Danach läuft
alles von selbst.

```bash
cd ~/Desktop/Projekte/Newsfolder
git init
git add -A
git commit -m "News-Taker: erster Commit"
```

Dann auf [github.com/new](https://github.com/new) ein **öffentliches** Repo
anlegen (öffentlich, damit GitHub Pages und Actions kostenlos bleiben — bei
einem privaten Repo braucht Pages ein bezahltes Konto), ohne README/.gitignore
(die gibt es schon), und den angezeigten Anweisungen für ein „vorhandenes
Repository pushen" folgen, etwa:

```bash
git remote add origin https://github.com/<dein-nutzername>/<repo-name>.git
git branch -M main
git push -u origin main
```

Danach in den Repo-Einstellungen:

- **Settings → Pages** → „Deploy from a branch" → Branch `main`, Ordner
  `/docs` → Save. Die URL erscheint dort nach kurzer Zeit.
- **Settings → Actions → General** → „Workflow permissions" auf
  „Read and write permissions" stellen (nötig, damit der Workflow `docs/`
  zurückpushen darf).

Ab dem nächsten Push (oder manuell über den Tab **Actions** → „News abrufen
und veröffentlichen" → „Run workflow") läuft der 30-Minuten-Takt von selbst.

**Bekannter Vorbehalt bei geplanten Workflows:** Bleibt das Repo 60 Tage ohne
jede Aktivität, deaktiviert GitHub den Zeitplan automatisch. Ein beliebiger
Commit oder ein manueller Lauf über den Actions-Tab reaktiviert ihn.

---

## Quellen

21 Häuser, 47 Feeds — alle beim Bau live geprüft. Pflichtquellen laut Vorgabe:
**Handelsblatt, Tagesschau, Spiegel**.

- **Deutschland:** Handelsblatt, Tagesschau, Spiegel, FAZ, ZEIT, SZ, heise
- **International:** BBC, New York Times, Guardian, Financial Times,
  Wall Street Journal, Al Jazeera, NPR, The Economist, CNBC
- **Wissenschaft:** Nature, Science, Quanta, Phys.org, Ars Technica

**Reuters und AP fehlen als Direktquellen** — beide haben ihre öffentlichen
RSS-Feeds abgeschaltet (geprüft: 404 bzw. 401). Ihr Material kommt trotzdem an,
weil Tagesschau, Handelsblatt und FAZ es weiterverbreiten; die Agentur wird
erkannt und in der Metazeile mitgeführt.

Quellen ändern: `newstaker/config.py`, Liste `SOURCES`. Jeder Feed trägt sein
Thema; `tier` (1–3) geht als Gewicht ins Ranking ein, nicht als Filter.

---

## Wie das Board entsteht

1. **Abruf** — conditional GET über ETag/Last-Modified, sonst Vergleich des
   Inhalts-Hashs. Rohantworten landen in der Datenbank, damit jeder Board-Stand
   ohne Netz rekonstruierbar ist.
2. **Einlesen** — RSS 2.0, Atom und RSS 1.0/RDF (Nature, Science). Kanonische
   URL ohne Tracking-Parameter ist die Identität einer Meldung.
3. **Clustern** — IDF-gewichtete Jaccard-Ähnlichkeit über die Wörter der
   Schlagzeile, Single-Linkage per Union-Find. Ergänzend ein
   Containment-Kriterium für den Fall, dass eine Redaktion ausführlicher
   titelt als die andere.
4. **Ranken** — fünf sichtbare Komponenten, Gewichte in `config.RANK_WEIGHTS`:
   Quellen-Tier, Anzahl unabhängiger Quellen, Platzierung im Feed
   (das redaktionelle Urteil der Quelle), Aktualität, Themen-Boost.
5. **Bilder** — dreistufig, damit bei *jeder* Schlagzeile eines steht:
   Feed-Bild → `og:image` der Artikelseite → deterministisch erzeugte
   SVG-Kachel. Die Kachel greift immer und braucht kein Netz.

### Kalibrierung des Clusterings

Die Schwelle **0.34** stammt aus einem Abgleich an 484 echten Meldungen aus
sieben deutschen Quellen: 0.28 wurde unscharf, 0.42 zu streng (maximal zwei
Quellen je Cluster). Bei 0.34 entstanden ausschließlich korrekte Gruppen.

Im aktuellen Bestand ergibt das 25 Mehr-Quellen-Cluster, jedes davon geprüft —
etwa die Waldbrände in Frankreich und Spanien über vier deutsche Quellen oder
die indischen Proteste über sechs internationale.

### Bewusste Einschränkung: keine Cluster über Sprachgrenzen

Deutsche und englische Meldungen zum selben Ereignis werden **nicht**
zusammengefasst. Ein Verfahren über gemeinsame Eigennamen wurde an 302
deutschen und 247 englischen Meldungen getestet: 7 Kandidaten, davon nur 2
korrekt. Der Rest waren Namenskoinzidenzen — „Donald Trump" taucht an einem
Tag in mehreren unabhängigen Geschichten auf. Jede Verschärfung, die die
Fehltreffer beseitigt, beseitigt auch die Treffer.

Ein falsch verschmolzener Cluster ist in einem Nachrichtentool teurer als ein
fehlender. Die Waldbrände erscheinen deshalb als deutscher und als englischer
Cluster nebeneinander.

---

## Bedienung

- **Marktübersicht** (oben): ETFs und Einzelaktien, siehe eigener Abschnitt
  unten.
- **Pills**: Alle · Welt · Politik · Wirtschaft · Technologie · Wissenschaft.
- **☆** merkt eine Meldung, **○ / ✓** markiert sie als gelesen. Auf der
  lokalen Live-Version liegt das serverseitig (Mac und iPhone zeigen denselben
  Stand); auf der statischen Cloud-Version (GitHub Pages) liegt es in
  localStorage je Gerät, siehe „Zwei Betriebsarten" unten.
- **MEHR** klappt den Teaser auf; bei Clustern erscheinen dort die übrigen
  Quellen als anklickbare Kürzel — der „+N QUELLEN"-Hinweis bei mehrfach
  bestätigten Meldungen bleibt erhalten, nur die frühere Themen-Übersicht ganz
  oben ist durch die Marktübersicht ersetzt.
- **SUCHE** (Fußzeile): Volltext über alle archivierten Meldungen, dazu der
  Umschalter „☆ Gemerkte". Umlaute sind egal — „Zölle" und „zoelle" finden
  dasselbe.

---

## Marktübersicht

Zwei Boxen oben im Board: **ETFs** und **Einzelaktien**, je Titel Tagespreis
und Kursveränderung über `MARKETS_LOOKBACK_YEARS` (3 Jahre). Das ist bewusst
**keine Anlageempfehlung und keine Prognose** — nur berechnete Kennzahlen aus
echten Kursdaten, passend zu Livs Anlagestil (langfristiger Vermögensaufbau
über nicht-dividendenzahlende Titel).

**„Regelbasiert" heißt konkret:** `config.CANDIDATE_ETFS`/`CANDIDATE_STOCKS`
sind eine feste Kandidatenliste. Bei jedem Abruf prüft `markets.py` für jeden
Titel die tatsächliche Dividendenhistorie der letzten 3 Jahre (Yahoo-Finance-
Chart-API, `events=div`) — zahlt ein Titel auch nur einmal Dividende, fliegt
er automatisch raus. Das ist kein einmalig behaupteter Fakt, sondern wird bei
jedem Lauf neu geprüft: Firmen ändern ihre Ausschüttungspolitik (Meta und
Alphabet etwa begannen 2024 damit). Aus den verbleibenden, tatsächlich
dividendenfreien Titeln zeigt jede Box die `MARKETS_TOP_N` (5) mit der
größten 3-Jahres-Kurssteigerung.

Die Kandidatenlisten wurden beim Bau einzeln live geprüft (Kursverlauf
vorhanden, keine Dividende in 3 Jahren). Ausgeschlossen wurden dabei u. a.
EQQQ, VFEM, ASML, BKNG, CRM und INTU — die zahlen inzwischen Dividende.

**Datenquelle:** die inoffizielle Yahoo-Finance-Chart-API (kein API-Key, aber
auch keine dokumentierte, garantierte Schnittstelle). Fällt sie aus, bleibt
einfach der letzte erfolgreiche Stand aus der Datenbank stehen — die
Aktualisierung läuft mit einer TTL von `MARKETS_TTL_MINUTES` (12 Std.), da
sich eine 3-Jahres-Kennzahl im 30-Minuten-Takt ohnehin nicht sichtbar ändert.

Eigene Watchlist statt Kandidatenliste: Liste einfach in
`newstaker/config.py` unter `CANDIDATE_ETFS`/`CANDIDATE_STOCKS` anpassen —
die Dividendenprüfung und das Ranking laufen automatisch über jede neue Liste.

---

## Tests

```bash
python3 -m unittest discover -s tests -v
```

63 Tests, ohne Netzzugriff. Abgedeckt sind unter anderem: Reproduzierbarkeit
des Boards, die geprüften Cluster-Positivfälle, der Negativfall „zwei
unabhängige Trump-Meldungen dürfen nicht verschmelzen", die Bildgarantie,
Vollständigkeit des WMO-Wettercode-Mappings, die Umlaut-Suche, die
Dividenden-/Historie-Filter der Marktübersicht, sowie zwei von einem
unabhängigen Audit gefundene Determinismus-Bugs (siehe unten).

**Zur Reproduzierbarkeit:** Die Aktualitätskomponente des Rankings hängt an
der Uhrzeit — das ist beabsichtigt, frische Meldungen sollen steigen. `run.py
rebuild` reprozessiert ausschließlich bereits gespeicherte Rohdaten (kein
neuer Fetch) und verankert diese Uhrzeit deshalb am Zeitpunkt des letzten
tatsächlichen Abrufs (`last_fetch_at`), nicht am Moment, in dem der Befehl
zufällig getippt wird — sonst kippt allein durch ein paar Sekunden Abstand
zwischen zwei Aufrufen die Sortierreihenfolge knapp beieinanderliegender
Meldungen. Damit gilt das Versprechen unbedingt: `python3 run.py rebuild`
liefert bei beliebig vielen Durchläufen denselben Fingerabdruck, egal wie
viel reale Zeit dazwischen liegt — verifiziert mit echten CLI-Aufrufen und
zehn Sekunden Pause dazwischen, nicht nur in der Testumgebung.

Dieser genaue Mechanismus wurde nachträglich korrigiert: ein unabhängiger
Audit fand, dass die ursprüngliche Implementierung bei jedem Aufruf die
reale Wanduhrzeit heranzog (in drei verschiedenen Funktionen: dem
CLI-Befehl selbst, dem Cluster-Zeitfenster und der Bild-Backfill-Auswahl) —
drei reale Läufe ergaben drei verschiedene Fingerabdrücke trotz identischer
Rohdaten. Behoben und mit einem Regressionstest verankert, der echte Zeit
zwischen zwei CLI-Aufrufen verstreichen lässt
(`test_cli_rebuild_ist_reproduzierbar`).

---

## Aufbau

```
run.py                CLI: init | fetch | serve | rebuild | export | status
newstaker/
  config.py           Quellen, Themen, Gewichte, Schwellen, Marktkandidaten — alles an einer Stelle
  fetch.py            HTTP (requests + certifi, s. u.), conditional GET, Höflichkeitspause
  feedparse.py        RSS 2.0 / Atom / RSS 1.0, Bildextraktion
  normalize.py        Kanonische URL, Kicker-Strip, Faltung, Endungen, Themen
  cluster.py          IDF-Jaccard + Containment + Union-Find
  rank.py             Scoring, jede Komponente einzeln nachvollziehbar
  images.py           Dreistufige Bildbeschaffung inkl. SVG-Kachel
  weather.py          Open-Meteo, WMO-Code → Symbol
  markets.py          ETFs/Aktien: Yahoo-Chart-API, automatische Dividendenprüfung, Ranking
  store.py            SQLite-Schema, FTS5, Status
  pipeline.py         Verdrahtet alles zu refresh() | rebuild() | build_board()
  server.py           JSON-API + statische Auslieferung (lokale Live-Version)
  export.py           Statischer Export nach docs/ (Cloud-Version)
web/                  Frontend, Live-Version (kein Buildstep)
docs/                 Frontend, statische Cloud-Version + generierte Daten (data/, tiles/)
.github/workflows/    update.yml — der 30-Minuten-Cron-Abruf
scripts/              com.newstaker.fetch.plist.template — Vorlage für den lokalen launchd-Auto-Abruf
var/                  Datenbank und Protokolle (nicht im Repo)
```

### Eine Falle dieser Maschine

`urllib.request` scheitert hier an `CERTIFICATE_VERIFY_FAILED`: die
python.org-Installation hat kein CA-Bundle verdrahtet. `requests` bringt
certifi mit und funktioniert. Der Abruf geht deshalb konsequent über
`requests` — wer das umbaut, muss `ssl.create_default_context(cafile=certifi.where())`
mitgeben, sonst lädt kein einziger Feed.

---

## Was bewusst fehlt

- Keine Zusammenfassungen — angezeigt wird ausschließlich der Teaser aus dem
  Feed.
- Keine Übersetzung. Englische Schlagzeilen bleiben englisch.
- Keine Artikelanzeige in der App; ein Tipp auf die Schlagzeile öffnet die
  Quelle.
- Bilder werden nur verlinkt, nicht gespiegelt.
- Die Marktübersicht ist keine Anlageberatung und keine Kaufempfehlung —
  reine berechnete Kennzahlen aus historischen Kursdaten. Welche Titel
  überhaupt in der Kandidatenliste stehen, hat kein Modell ausgewählt,
  sondern wurde beim Bau von Hand zusammengestellt (siehe Abschnitt
  „Marktübersicht").
- Auf der statischen Cloud-Version (`docs/`, GitHub Pages) ist Gelesen/Gemerkt
  nicht mehr zwischen Mac und iPhone synchron — jedes Gerät führt seinen
  eigenen Stand in localStorage. Das ist der bewusste Kompromiss dafür, dass
  die News auch bei schlafendem Mac aktuell bleiben.
