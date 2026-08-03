"""RSS-2.0- und Atom-Parser auf Basis von xml.etree.

Bewusst tolerant: Feeds in freier Wildbahn sind uneinheitlich. Getestet gegen
alle in config.SOURCES registrierten Feeds, inklusive der Atom-Variante von
heise und der content:encoded-Bilder von Tagesschau.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

NS = {
    "media": "http://search.yahoo.com/mrss/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom": "http://www.w3.org/2005/Atom",
}

# Nature und Science liefern RSS 1.0 (RDF) mit Default-Namespace. Struktur und
# Elementnamen sind identisch zu RSS 2.0, nur eben namespaced - wir raeumen den
# Namespace vor der Verarbeitung weg und behandeln den Feed danach wie RSS 2.0.
RSS1_NS = "{http://purl.org/rss/1.0/}"
RSS1_ENC_NS = "{http://purl.oclc.org/net/rss_2.0/enc/}"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_IMG_SRC_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)
_SRCSET_RE = re.compile(r"""srcset=["']([^"']+)["']""", re.I)

# Bildformate, die wir akzeptieren. Schuetzt vor Tracking-Pixeln und Logos,
# die manche Feeds als <enclosure> mitschicken.
_IMAGE_EXT_RE = re.compile(r"\.(jpe?g|png|webp|avif|gif)(\?|$)", re.I)
_BAD_IMAGE_RE = re.compile(r"(pixel|tracking|1x1|blank|spacer|logo|avatar|placeholder)", re.I)


@dataclass
class FeedItem:
    title: str = ""
    link: str = ""
    guid: str = ""
    teaser: str = ""
    published: datetime | None = None
    categories: list[str] = field(default_factory=list)
    author: str = ""
    image: str = ""
    position: int = 0


def _text(el) -> str:
    if el is None:
        return ""
    # itertext() faengt auch CDATA mit eingebettetem Markup ein.
    return "".join(el.itertext()).strip()


def clean_text(raw: str, *, limit: int = 600) -> str:
    if not raw:
        return ""
    txt = _TAG_RE.sub(" ", raw)
    txt = html.unescape(txt)
    txt = txt.replace("­", "")          # weiches Trennzeichen
    txt = _WS_RE.sub(" ", txt).strip()
    if len(txt) > limit:
        cut = txt[:limit].rsplit(" ", 1)[0]
        txt = cut + "…"
    return txt


def parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    # Atom / ISO-8601
    candidate = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        try:
            return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _plausible_image(url: str) -> bool:
    if not url or not url.lower().startswith(("http://", "https://")):
        return False
    if _BAD_IMAGE_RE.search(url):
        return False
    # Viele CDNs liefern Bilder ohne Dateiendung, dafuer mit Bildparametern.
    return bool(_IMAGE_EXT_RE.search(url)) or "image" in url.lower() or "/img/" in url.lower()


def _best_from_srcset(srcset: str) -> str:
    """Waehlt aus einem srcset die groesste Variante - deterministisch."""
    best, best_w = "", -1
    for part in srcset.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split()
        url = bits[0]
        width = -1
        if len(bits) > 1 and bits[1].endswith("w"):
            try:
                width = int(bits[1][:-1])
            except ValueError:
                width = -1
        if width > best_w:
            best, best_w = url, width
    return best


def _extract_image(el) -> str:
    """Sucht das Aufmacherbild in der Reihenfolge der Verlaesslichkeit."""
    candidates: list[tuple[int, str]] = []

    # media:content / media:thumbnail - Guardian, NYT, BBC, FAZ, FT
    for tag in ("media:content", "media:thumbnail"):
        for node in el.findall(tag, NS):
            url = (node.get("url") or "").strip()
            if not url:
                continue
            medium = (node.get("medium") or "").lower()
            typ = (node.get("type") or "").lower()
            if medium and medium != "image":
                continue
            if typ and not typ.startswith("image"):
                continue
            try:
                width = int(node.get("width") or 0)
            except ValueError:
                width = 0
            candidates.append((width, url))

    # enclosure - Spiegel, Handelsblatt, ZEIT, Science
    for node in el.findall("enclosure"):
        typ = (node.get("type") or "").lower()
        url = (node.get("url") or "").strip()
        if url and (typ.startswith("image") or _IMAGE_EXT_RE.search(url)):
            candidates.append((0, url))

    # Atom: <link rel="enclosure" type="image/...">
    for node in el.findall("atom:link", NS) + el.findall("link"):
        if (node.get("rel") or "") == "enclosure" and (node.get("type") or "").startswith("image"):
            url = (node.get("href") or "").strip()
            if url:
                candidates.append((0, url))

    # <img> in content:encoded oder description - Tagesschau, heise, NPR, FAZ
    for tag in ("content:encoded", "description", "atom:content", "atom:summary", "summary"):
        node = el.find(tag, NS) if ":" in tag else el.find(tag)
        if node is None:
            continue
        raw = "".join(node.itertext())
        srcset = _SRCSET_RE.search(raw)
        if srcset:
            url = _best_from_srcset(html.unescape(srcset.group(1)))
            if url:
                candidates.append((0, url))
        for m in _IMG_SRC_RE.finditer(raw):
            candidates.append((0, html.unescape(m.group(1)).strip()))

    # Groesste plausible Variante gewinnt; bei Gleichstand die erste - stabil.
    best, best_w = "", -1
    for width, url in candidates:
        url = html.unescape(url).strip()
        if not _plausible_image(url):
            continue
        if width > best_w:
            best, best_w = url, width
    return best


def _extract_link(el) -> str:
    node = el.find("link")
    if node is not None:
        text = _text(node)
        if text:
            return text
        href = node.get("href")
        if href:
            return href.strip()
    # Atom: bevorzugt rel="alternate"
    best = ""
    for node in el.findall("atom:link", NS):
        rel = node.get("rel") or "alternate"
        href = (node.get("href") or "").strip()
        if not href:
            continue
        if rel == "alternate":
            return href
        if not best:
            best = href
    if best:
        return best
    guid = el.find("guid")
    if guid is not None:
        text = _text(guid)
        if text.startswith("http"):
            return text
    return ""


def _strip_rss1_namespace(root) -> None:
    """Macht aus RSS-1.0-Tags gewoehnliche RSS-2.0-Tags (in place)."""
    for el in root.iter():
        if isinstance(el.tag, str):
            if el.tag.startswith(RSS1_NS):
                el.tag = el.tag[len(RSS1_NS):]
            elif el.tag.startswith(RSS1_ENC_NS):
                # enc:enclosure -> enclosure
                el.tag = el.tag[len(RSS1_ENC_NS):]


def parse(body: bytes) -> list[FeedItem]:
    """Parst RSS 2.0 oder Atom. Gibt bei kaputtem XML eine leere Liste zurueck."""
    if not body:
        return []
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        # Manche Feeds haben ein fuehrendes BOM oder Leerzeichen vor <?xml.
        try:
            root = ElementTree.fromstring(body.strip().lstrip(b"\xef\xbb\xbf"))
        except ElementTree.ParseError:
            return []

    _strip_rss1_namespace(root)

    nodes = root.findall(".//item")
    if not nodes:
        nodes = root.findall(".//atom:entry", NS)
    if not nodes:
        nodes = [n for n in root.iter() if n.tag.endswith("}entry") or n.tag == "entry"]

    items: list[FeedItem] = []
    for pos, el in enumerate(nodes):
        title_node = el.find("title")
        if title_node is None:
            title_node = el.find("atom:title", NS)
        title = clean_text(_text(title_node), limit=300)
        if not title:
            continue

        link = _extract_link(el)
        if not link:
            continue

        # Achtung: ein Element ohne Kinder ist in ElementTree falsy, deshalb
        # hier explizit auf None pruefen statt `a or b`.
        guid_node = el.find("guid")
        if guid_node is None:
            guid_node = el.find("atom:id", NS)
        guid = _text(guid_node)

        teaser_raw = ""
        for tag in ("description", "atom:summary", "summary", "content:encoded", "atom:content"):
            node = el.find(tag, NS) if ":" in tag else el.find(tag)
            if node is not None:
                teaser_raw = "".join(node.itertext())
                if clean_text(teaser_raw):
                    break

        date_raw = ""
        for tag in ("pubDate", "dc:date", "atom:published", "atom:updated", "published", "updated"):
            node = el.find(tag, NS) if ":" in tag else el.find(tag)
            if node is not None and _text(node):
                date_raw = _text(node)
                break

        cats = []
        for node in el.findall("category") + el.findall("atom:category", NS):
            val = _text(node) or (node.get("term") or "")
            val = val.strip()
            if val:
                cats.append(val)

        author = ""
        for tag in ("dc:creator", "author", "dc:publisher"):
            node = el.find(tag, NS) if ":" in tag else el.find(tag)
            if node is not None and _text(node):
                author = clean_text(_text(node), limit=80)
                break
        if not author:
            node = el.find("atom:author/atom:name", NS)
            if node is not None:
                author = clean_text(_text(node), limit=80)

        items.append(
            FeedItem(
                title=title,
                link=link.strip(),
                guid=guid,
                teaser=clean_text(teaser_raw),
                published=parse_date(date_raw),
                categories=cats,
                author=author,
                image=_extract_image(el),
                position=pos,
            )
        )
    return items
