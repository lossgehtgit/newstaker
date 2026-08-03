"""Normalisierung von URLs und Titeln.

Diese Datei entscheidet, was als "dieselbe Meldung" gilt und welche Woerter das
Clustering ueberhaupt sieht. Alles hier ist rein funktional und ohne Zufall -
gleiche Eingabe, gleiche Ausgabe.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from functools import lru_cache
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from . import config

# Tracking-Parameter, die dieselbe Seite unter verschiedenen URLs erscheinen
# lassen. Alles mit utm_ Praefix wird generisch entfernt.
_DROP_PARAMS = {
    "ref", "cmp", "src", "source", "smid", "partner", "referrer", "referer",
    "at_medium", "at_campaign", "at_custom1", "at_custom2", "at_custom3",
    "at_custom4", "at_link_id", "at_link_type", "at_link_origin", "at_bbc_team",
    "ns_mchannel", "ns_source", "ns_campaign", "ns_linkname", "ns_fee",
    "ito", "CMP", "sh", "share", "fbclid", "gclid", "igshid", "mc_cid", "mc_eid",
    "xtor", "wt_mc", "wt_zmc", "GEPC", "seite",
}

# Kicker-Praefixe wie "Zoelle: " oder "Hollywood-Deal: " tragen keine
# Information ueber das Ereignis, verschlechtern aber die Aehnlichkeitsmessung.
#
# Die Begrenzung auf hoechstens zwei Woerter ist wesentlich: ein Ressortkuerzel
# besteht praktisch immer aus ein bis zwei Woertern ("Zoelle", "Hollywood-Deal",
# "Liveblog Irankrieg"). Ein laengerer Vorspann ist in aller Regel schon der
# Inhalt - "Waldbraende in Frankreich: Mehr als 110.000 Menschen evakuiert"
# wuerde sonst sein Thema verlieren und faende seine Geschwistermeldungen nicht
# mehr.
_KICKER_RE = re.compile(r"^(?P<kicker>[^:]{2,28}):\s+")
_KICKER_MAX_WORDS = 2
_LIVE_PREFIX_RE = re.compile(
    r"^(liveblog|newsblog|ticker|live|update|kommentar|analyse|interview|gastbeitrag|"
    r"podcast|video|audio|grafik|faq|portraet|portrait|nachruf|glosse|meinung)\b[:\s|-]*",
    re.I,
)
# Quellen-Suffixe wie " - Handelsblatt" oder " | ZEIT ONLINE".
_SUFFIX_RE = re.compile(
    r"\s*[-–|·]\s*(handelsblatt|tagesschau\.?de|der spiegel|spiegel online|faz\.net|"
    r"zeit online|sz\.de|heise online|bbc news|the guardian|reuters|bloomberg|cnbc|npr)\s*$",
    re.I,
)

_WORD_RE = re.compile(r"[a-z0-9]+")


@lru_cache(maxsize=1)
def _stopwords() -> frozenset[str]:
    words: set[str] = set()
    for name in ("stopwords_de.txt", "stopwords_en.txt"):
        path = config.DATA_DIR / name
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    words.add(fold(line))
    return frozenset(words)


def fold(text: str) -> str:
    """Kleinschreibung + Umlautaufloesung + Diakritika entfernen.

    Muss zu der FTS5-Tokenisierung passen (unicode61 remove_diacritics 2),
    damit Suche und Clustering dieselbe Wortform sehen.
    """
    text = text.lower()
    text = (
        text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
        .replace("ß", "ss").replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    )
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def canonical_url(url: str) -> str:
    """Entfernt Tracking-Parameter, Fragment und ueberfluessige Endungen."""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    scheme = parts.scheme.lower() or "https"
    if scheme == "http":
        scheme = "https"
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    # Standardports weg
    netloc = netloc.replace(":443", "").replace(":80", "")

    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith("utm_") and k not in _DROP_PARAMS
    ]
    query = "&".join(f"{k}={v}" for k, v in sorted(query_pairs))

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    return urlunsplit((scheme, netloc, path, query, ""))


def item_id(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def strip_kicker(title: str) -> str:
    """Entfernt Ressort-Praefixe und Quellen-Suffixe aus einer Schlagzeile."""
    out = title.strip()
    out = _SUFFIX_RE.sub("", out)
    out = _LIVE_PREFIX_RE.sub("", out).strip()
    # Nur abschneiden, wenn der Vorspann wie ein Ressortkuerzel aussieht und
    # danach noch genug Titel uebrig bleibt - sonst zerstoert man Titel wie
    # "Merz: Wir bleiben dabei".
    m = _KICKER_RE.match(out)
    if m and len(out) - m.end() >= 24:
        if len(m.group("kicker").split()) <= _KICKER_MAX_WORDS:
            out = out[m.end():].strip()
    return out or title.strip()


# Sehr zurueckhaltende Endungsnormalisierung. Ohne sie findet
# "Waldbraenden" (Dativ) sein Gegenstueck "Waldbraende" nicht, und genau diese
# Beugungsunterschiede trennen im Deutschen sonst zusammengehoerende Meldungen.
# Nur eine Endung, nur ab sechs Zeichen, und es bleiben immer mindestens vier
# Zeichen stehen - damit bleibt der Wortstamm unterscheidbar.
_SUFFIXES = ("ern", "en", "er", "es", "e", "n", "s")
_STEM_MIN_LENGTH = 6
_STEM_MIN_REST = 4


def stem(word: str) -> str:
    if len(word) < _STEM_MIN_LENGTH:
        return word
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= _STEM_MIN_REST:
            return word[: -len(suffix)]
    return word


def tokens(title: str) -> frozenset[str]:
    """Inhaltstoken einer Schlagzeile - Grundlage der Aehnlichkeitsmessung."""
    stop = _stopwords()
    words = _WORD_RE.findall(fold(strip_kicker(title)))
    return frozenset(stem(w) for w in words if len(w) > 2 and w not in stop)


# --------------------------------------------------------------- Themen
#
# Ein Feed bringt sein Topic mit (config.SOURCES). Zusaetzlich koennen die
# Kategorien im Feed das Thema praezisieren - rein regelbasiert, keine
# Klassifikation durch ein Modell.

_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("wirtschaft", (
        "wirtschaft", "finanzen", "boerse", "borse", "markt", "markets", "business",
        "economy", "economics", "unternehmen", "companies", "finance", "money",
        "konjunktur", "handel", "trade", "banken", "immobilien",
    )),
    ("wissenschaft", (
        "wissenschaft", "wissen", "forschung", "science", "research", "health",
        "gesundheit", "medizin", "medicine", "klima", "climate", "environment",
        "umwelt", "natur", "physics", "biology", "space", "raumfahrt",
    )),
    ("technologie", (
        "technologie", "technik", "netzwelt", "digital", "technology", "tech",
        "it", "software", "internet", "ki", "artificial intelligence", "computing",
    )),
    ("welt", (
        "ausland", "welt", "world", "international", "global", "europa", "europe",
        "usa", "asien", "asia", "afrika", "africa", "nahost", "middle east", "ukraine",
    )),
    ("politik", (
        "politik", "politics", "inland", "innenpolitik", "bundestag", "wahl",
        "election", "government", "regierung", "eu-politik",
    )),
]


def topic_for_item(feed_topic: str, categories: list[str]) -> str:
    """Bestimmt das Thema. Der Feed gibt den Ausgangswert vor.

    Kategorien koennen ihn ueberschreiben, aber nur wenn sie eindeutig sind -
    das haelt z. B. eine Wirtschaftsmeldung im Schlagzeilen-Feed im richtigen
    Ressort, ohne generische Kategorien wie "News" wirken zu lassen.
    """
    if not categories:
        return feed_topic
    joined = " ".join(fold(c) for c in categories)
    for topic, needles in _CATEGORY_RULES:
        for needle in needles:
            if re.search(rf"\b{re.escape(fold(needle))}", joined):
                return topic
    return feed_topic


# --------------------------------------------------------------- Agentur

_AGENCIES = ("dpa", "afp", "reuters", "ap", "epd", "kna", "sid", "bloomberg", "dpa-afx")


def agency_from(author: str, teaser: str) -> str:
    """Erkennt die Nachrichtenagentur hinter einer Meldung.

    Reuters und AP haben ihre eigenen RSS-Feeds abgeschaltet; ihr Material
    erreicht uns ueber Tagesschau, Handelsblatt und FAZ. Die Agentur wird
    deshalb als Zusatz mitgefuehrt.
    """
    haystack = fold(f"{author} {teaser[:120]}")
    for agency in _AGENCIES:
        if re.search(rf"\b{re.escape(agency)}\b", haystack):
            return agency.upper() if len(agency) <= 3 else agency.capitalize()
    return ""
