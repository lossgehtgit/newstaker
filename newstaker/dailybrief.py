"""Morning Brief: Top-5-Schlagzeilen, Zitat-Bullets, Fun Fact, Markt-Kennzahl.

Alles hier baut auf bereits geladenen Daten auf (Board-Items, Markets-Payload)
oder auf einem einmal-pro-Tag gecachten Netzabruf (Wikipedia "on this day") -
keine neue KI-generierte Zusammenfassung, nur Zitat/Auswahl/Arithmetik echter
Daten, siehe CLAUDE.md "Bewusste Nicht-Ziele".
"""

from __future__ import annotations

from datetime import datetime

from . import config, fetch, normalize, store

_SENTENCE_SPLIT_RE = None


def _split_sentences(text: str) -> list[str]:
    import re

    global _SENTENCE_SPLIT_RE
    if _SENTENCE_SPLIT_RE is None:
        _SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text.strip()) if p.strip()]
    return parts


def _teaser_bullets(title: str, teaser: str) -> list[str]:
    """Bis zu zwei woertliche Kurzausschnitte aus dem Feed-Teaser - nie
    generierter Text. Degradiert auf keine Bullets, wenn der Teaser fehlt
    oder nur den Titel wiederholt (leere Aussage waere schlimmer als keine)."""
    teaser = (teaser or "").strip()
    if not teaser:
        return []
    if normalize.fold(teaser) == normalize.fold(title or ""):
        return []
    sentences = _split_sentences(teaser)
    if not sentences:
        return []
    return sentences[:2]


def _top5(board_items: list[dict]) -> list[dict]:
    return [
        {"id": e["id"], "title": e["title"], "source": e["source"], "url": e["url"]}
        for e in board_items[:5]
    ]


def _finance_stat(markets_payload: dict, *, now: datetime) -> dict | None:
    """Eine reale, bereits berechnete Kennzahl aus etfs/stocks - je nach
    Tag-des-Jahres eine andere Ausrichtung (Tagesgewinner vs. 3J-Wachstum),
    keine neue Metrik, nur Auswahl+Formatierung."""
    pool = (markets_payload or {}).get("etfs", []) + (markets_payload or {}).get("stocks", [])
    if not pool:
        return None
    use_daily = now.timetuple().tm_yday % 2 == 0
    key = "changePctDaily" if use_daily else "changePct"
    best = max(pool, key=lambda m: m.get(key, 0))
    return {
        "label": "Bester Tages-Gewinner" if use_daily else f"Bester {config.MARKETS_LOOKBACK_YEARS}J-Wachstumstitel",
        "name": best["name"],
        "symbol": best["symbol"],
        "changePct": best.get(key, 0),
        "period": "heute" if use_daily else f"{config.MARKETS_LOOKBACK_YEARS} Jahre",
    }


def refresh(conn, *, force: bool = False) -> dict:
    """Holt den Fun Fact des Tages, wenn der Cache aelter als einen Tag ist.

    Wall-clock-Kadenz wie bei weather/markets (Netz-Frische-Frage, nicht
    Board-Determinismus) - der gecachte Fakt selbst wird ausschliesslich von
    board_payload() gelesen, das rebuild()-sicher nur die DB anfasst.
    """
    row = store.load_daily_fact(conn)
    if not force and row is not None:
        fetched = datetime.fromisoformat(row["fetched_at"])
        age_minutes = (datetime.now(fetched.tzinfo) - fetched).total_seconds() / 60.0
        if age_minutes < config.DAILY_FACT_TTL_MINUTES:
            return {"refreshed": False}

    now = datetime.now()
    url = config.DAILY_FACT_URL.format(mm=f"{now.month:02d}", dd=f"{now.day:02d}")
    payload = fetch.fetch_json(url)
    selected = (payload or {}).get("selected") or []
    if not selected:
        return {"refreshed": False, "failed": True}

    entry = selected[0]
    pages = entry.get("pages") or []
    page = pages[0] if pages else {}
    title = (page.get("titles") or {}).get("normalized") or (page.get("title") or "")
    extract = page.get("extract") or entry.get("text") or ""
    page_url = ((page.get("content_urls") or {}).get("desktop") or {}).get("page", "")
    if not extract:
        return {"refreshed": False, "failed": True}

    store.save_daily_fact(conn, f"{now.month:02d}-{now.day:02d}", title, extract, page_url)
    return {"refreshed": True}


def board_payload(conn, board_items: list[dict], markets_payload: dict, *, now: datetime) -> dict:
    """Baut die dailyBrief-Struktur fuer das Frontend. Keine Netzabrufe hier -
    das haelt build_board()/rebuild() ohne Netz reproduzierbar."""
    top5 = _top5(board_items)
    bullets = _teaser_bullets(board_items[0]["title"], board_items[0].get("teaser", "")) if board_items else []

    fact_row = store.load_daily_fact(conn)
    fact = (
        {"title": fact_row["title"], "extract": fact_row["extract"], "url": fact_row["page_url"]}
        if fact_row
        else None
    )

    return {
        "top5": top5,
        "topBullets": bullets,
        "fact": fact,
        "financeStat": _finance_stat(markets_payload, now=now),
    }
