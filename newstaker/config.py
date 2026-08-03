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
# tier: 1 = Kernquelle (von Liv explizit gefordert bzw. gleichwertig),
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
    # ---- Kernquellen Deutschland (von Liv gefordert) ----
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
# Livs erklaerter Fokus: Welt, Wirtschaft, Wissenschaft.
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
# Ersetzt die "Themen des Tages"-Uebersicht oben im Board (Liv fand sie
# unverstaendlich und nicht hilfreich). Liv baut langfristig Vermoegen mit
# nicht-dividendenzahlenden ETFs und Wachstumsaktien auf - gezeigt werden
# reine Kennzahlen (Tagespreis, Veraenderung ueber 3 Jahre), keine
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

MARKETS_LOOKBACK_YEARS = 3
MARKETS_TOP_N = 5
MARKETS_TTL_MINUTES = 12 * 60  # Kursverlauf ueber 3 Jahre aendert sich nicht im 30-Min-Takt
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

CANDIDATE_ETFS = [
    "VWCE.DE", "IWDA.AS", "SXR8.DE", "XDWD.DE", "IUSQ.DE", "EUNL.DE",
    "CSPX.L", "VUAA.L", "IS3N.DE", "XMME.DE", "CSNDX.SW", "XDEM.DE", "SPYI.DE",
]

CANDIDATE_STOCKS = [
    "AMZN", "TSLA", "MELI", "SHOP", "NFLX", "PLTR", "CRWD", "UBER", "ABNB",
    "DDOG", "NET", "SNOW", "RBLX", "COIN", "ISRG", "LULU", "TTD", "ADBE",
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
