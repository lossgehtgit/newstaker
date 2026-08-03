"""Bildbeschaffung in drei Stufen.

Liv will bei jeder Schlagzeile ein Bild. Nicht jede Quelle liefert eines, und
manche Artikelseiten sperren den Zugriff (gemessen: WSJ 401, Economist 403,
Science 403). Deshalb drei Stufen, von denen die letzte immer greift:

  1. Bild aus dem Feed          - deckt rund zwei Drittel aller Meldungen
  2. og:image der Artikelseite  - holt CNBC, Al Jazeera und Nature dazu
  3. generierte SVG-Kachel      - Rest, ohne Ausnahme

Stufe 3 uebernimmt die Diagonalschraffur, die der Entwurf 1b bereits als
Platzhalter verwendet (repeating-linear-gradient 135deg, #f4f2ee/#eae7e1).
Die Variante ergibt sich aus der id der Meldung, ist also stabil: dieselbe
Meldung bekommt immer dieselbe Kachel.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from . import config, fetch, store

_OG_PATTERNS = [
    re.compile(r"""<meta[^>]+property=["']og:image(?::url)?["'][^>]*content=["']([^"']+)["']""", re.I),
    re.compile(r"""<meta[^>]+content=["']([^"']+)["'][^>]*property=["']og:image(?::url)?["']""", re.I),
    re.compile(r"""<meta[^>]+name=["']twitter:image(?::src)?["'][^>]*content=["']([^"']+)["']""", re.I),
    re.compile(r"""<link[^>]+rel=["']image_src["'][^>]*href=["']([^"']+)["']""", re.I),
]

# Farbpaare der Kachel - alle aus der Palette des Entwurfs.
_TILE_PALETTE = [
    ("#f4f2ee", "#eae7e1"),
    ("#f1efe9", "#e6e3db"),
    ("#f5f3ef", "#ebe8e0"),
    ("#f2f0ea", "#e8e5dd"),
]


def og_image(url: str) -> str:
    """Liest og:image aus dem Kopf der Artikelseite. '' wenn nichts da ist."""
    html = fetch.fetch_text(url)
    if not html:
        return ""
    for pattern in _OG_PATTERNS:
        m = pattern.search(html)
        if m:
            candidate = m.group(1).strip()
            candidate = candidate.replace("&amp;", "&")
            if candidate.startswith("//"):
                candidate = "https:" + candidate
            if candidate.startswith(("http://", "https://")):
                return candidate
    return ""


def tile_url(item_id: str, source_name: str, topic: str) -> str:
    """URL der generierten Kachel. Wird vom Server ausgeliefert."""
    return f"/tile/{item_id}.svg?s={quote(source_name)}&t={quote(topic)}"


def render_tile(item_id: str, source_name: str, topic: str, width: int = 640, height: int = 400) -> str:
    """Erzeugt die Platzhalter-Kachel als SVG.

    Rein aus der id abgeleitet, also ohne Zufall und ohne Netzzugriff.
    """
    seed = int(item_id[:8], 16) if item_id else 0
    light, dark = _TILE_PALETTE[seed % len(_TILE_PALETTE)]
    # Streifenbreite leicht variieren, damit nicht alle Kacheln gleich wirken.
    stripe = 8 + (seed >> 4) % 5
    label = _escape(source_name.upper())
    kicker = _escape(topic.upper())

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{label}">
  <defs>
    <pattern id="h" width="{stripe * 2}" height="{stripe * 2}" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
      <rect width="{stripe * 2}" height="{stripe * 2}" fill="{light}"/>
      <rect width="{stripe}" height="{stripe * 2}" fill="{dark}"/>
    </pattern>
  </defs>
  <rect width="{width}" height="{height}" fill="url(#h)"/>
  <rect x="16" y="{height - 46}" width="{18 + len(label) * 8.2:.0f}" height="26" rx="5" fill="#ffffff" fill-opacity="0.92"/>
  <text x="25" y="{height - 28}" font-family="IBM Plex Mono, Menlo, monospace" font-size="12" letter-spacing="0.8" fill="#6f6b64">{label}</text>
  <text x="{width - 16}" y="30" text-anchor="end" font-family="IBM Plex Mono, Menlo, monospace" font-size="11" letter-spacing="1.2" fill="#a8a49c">{kicker}</text>
</svg>"""


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def backfill(conn, *, hours: int, budget: int = 40, verbose: bool = False) -> dict[str, int]:
    """Stufe 2 und 3 fuer alle Meldungen ohne echtes Bild.

    `budget` begrenzt die Zahl der Artikelseiten-Aufrufe pro Durchlauf, damit
    ein Abruf nicht minutenlang laeuft. Der Rest bekommt sofort die Kachel und
    wird beim naechsten Lauf erneut betrachtet.
    """
    stats = {"og_hit": 0, "og_miss": 0, "og_cached": 0, "tile": 0, "skipped": 0}
    rows = store.items_missing_image(conn, hours)
    spent = 0

    for row in rows:
        item_id = row["id"]
        url = row["canonical_url"]
        src = config.source_by_key(row["source_key"]) or {}
        source_name = src.get("name", row["source_key"])

        found = ""
        cached = store.og_cached(conn, url)
        if cached is not None:
            found = cached["image_url"]
            if found:
                stats["og_cached"] += 1
        elif src.get("no_og_scrape"):
            # Quelle sperrt Artikelseiten - gar nicht erst anfassen.
            store.og_store(conn, url, "")
            stats["skipped"] += 1
        elif spent < budget:
            spent += 1
            found = og_image(url)
            store.og_store(conn, url, found)
            stats["og_hit" if found else "og_miss"] += 1
            if verbose:
                mark = "+" if found else "-"
                print(f"  og {mark} {source_name}: {row['title'][:60]}")

        if found:
            store.set_image(conn, item_id, found, "og")
        elif row["image_url"] == "":
            store.set_image(conn, item_id, tile_url(item_id, source_name, row["topic"]), "tile")
            stats["tile"] += 1

    return stats
