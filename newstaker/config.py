"""Zentrale Konfiguration.

Alles, was das Verhalten des Boards steuert, steht hier sichtbar: Quellen,
Themen, Gewichte, Schwellen. Keine versteckten Konstanten in den Modulen.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------- Pfade

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
VAR_DIR = ROOT / "var"
DB_PATH = VAR_DIR / "news.db"
DATA_DIR = Path(__file__).resolve().parent / "data"

# ---------------------------------------------------------------- Server

HOST = os.environ.get("NEWSTAKER_HOST", "0.0.0.0")
PORT = int(os.environ.get("NEWSTAKER_PORT", "8787"))

# ---------------------------------------------------------------- Themen
#
# Die Pills im Board. "Alle" ist kein Topic, sondern der Aus-Zustand des Filters.

TOPICS = ["welt", "politik", "wirtschaft", "technologie", "wissenschaft"]

TOPIC_LABELS = {
    "welt": "Welt",
    "politik": "Politik",
    "wirtschaft": "Wirtschaft",
    "technologie": "Technologie",
    "wissenschaft": "Wissenschaft",
}

# ---------------------------------------------------------------- Quellen
#
# tier: 1 = Kernquelle (explizit gefordert bzw. gleichwertig),
#       2 = starke Ergänzung, 3 = Spezial-/Fachquelle.
# Das Tier geht als Gewicht ins Ranking ein, nicht als Filter.
#
# lang steuert das Clustering: gemerged wird ausschliesslich innerhalb einer
# Sprache. Begruendung siehe README (Cross-Language-Test mit 302 DE + 247 EN
# Meldungen ergab 7 Kandidaten, davon nur 2 korrekt).
#
# Jeder Feed traegt sein eigenes Topic. Feeds ohne thematischen Zuschnitt
# ("Schlagzeilen") bekommen ein Default-Topic und werden zusaetzlich ueber die
# Kategorien des Feeds nachjustiert (siehe normalize.topic_for_item).

SOURCES = [
    # ---- Kernquellen Deutschland (explizit gefordert) ----
    {
        "key": "handelsblatt",
        "name": "Handelsblatt",
        "tier": 1,
        "lang": "de",
        "home": "https://www.handelsblatt.com",
        "feeds": [
            ("https://www.handelsblatt.com/contentexport/feed/schlagzeilen", "wirtschaft"),
            ("https://www.handelsblatt.com/contentexport/feed/wirtschaft", "wirtschaft"),
            ("https://www.handelsblatt.com/contentexport/feed/finanzen", "wirtschaft"),
            ("https://www.handelsblatt.com/contentexport/feed/unternehmen", "wirtschaft"),
            ("https://www.handelsblatt.com/contentexport/feed/politik", "politik"),
            ("https://www.handelsblatt.com/contentexport/feed/technologie", "technologie"),
        ],
    },
    {
        "key": "tagesschau",
        "name": "Tagesschau",
        "tier": 1,
        "lang": "de",
        "home": "https://www.tagesschau.de",
        "feeds": [
            ("https://www.tagesschau.de/index~rss2.xml", "politik"),
            ("https://www.tagesschau.de/wirtschaft/index~rss2.xml", "wirtschaft"),
            ("https://www.tagesschau.de/ausland/index~rss2.xml", "welt"),
            ("https://www.tagesschau.de/inland/index~rss2.xml", "politik"),
            ("https://www.tagesschau.de/wissen/index~rss2.xml", "wissenschaft"),
        ],
    },
    {
        "key": "spiegel",
        "name": "Spiegel",
        "tier": 1,
        "lang": "de",
        "home": "https://www.spiegel.de",
        "feeds": [
            ("https://www.spiegel.de/schlagzeilen/tops/index.rss", "politik"),
            ("https://www.spiegel.de/wirtschaft/index.rss", "wirtschaft"),
            ("https://www.spiegel.de/wissenschaft/index.rss", "wissenschaft"),
            ("https://www.spiegel.de/ausland/index.rss", "welt"),
            ("https://www.spiegel.de/netzwelt/index.rss", "technologie"),
        ],
    },
    # ---- Weitere deutsche Qualitaetsquellen ----
    {
        "key": "faz",
        "name": "FAZ",
        "tier": 2,
        "lang": "de",
        "home": "https://www.faz.net",
        "feeds": [
            ("https://www.faz.net/rss/aktuell/", "politik"),
            ("https://www.faz.net/rss/aktuell/wirtschaft/", "wirtschaft"),
            ("https://www.faz.net/rss/aktuell/politik/", "politik"),
            ("https://www.faz.net/rss/aktuell/wissen/", "wissenschaft"),
        ],
    },
    {
        "key": "zeit",
        "name": "ZEIT",
        "tier": 2,
        "lang": "de",
        "home": "https://www.zeit.de",
        "feeds": [("https://newsfeed.zeit.de/index", "politik")],
    },
    {
        "key": "sz",
        "name": "SZ",
        "tier": 2,
        "lang": "de",
        "home": "https://www.sueddeutsche.de",
        "feeds": [("https://rss.sueddeutsche.de/rss/Topthemen", "politik")],
    },
    {
        "key": "heise",
        "name": "heise",
        "tier": 3,
        "lang": "de",
        "home": "https://www.heise.de",
        "feeds": [("https://www.heise.de/rss/heise-atom.xml", "technologie")],
    },
    # ---- International ----
    {
        "key": "bbc",
        "name": "BBC",
        "tier": 1,
        "lang": "en",
        "home": "https://www.bbc.com/news",
        "feeds": [
            ("https://feeds.bbci.co.uk/news/world/rss.xml", "welt"),
            ("https://feeds.bbci.co.uk/news/business/rss.xml", "wirtschaft"),
            ("https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "wissenschaft"),
            ("https://feeds.bbci.co.uk/news/technology/rss.xml", "technologie"),
        ],
    },
    {
        "key": "guardian",
        "name": "Guardian",
        "tier": 2,
        "lang": "en",
        "home": "https://www.theguardian.com",
        "feeds": [
            ("https://www.theguardian.com/world/rss", "welt"),
            ("https://www.theguardian.com/business/rss", "wirtschaft"),
            ("https://www.theguardian.com/science/rss", "wissenschaft"),
        ],
    },
    {
        "key": "nyt",
        "name": "New York Times",
        "tier": 1,
        "lang": "en",
        "home": "https://www.nytimes.com",
        "feeds": [
            ("https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "welt"),
            ("https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "wirtschaft"),
            ("https://rss.nytimes.com/services/xml/rss/nyt/Science.xml", "wissenschaft"),
            ("https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "technologie"),
        ],
    },
    {
        "key": "wsj",
        "name": "Wall Street Journal",
        "tier": 2,
        "lang": "en",
        "home": "https://www.wsj.com",
        # Artikelseiten antworten mit 401 -> og:image-Stufe wird uebersprungen.
        "no_og_scrape": True,
        "feeds": [
            ("https://feeds.a.dj.com/rss/RSSWorldNews.xml", "welt"),
            ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "wirtschaft"),
        ],
    },
    {
        "key": "ft",
        "name": "Financial Times",
        "tier": 1,
        "lang": "en",
        "home": "https://www.ft.com",
        "feeds": [("https://www.ft.com/rss/home", "wirtschaft")],
    },
    {
        "key": "aljazeera",
        "name": "Al Jazeera",
        "tier": 2,
        "lang": "en",
        "home": "https://www.aljazeera.com",
        "feeds": [("https://www.aljazeera.com/xml/rss/all.xml", "welt")],
    },
    {
        "key": "npr",
        "name": "NPR",
        "tier": 2,
        "lang": "en",
        "home": "https://www.npr.org",
        "feeds": [("https://feeds.npr.org/1004/rss.xml", "welt")],
    },
    {
        "key": "economist",
        "name": "The Economist",
        "tier": 1,
        "lang": "en",
        "home": "https://www.economist.com",
        # Artikelseiten antworten mit 403.
        "no_og_scrape": True,
        "feeds": [
            ("https://www.economist.com/finance-and-economics/rss.xml", "wirtschaft"),
            ("https://www.economist.com/science-and-technology/rss.xml", "wissenschaft"),
        ],
    },
    {
        "key": "cnbc",
        "name": "CNBC",
        "tier": 3,
        "lang": "en",
        "home": "https://www.cnbc.com",
        "feeds": [("https://www.cnbc.com/id/100003114/device/rss/rss.html", "wirtschaft")],
    },
    # ---- Wissenschaft ----
    {
        "key": "nature",
        "name": "Nature",
        "tier": 1,
        "lang": "en",
        "home": "https://www.nature.com",
        # Kein Bild im Feed, aber og:image auf der Artikelseite (2 von 3 im Test).
        "feeds": [("https://www.nature.com/nature.rss", "wissenschaft")],
    },
    {
        "key": "science",
        "name": "Science",
        "tier": 1,
        "lang": "en",
        "home": "https://www.science.org",
        "no_og_scrape": True,
        "feeds": [("https://www.science.org/rss/news_current.xml", "wissenschaft")],
    },
    {
        "key": "quanta",
        "name": "Quanta Magazine",
        "tier": 2,
        "lang": "en",
        "home": "https://www.quantamagazine.org",
        "feeds": [("https://www.quantamagazine.org/feed/", "wissenschaft")],
    },
    {
        "key": "physorg",
        "name": "Phys.org",
        "tier": 3,
        "lang": "en",
        "home": "https://phys.org",
        "feeds": [("https://phys.org/rss-feed/", "wissenschaft")],
    },
    {
        "key": "arstechnica",
        "name": "Ars Technica",
        "tier": 3,
        "lang": "en",
        "home": "https://arstechnica.com",
        "feeds": [("https://arstechnica.com/feed/", "technologie")],
    },
]

# ---------------------------------------------------------------- Clustering
#
# Schwellen aus dem Prototyp gegen 484 echte Meldungen kalibriert:
#   0.28 -> beginnende Unschaerfe, 0.34 -> 10 saubere Cluster ohne Fehltreffer,
#   0.42 -> zu streng (max. 2 Quellen je Cluster).

CLUSTER_THRESHOLD = 0.34
# Dieselbe Meldung taucht bei einer Quelle oft in mehreren Feeds auf. Innerhalb
# einer Quelle darf daher aggressiver zusammengefasst werden.
CLUSTER_THRESHOLD_SAME_SOURCE = 0.55
# Zeitfenster, innerhalb dessen zwei Meldungen ueberhaupt verglichen werden.
CLUSTER_WINDOW_HOURS = 36
# Unter dieser Zahl an Inhaltstoken ist ein Titel zu duenn fuer einen Vergleich.
CLUSTER_MIN_TOKENS = 3

# Zweiter Weg zur Zusammenfassung, fuer den Fall, dass eine Redaktion deutlich
# ausfuehrlicher titelt als die andere. Dann zaehlt nicht die Jaccard-Schwelle,
# sondern wie vollstaendig der kuerzere Titel im laengeren aufgeht. Alle drei
# Bedingungen muessen gleichzeitig erfuellt sein.
CLUSTER_CONTAINMENT = 0.62      # Anteil des kleineren Titels
CLUSTER_MIN_SHARED = 3          # geteilte Inhaltswoerter
CLUSTER_THRESHOLD_FLOOR = 0.26  # Jaccard darf trotzdem nicht beliebig tief sein

# ---------------------------------------------------------------- Ranking
#
# score = Summe der gewichteten Komponenten. Jede Komponente ist auf 0..1
# normiert, damit die Gewichte direkt vergleichbar bleiben.

RANK_WEIGHTS = {
    "source": 1.0,      # Tier der Quelle
    "cluster": 1.6,     # Anzahl distinkter Quellen, die die Story bringen
    "position": 0.8,    # Platzierung im Feed = redaktionelles Urteil der Quelle
    "recency": 1.2,     # Halbwertszeit
    "topic": 0.4,       # Themen-Boost
}
RECENCY_HALFLIFE_HOURS = 6.0
# Erklaerter Fokus: Welt, Wirtschaft, Wissenschaft.
TOPIC_BOOST = {
    "welt": 1.0,
    "wirtschaft": 1.0,
    "wissenschaft": 1.0,
    "politik": 0.7,
    "technologie": 0.6,
}

# Wie viele Meldungen das Board maximal zeigt und wie viele davon Aufmacher sind.
LEAD_COUNT = 3
BOARD_LIMIT = 120
CLUSTER_STRIP_LIMIT = 8

# ---------------------------------------------------------------- Abruf

USER_AGENT = "NewsTaker/1.0 (persoenlicher Feedreader; +http://localhost)"
FETCH_TIMEOUT = 15
FETCH_RETRIES = 2
FETCH_BACKOFF_SECONDS = 1.5
# Hoeflichkeit: Mindestabstand zwischen zwei Anfragen an denselben Host.
HOST_DELAY_SECONDS = 1.0
# Rohantworten aelter als das werden beim Aufraeumen verworfen.
RAW_RETENTION_DAYS = 7
# Meldungen aelter als das erscheinen nicht mehr auf dem Board (bleiben aber
# in der Datenbank und damit in der Suche).
BOARD_MAX_AGE_HOURS = 48

# ---------------------------------------------------------------- Wetter

CITIES = {
    "München": {"lat": 48.1374, "lon": 11.5755},
    "Reutlingen": {"lat": 48.4914, "lon": 9.2043},
}
DEFAULT_CITY = "München"
WEATHER_DAYS = 3
WEATHER_TTL_MINUTES = 60
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TIMEZONE = "Europe/Berlin"

# ---------------------------------------------------------------- Maerkte
#
# Ersetzt die urspruengliche "Themen des Tages"-Uebersicht oben im Board
# (als unverstaendlich und wenig hilfreich empfunden). Gezeigt werden Titel
# ohne Dividendenausschuettung mit Wachstumsfokus - reine berechnete
# Kennzahlen (Tagespreis, Veraenderung ueber 3 Jahre), keine
# KI-Einschaetzung und keine Anlageempfehlung. "Regelbasierte Rangliste"
# heisst: aus der Kandidatenliste unten werden automatisch nur die Titel
# angezeigt, die tatsaechlich keine Dividende ausgeschuettet haben (per
# Yahoo-Finance-Dividendenhistorie ueber MARKETS_LOOKBACK_YEARS gegengeprueft,
# nicht aus dem Gedaechtnis behauptet - Firmen aendern ihre Ausschuettungspolitik,
# siehe Meta/Alphabet, die 2024 begannen). Ranking innerhalb jeder Box: nach
# 3-Jahres-Veraenderung absteigend, streng deterministisch.
#
# Kandidatenlisten wurden beim Bau einzeln live gegen die Yahoo-Chart-API
# verifiziert (Kursverlauf vorhanden, keine Dividendenzahlung in 3 Jahren).
# Ausgeschlossen wurden dabei u.a. EQQQ, VFEM, ASML, BKNG, CRM, INTU - die
# zahlen inzwischen Dividende.

# ---------------------------------------------------------------- Morning Brief
#
# "Fun Fact des Tages": eine von Hand geschriebene, geprueft-faktentreue Liste
# statt eines Live-Netzabrufs - passt zur deterministischen, KI-freien
# Architektur (kein API-Key im Deploy, kein Risiko unwahrer generierter
# Inhalte). Ausgewaehlt wird taeglich deterministisch nach Tag-des-Jahres
# (siehe dailybrief.py), kein Zufall, kein Netzzugriff. Mischung aus
# Wirtschaftsbegriffen (fuer eine BWL-Studentin), Geschichte und einfach
# erklaerter Technik. Jederzeit erweiterbar - laenger als 366 Eintraege muss
# die Liste nie werden, da sie ohnehin taeglich rotiert.
DAILY_FACTS = [
    {"title": "Opportunitätskosten", "text": "Die Opportunitätskosten einer Entscheidung sind der Wert der besten Alternative, auf die man verzichtet. Verbringst du einen Abend mit Lernen statt mit einem Nebenjob, sind die entgangenen Stunden Lohn deine Opportunitätskosten des Lernens - auch wenn kein Geld fließt, ist es ein echter Kostenfaktor."},
    {"title": "Warum Bluetooth 'Bluetooth' heißt", "text": "Bluetooth ist nach dem dänischen Wikingerkönig Harald Blauzahn (Harald Blåtand) benannt, der im 10. Jahrhundert Dänemark und Norwegen einte. Das Funklogo ist eine Kombination der Runen für seine Initialen H und B - Bluetooth sollte Geräte verschiedener Hersteller vereinen, so wie Harald die Stämme einte."},
    {"title": "Sunk Cost Fallacy", "text": "Der 'Sunk Cost'-Fehlschluss beschreibt die Tendenz, eine Entscheidung an bereits investiertem Geld oder Zeit festzumachen, statt am zukünftigen Nutzen. Ökonomisch sind versunkene Kosten irrelevant für rationale Entscheidungen - sie sind ausgegeben, egal wie man sich jetzt entscheidet."},
    {"title": "Die Erfindung des Wechselgeldes", "text": "Münzgeld entstand vermutlich im 7. Jahrhundert v. Chr. im Königreich Lydien (heute Westtürkei) aus Elektron, einer natürlichen Gold-Silber-Legierung. Vorher lief Handel über abgewogene Edelmetallstücke - genormte, gestempelte Münzen machten Transaktionen erstmals schnell vergleichbar."},
    {"title": "Wie WLAN wirklich funktioniert", "text": "WLAN überträgt Daten per Funkwellen im 2,4- oder 5-Gigahertz-Band - denselben Frequenzbereichen, die auch Mikrowellen nutzen (deshalb kann eine laufende Mikrowelle das Signal stören). Der Router wandelt Internetdaten in Funksignale um und wieder zurück, wenn sie ankommen."},
    {"title": "Skaleneffekte", "text": "Skaleneffekte (Economies of Scale) senken die Stückkosten, je mehr produziert wird, weil sich Fixkosten wie Maschinen oder Entwicklung auf mehr Einheiten verteilen. Das ist ein Hauptgrund, warum große Konzerne oft günstiger produzieren können als kleine Wettbewerber."},
    {"title": "Der erste Börsencrash der Geschichte", "text": "Als erster spekulativer Crash der Wirtschaftsgeschichte gilt die Tulpenmanie in den Niederlanden 1637: Preise für seltene Tulpenzwiebeln stiegen auf das Vielfache eines Handwerkerjahreslohns, bevor der Markt binnen Wochen zusammenbrach."},
    {"title": "Warum GPS so genau ist", "text": "GPS-Satelliten tragen Atomuhren, die durch die Relativitätstheorie leicht anders ticken als Uhren auf der Erde - schneller wegen geringerer Schwerkraft, langsamer wegen ihrer hohen Geschwindigkeit. Ohne diese Korrektur würde sich der berechnete Standort um mehrere Kilometer pro Tag verschieben."},
    {"title": "Angebot und Nachfrage im Kaffeehaus", "text": "Das erste bekannte Kaffeehaus Europas eröffnete 1645 in Venedig. Kaffeehäuser wurden schnell zu Handelsplätzen - Lloyd's of London, heute einer der größten Versicherungsmärkte der Welt, entstand 1688 aus einem Londoner Kaffeehaus, in dem sich Reeder und Versicherer trafen."},
    {"title": "Wie Touchscreens Berührungen erkennen", "text": "Kapazitive Touchscreens (wie bei Smartphones) tragen ein feines Gitter aus leitfähigen Elektroden unter dem Glas. Eine Fingerberührung verändert lokal das elektrische Feld - der Chip berechnet aus dieser Veränderung die genaue Position, deshalb funktionieren sie mit Fingern, aber meist nicht mit dicken Handschuhen."},
    {"title": "Inflation ist nicht gleich Preissteigerung", "text": "Inflation misst die durchschnittliche Preisentwicklung eines ganzen Warenkorbs über Zeit, nicht den Preis eines einzelnen Produkts. Steigt Butter im Preis, während Strom günstiger wird, kann die Gesamtinflation trotzdem niedrig oder sogar negativ sein."},
    {"title": "Die Hanse - ein mittelalterliches Wirtschaftsnetzwerk", "text": "Die Hanse war ein Bund von Kaufleuten und Städten (u.a. Lübeck, Hamburg, Danzig), der vom 13. bis 17. Jahrhundert den Handel im Nord- und Ostseeraum dominierte. Sie hatte eigene Handelsniederlassungen ('Kontore') von London bis Nowgorod, aber nie eine zentrale Regierung."},
    {"title": "Warum Flugzeug-WLAN oft langsam ist", "text": "Flugzeuge verbinden sich meist über Satelliten oder Bodenstationen, die die Kabine mit einer geteilten Bandbreite versorgen - alle Passagiere teilen sich dieselbe Verbindung. Je mehr Menschen gleichzeitig streamen, desto langsamer wird es für alle."},
    {"title": "Der Zinseszinseffekt", "text": "Beim Zinseszins werden bereits erhaltene Zinsen im nächsten Jahr mitverzinst - dadurch wächst ein Vermögen nicht linear, sondern exponentiell. Albert Einstein soll den Zinseszins (ob belegt oder nicht) als 'das achte Weltwunder' bezeichnet haben, weil sein Effekt über Jahrzehnte oft unterschätzt wird."},
    {"title": "Die Geburtsstunde des Aktienmarkts", "text": "Die erste moderne Aktiengesellschaft war die niederländische Vereinigte Ostindien-Kompanie (VOC), gegründet 1602. Ihre Anteile wurden an der Amsterdamer Börse gehandelt - der ersten Börse der Welt, an der dauerhaft Anteile eines Unternehmens frei gekauft und verkauft werden konnten."},
    {"title": "Wie ein Katalysator im Auto funktioniert", "text": "Ein Drei-Wege-Katalysator wandelt giftige Abgase (Kohlenmonoxid, Stickoxide, unverbrannte Kohlenwasserstoffe) mithilfe von Edelmetallen wie Platin und Rhodium in weniger schädliche Stoffe wie CO2, Stickstoff und Wasser um - deshalb enthalten alte Katalysatoren wertvolle Metalle und werden recycelt."},
    {"title": "Das Pareto-Prinzip", "text": "Der italienische Ökonom Vilfredo Pareto beobachtete 1896, dass rund 80% des Landbesitzes in Italien etwa 20% der Bevölkerung gehörten. Daraus entstand die verallgemeinerte '80/20-Regel', die in der Betriebswirtschaft oft (nicht immer exakt zutreffend) auf Ursache-Wirkung-Verhältnisse angewendet wird."},
    {"title": "Warum der Suezkanal so wichtig für den Welthandel ist", "text": "Der 1869 eröffnete Suezkanal verbindet Mittelmeer und Rotes Meer und erspart Schiffen zwischen Europa und Asien die Umrundung Afrikas - eine Ersparnis von oft über 7.000 Kilometern. Als die 'Ever Given' ihn 2021 sechs Tage blockierte, stauten sich Waren im Wert von Milliarden Dollar täglich."},
    {"title": "Wie ein Touchscreen-Stift ohne Batterie funktioniert", "text": "Passive Eingabestifte für Touchscreens brauchen keine Batterie: ihre leitfähige Spitze schließt einfach den Stromkreis wie ein Finger. Aktive Stifte (z.B. Apple Pencil) senden dagegen eigene Signale und ermöglichen dadurch Druckempfindlichkeit."},
    {"title": "Die Erfindung der doppelten Buchführung", "text": "Die doppelte Buchführung - jede Transaktion wird auf zwei Konten erfasst, Soll und Haben - wurde erstmals 1494 systematisch vom italienischen Mönch Luca Pacioli beschrieben. Sie gilt als Grundlage des modernen Rechnungswesens und wird bis heute nahezu unverändert genutzt."},
    {"title": "Warum Antibiotika nicht gegen Viren wirken", "text": "Antibiotika stören gezielt Prozesse in Bakterienzellen, etwa den Aufbau ihrer Zellwand. Viren haben keine eigene Zellwand und keinen eigenen Stoffwechsel - sie kapern die Zellen des Wirts. Deshalb helfen Antibiotika bei einer Grippe oder Erkältung (meist Viren) grundsätzlich nicht."},
    {"title": "Der Ursprung des Wortes 'Bankrott'", "text": "Das Wort stammt vom italienischen 'banca rotta' ('zerbrochene Bank') - im mittelalterlichen Italien saßen Geldwechsler an Tischen ('banca'). Konnte ein Händler seine Schulden nicht mehr bezahlen, wurde sein Tisch der Überlieferung nach zerbrochen."},
    {"title": "Wie Rauchmelder Rauch erkennen", "text": "Die meisten Rauchmelder arbeiten optisch: eine LED sendet Licht in eine Kammer, die im Normalfall nicht auf einen Sensor trifft. Dringt Rauch ein, streut er das Licht, sodass es den Sensor erreicht und den Alarm auslöst - kein Feuer nötig, nur genug Partikel in der Luft."},
    {"title": "Was ein Monopol wirtschaftlich bedeutet", "text": "Ein Monopol liegt vor, wenn ein einziger Anbieter einen Markt beherrscht und keine echten Wettbewerber existieren. Ökonomisch problematisch ist das, weil der Anbieter Preise über dem Wettbewerbsniveau setzen kann - deshalb gibt es in den meisten Ländern eigene Kartell- und Wettbewerbsbehörden."},
    {"title": "Die Weltwirtschaftskrise begann mit einem Börsencrash", "text": "Am 'Schwarzen Donnerstag', dem 24. Oktober 1929, brach die New Yorker Börse ein. Der folgende Kurssturz war nicht die alleinige Ursache, aber der sichtbare Auslöser der Weltwirtschaftskrise der 1930er-Jahre, die Millionen Menschen weltweit in Arbeitslosigkeit stürzte."},
    {"title": "Wie Kopfhörer mit Noise Cancelling funktionieren", "text": "Aktive Geräuschunterdrückung misst Umgebungsgeräusche per Mikrofon und erzeugt eine Schallwelle, die genau gegenphasig zum Störgeräusch ist - beide Wellen löschen sich rechnerisch nahezu aus. Das funktioniert besonders gut bei tiefen, gleichmäßigen Tönen wie Flugzeug- oder Motorenlärm."},
    {"title": "Warum Zentralbanken unabhängig sein sollen", "text": "Die meisten großen Zentralbanken (z.B. die Europäische Zentralbank) sind bewusst unabhängig von der Regierung, um Zinsentscheidungen vor kurzfristigem politischem Druck zu schützen - etwa der Versuchung, vor Wahlen die Wirtschaft künstlich per Niedrigzins anzukurbeln."},
    {"title": "Der Marshallplan nach dem Zweiten Weltkrieg", "text": "Mit dem Marshallplan (offiziell European Recovery Program) unterstützten die USA ab 1948 den Wiederaufbau Westeuropas mit umgerechnet heute rund 150 Milliarden Dollar - auch Westdeutschland profitierte erheblich, was zum sogenannten 'Wirtschaftswunder' der 1950er-Jahre beitrug."},
    {"title": "Wie ein Lithium-Ionen-Akku Energie speichert", "text": "In einem Lithium-Ionen-Akku wandern beim Laden Lithium-Ionen von der Kathode zur Anode und lagern sich dort ein; beim Entladen wandern sie zurück und geben dabei Energie als elektrischen Strom ab. Die 'Ionen wandern hin und her'-Bauweise ist auch als Grund für den Namen 'Rocking-Chair-Batterie' bekannt."},
    {"title": "Die Erfindung des Fließbands", "text": "Henry Ford führte 1913 in seiner Fabrik in Highland Park das laufende Fließband ein und senkte die Produktionszeit eines Model T von über 12 Stunden auf etwa 90 Minuten. Dadurch konnte er Autos so günstig herstellen, dass sie erstmals für breite Bevölkerungsschichten erschwinglich wurden."},
    {"title": "Warum Kreditkartennummern nicht zufällig sind", "text": "Kreditkartennummern folgen dem Luhn-Algorithmus, einer einfachen Prüfsummenformel aus den 1950er-Jahren. Sie erkennt zuverlässig einzelne Zahlendreher oder Tippfehler - deshalb kann ein Zahlungssystem eine offensichtlich falsch eingetippte Nummer sofort ablehnen, bevor überhaupt eine Bank angefragt wird."},
    {"title": "Das Konzept des Humankapitals", "text": "Humankapital bezeichnet den wirtschaftlichen Wert, den Wissen, Fähigkeiten und Erfahrung eines Menschen für seine Produktivität haben. Ausgaben für Bildung gelten ökonomisch deshalb nicht nur als Konsum, sondern als Investition, die sich später in höherem Einkommen niederschlagen kann."},
    {"title": "Die Geschichte des Papiergelds", "text": "Papiergeld wurde erstmals im China der Tang- und vor allem der Song-Dynastie (ab dem 7.-11. Jahrhundert) eingeführt, weil Kupfermünzen für große Transaktionen zu schwer wurden. In Europa dauerte es bis ins 17. Jahrhundert, bis sich Banknoten durchsetzten."},
    {"title": "Wie ein Mikrowellenherd Essen erhitzt", "text": "Mikrowellen bringen Wassermoleküle im Essen dazu, sich milliardenfach pro Sekunde auszurichten und wieder zurückzudrehen - diese Reibung erzeugt Wärme direkt im Lebensmittel, statt es wie ein Backofen nur von außen zu erhitzen. Deshalb werden wasserarme Materialien wie Porzellan kaum warm."},
    {"title": "Was 'Diversifikation' wirklich bringt", "text": "Diversifikation streut Kapital über mehrere, möglichst wenig korrelierte Anlagen, um das Gesamtrisiko zu senken, ohne zwangsläufig die erwartete Rendite zu opfern. Der Ökonom Harry Markowitz erhielt für diese 'Portfoliotheorie' 1990 den Wirtschaftsnobelpreis."},
    {"title": "Der Ursprung der Börse Amsterdam", "text": "Die Amsterdamer Börse eröffnete 1611 als erstes dauerhaftes Gebäude speziell für den Aktienhandel. Vorher trafen sich Händler auf offenen Plätzen oder in Kaffeehäusern - ein eigenes Gebäude machte den Handel erstmals zu einer täglichen, institutionalisierten Routine."},
    {"title": "Wie Fingerabdrucksensoren am Smartphone funktionieren", "text": "Kapazitive Fingerabdrucksensoren messen winzige Unterschiede im elektrischen Feld zwischen den Rillen (nah am Sensor) und Tälern (weiter weg) deines Fingerabdrucks und setzen daraus ein Bild zusammen - ganz ohne sichtbares Licht oder Kamera."},
    {"title": "Warum 'zu groß, um zu scheitern' ein Problem ist", "text": "'Too big to fail' beschreibt Banken oder Konzerne, deren Zusammenbruch das gesamte Finanzsystem gefährden würde - Staaten sehen sich deshalb oft gezwungen, sie mit Steuergeld zu retten. Kritiker sagen, das schaffe einen Anreiz für besonders riskantes Verhalten, weil Verluste im Ernstfall sozialisiert werden."},
    {"title": "Die Erfindung des Kühlschranks veränderte den Handel", "text": "Erst mit zuverlässigen elektrischen Kühlschränken ab den 1920er-Jahren wurde der Handel mit verderblichen Lebensmitteln über weite Strecken praktikabel. Vorher mussten Städte auf lokale Landwirtschaft oder teuren, unsicheren Eistransport setzen."},
    {"title": "Wie GPS-freie Indoor-Navigation funktioniert", "text": "In Gebäuden, wo GPS-Signale zu schwach sind, orten Apps das Smartphone oft über die Signalstärke bekannter WLAN-Router oder Bluetooth-Beacons - je nachdem, wie stark oder schwach mehrere Signale ankommen, lässt sich die Position auf wenige Meter genau berechnen."},
    {"title": "Was ein 'Schwarzer Schwan' in der Wirtschaft ist", "text": "Der Begriff 'Schwarzer Schwan' (geprägt vom Autor Nassim Taleb) beschreibt extrem seltene, kaum vorhersehbare Ereignisse mit gewaltigen Folgen - im Nachhinein wirken sie oft erklärbar, obwohl sie vorher kaum jemand für möglich hielt, etwa die Finanzkrise 2008."},
    {"title": "Die Erfindung des Schecks", "text": "Vorläufer des Schecks gab es schon im antiken Persien und im mittelalterlichen arabischen Handel, wo Kaufleute per Zahlungsanweisung ('Sakk') Geld überweisen konnten, ohne Münzen physisch zu transportieren - ein früher Schritt weg vom reinen Bargeldhandel."},
    {"title": "Wie ein 3D-Drucker ein Objekt aufbaut", "text": "Die meisten 3D-Drucker für zuhause arbeiten additiv: sie schmelzen einen Kunststofffaden und tragen ihn Schicht für Schicht entlang eines digitalen Modells auf, bis nach oft Hunderten Schichten das fertige Objekt entsteht - das Gegenteil von Fräsen, wo Material abgetragen wird."},
    {"title": "Der Unterschied zwischen BIP und BSP", "text": "Das Bruttoinlandsprodukt (BIP) misst die Wirtschaftsleistung innerhalb der Landesgrenzen, egal wer sie erbringt. Das Bruttosozialprodukt (heute meist Bruttonationaleinkommen genannt) misst dagegen die Leistung aller Staatsangehörigen, egal wo auf der Welt sie erwirtschaftet wird."},
    {"title": "Die Weltausstellung als Wirtschaftsschaufenster", "text": "Die erste Weltausstellung fand 1851 im Kristallpalast in London statt und zeigte industrielle Innovationen aus aller Welt. Solche Ausstellungen dienten Ländern lange als PR-Bühne für ihre wirtschaftliche und technische Stärke - der Eiffelturm entstand 1889 als Eingangstor zur Pariser Weltausstellung."},
    {"title": "Wie Kreditausfallversicherungen (CDS) funktionieren", "text": "Ein Credit Default Swap ist im Kern eine Versicherung gegen den Zahlungsausfall eines Schuldners - der Käufer zahlt regelmäßige Prämien und bekommt bei Ausfall eine Entschädigung. In der Finanzkrise 2008 verstärkten massenhaft gehandelte CDS auf Hypothekenpapiere die Krise erheblich."},
    {"title": "Warum Flugzeugreifen so oft nachgesehen werden", "text": "Flugzeugreifen sind mit Stickstoff statt normaler Luft gefüllt, weil Stickstoff kaum auf Temperaturschwankungen reagiert und nicht brennbar ist - bei den enormen Belastungen von Start und Landung (oft über 300 km/h Aufsetzgeschwindigkeit) ist konstanter Reifendruck entscheidend für die Sicherheit."},
    {"title": "Das Konzept der 'unsichtbaren Hand'", "text": "Der Ökonom Adam Smith prägte 1776 in 'Der Wohlstand der Nationen' das Bild der 'unsichtbaren Hand': Wenn jeder im Eigeninteresse handelt (etwa ein Bäcker, der Brot verkauft, um Gewinn zu machen), kann daraus trotzdem ein für alle vorteilhaftes Marktergebnis entstehen - ganz ohne zentrale Planung."},
    {"title": "Wie QR-Codes so viel Information speichern", "text": "Ein QR-Code speichert Daten nicht linear wie ein klassischer Barcode, sondern zweidimensional in einem Raster aus schwarzen und weißen Feldern - dadurch passt deutlich mehr Information hinein. Drei markante Eckquadrate helfen der Kamera, den Code aus jedem Winkel korrekt auszurichten."},
    {"title": "Die Erfindung des Franchise-Modells", "text": "Isaac Singer, Erfinder der modernen Nähmaschine, gilt als einer der Pioniere des Franchisings: In den 1850er-Jahren ließ er unabhängige Händler seine Maschinen unter seinem Namen verkaufen und warten - ein Modell, das später Ketten wie McDonald's massenhaft übernahmen."},
    {"title": "Was 'Preiselastizität der Nachfrage' bedeutet", "text": "Die Preiselastizität zeigt, wie stark die nachgefragte Menge auf eine Preisänderung reagiert. Bei lebensnotwendigen Gütern wie Insulin ist sie meist gering (Menschen kaufen es fast unabhängig vom Preis), bei Luxusgütern oder leicht ersetzbaren Produkten dagegen oft hoch."},
    {"title": "Wie Solarzellen Licht in Strom umwandeln", "text": "Trifft Licht auf eine Solarzelle aus Silizium, lösen die Lichtteilchen (Photonen) Elektronen aus ihrer Bindung - dieser sogenannte photoelektrische Effekt erzeugt einen Elektronenfluss, also elektrischen Strom. Albert Einstein erhielt für die theoretische Erklärung dieses Effekts 1921 den Nobelpreis."},
    {"title": "Die Südsee-Blase von 1720", "text": "Die South Sea Company versprach Anlegern hohe Gewinne aus dem Handel mit Südamerika, obwohl kaum reales Geschäft dahinterstand. Die Aktie verzehnfachte sich 1720 innerhalb weniger Monate, bevor die Blase platzte - selbst Isaac Newton verlor dabei einen erheblichen Teil seines Vermögens."},
    {"title": "Warum USB-Kabel oft erst beim zweiten Versuch passen", "text": "Klassische USB-A-Stecker sind zwar rechteckig, aber innen asymmetrisch aufgebaut - deshalb passen sie nur in einer von zwei Ausrichtungen. USB-C wurde bewusst symmetrisch designt, damit der Stecker in beide Richtungen passt."},
    {"title": "Das Prinzip der Grenzkosten", "text": "Grenzkosten sind die Kosten, die durch die Produktion genau einer zusätzlichen Einheit entstehen. Unternehmen lohnt es sich rein ökonomisch, so lange zu produzieren, wie der Verkaufspreis über den Grenzkosten liegt - danach macht jede weitere Einheit Verlust."},
    {"title": "Die Erfindung des Containers revolutionierte den Welthandel", "text": "Der US-Spediteur Malcom McLean verschiffte 1956 erstmals standardisierte Stahlcontainer statt loser Fracht. Weil Waren dadurch viel schneller und günstiger von Schiff auf Zug oder LKW umgeladen werden konnten, gilt der Container als einer der größten Treiber der modernen Globalisierung."},
    {"title": "Wie Kopfhörer-Bluetooth Verzögerung entsteht", "text": "Bluetooth-Audio muss Musik komprimieren, senden und beim Empfänger wieder dekomprimieren - dieser Prozess braucht Zeit, meist 100-200 Millisekunden. Bei Musikgenuss fällt das kaum auf, bei Videos kann es zu leicht asynchronen Lippenbewegungen führen."},
    {"title": "Was ein Leitzins wirklich steuert", "text": "Der Leitzins ist der Zinssatz, zu dem sich Geschäftsbanken bei der Zentralbank Geld leihen können. Erhöht ihn die Zentralbank, werden Kredite für Banken und in der Folge für Verbraucher teurer - das bremst Konsum und Investitionen und wird typischerweise gegen hohe Inflation eingesetzt."},
    {"title": "Die Geschichte der ersten Kreditkarte", "text": "Die erste breit nutzbare Kreditkarte war die Diners Club Card von 1950, ursprünglich für Restaurantrechnungen gedacht. Die Idee soll entstanden sein, nachdem ein Geschäftsmann in New York sein Portemonnaie beim Abendessen vergessen hatte."},
    {"title": "Wie Klimaanlagen Räume kühlen", "text": "Klimaanlagen kühlen nicht direkt, sondern entziehen der Raumluft Wärme: Ein Kältemittel verdampft im Inneren und nimmt dabei Wärme auf, wird dann verdichtet und gibt die Wärme draußen wieder ab. Das ist im Prinzip derselbe Kreislauf wie in einem Kühlschrank."},
    {"title": "Der Unterschied zwischen Aktie und Anleihe", "text": "Wer eine Aktie kauft, wird Miteigentümer eines Unternehmens und trägt unternehmerisches Risiko und Chance. Wer eine Anleihe kauft, verleiht dem Emittenten Geld gegen feste Zinsen und hat im Grundsatz Anspruch auf Rückzahlung - unabhängig davon, wie profitabel das Unternehmen wirtschaftet."},
    {"title": "Die Erfindung der Glühbirne war ein Wettlauf", "text": "Thomas Edison gilt oft als alleiniger Erfinder der Glühbirne, doch mehrere Erfinder (u.a. Joseph Swan in England) arbeiteten parallel an ähnlichen Lösungen. Edisons eigentliche Leistung 1879 war weniger das Grundprinzip als ein praktikabler, langlebiger Glühfaden und ein vermarktbares Gesamtsystem."},
    {"title": "Wie ein Head-up-Display im Auto Bilder in die Luft zaubert", "text": "Ein Head-up-Display projiziert ein Bild auf die Windschutzscheibe (oder eine kleine Glasscheibe), die es zum Fahrer zurückspiegelt - das Gehirn interpretiert das reflektierte Licht so, als schwebe die Anzeige einige Meter vor dem Auto in der Luft."},
    {"title": "Was 'Moral Hazard' bedeutet", "text": "Moral Hazard beschreibt, wie eine Absicherung gegen Risiko dazu verleiten kann, riskanter zu handeln, weil man die Konsequenzen nicht mehr voll trägt - etwa wenn eine Vollkaskoversicherung dazu führt, dass man vorsichtiger mit dem eigenen, aber sorgloser mit dem versicherten Auto umgeht."},
    {"title": "Die Erfindung des Aktienindex", "text": "Der Dow Jones Industrial Average von 1896 war einer der ersten Aktienindizes und bestand anfangs aus nur 12 Unternehmen. Ein Index fasst die Kursentwicklung mehrerer Aktien in einer einzigen Zahl zusammen, um die Stimmung 'des Marktes' auf einen Blick lesbar zu machen."},
    {"title": "Wie ein Airbag in Millisekunden auslöst", "text": "Sensoren im Auto erkennen eine plötzliche Verzögerung (also einen Aufprall) und lösen eine kleine, kontrollierte Explosion aus, die den Airbag in unter 50 Millisekunden mit Gas füllt - schneller, als ein Mensch bewusst reagieren könnte."},
    {"title": "Der Ursprung des Wortes 'Salär'", "text": "Das Wort Salär (Gehalt) leitet sich vom lateinischen 'salarium' ab, ursprünglich einer Zuteilung von Salz an römische Soldaten und Beamte - Salz war damals ein wertvolles Konservierungsmittel. Ob daraus auch die Redewendung 'sein Geld wert sein' stammt, ist allerdings umstritten."},
]

MARKETS_LOOKBACK_YEARS = 3
MARKETS_TOP_N = 5
MARKETS_TTL_MINUTES = 12 * 60  # Kursverlauf ueber 3 Jahre aendert sich nicht im 30-Min-Takt
MARKETS_SPARK_POINTS = 24  # Stuetzstellen der Mini-Grafik je Titel (siehe markets._downsample)
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

CANDIDATE_ETFS = [
    "VWCE.DE", "IWDA.AS", "SXR8.DE", "XDWD.DE", "IUSQ.DE", "EUNL.DE",
    "CSPX.L", "VUAA.L", "IS3N.DE", "XMME.DE", "CSNDX.SW", "XDEM.DE", "SPYI.DE",
]

CANDIDATE_STOCKS = [
    "AMZN", "TSLA", "MELI", "SHOP", "NFLX", "PLTR", "CRWD", "UBER", "ABNB",
    "DDOG", "NET", "SNOW", "RBLX", "COIN", "ISRG", "LULU", "TTD", "ADBE",
]

# Breiterer, ungefilterter Suchindex fuer "beliebige Firma/Ticker suchbar"
# (z.B. SAP, das wegen Dividendenausschuettung nie in CANDIDATE_STOCKS landen
# kann). Keine Dividenden-Ausschluss-Regel, kein Top-N, keine 3J-Rangliste -
# nur Name/Preis/Tagesveraenderung/Spark, siehe markets.py::_refresh_search().
# Bewusst auf ein paar Dutzend bekannte Titel begrenzt (DAX-Schwergewichte +
# grosse US-Techwerte), nicht auf "alle Ticker" - das wuerde den
# MARKETS_TTL_MINUTES-Abrufaufwand sprengen.
SEARCH_INDEX_STOCKS = [
    "SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "AIR.DE", "MBG.DE", "BMW.DE",
    "BAS.DE", "MUV2.DE", "ADS.DE", "DHL.DE", "IFX.DE", "VOW3.DE", "RWE.DE",
    "AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMZN", "TSLA", "JPM", "V",
    "WMT", "KO", "MCD", "DIS",
]


def source_by_key(key: str) -> dict | None:
    for src in SOURCES:
        if src["key"] == key:
            return src
    return None


def all_feeds() -> list[tuple[dict, str, str]]:
    """Liefert (source, feed_url, topic) fuer jeden konfigurierten Feed."""
    out = []
    for src in SOURCES:
        for feed_url, topic in src["feeds"]:
            out.append((src, feed_url, topic))
    return out
