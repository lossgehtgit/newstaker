"""Morning Brief: Top-5-Schlagzeilen, Fun Fact, Markt-Kennzahl.

Top-5 und die Markt-Kennzahl bauen auf bereits geladenen Daten auf
(Board-Items, Markets-Payload). Der Fun Fact kommt aus config.DAILY_FACTS,
einer von Hand geschriebenen, geprueften Liste - kein Netzabruf, kein
KI-generierter Text zur Laufzeit, siehe CLAUDE.md "Bewusste Nicht-Ziele".
"""

from __future__ import annotations

from datetime import datetime

from . import config


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


def _fact_of_the_day(*, now: datetime) -> dict:
    """Waehlt deterministisch nach Tag-des-Jahres aus config.DAILY_FACTS -
    kein Zufall, kein Netzabruf, damit rebuild() ohne Netz reproduzierbar
    bleibt (dieselbe Eingabe liefert immer denselben Fakt)."""
    facts = config.DAILY_FACTS
    entry = facts[now.timetuple().tm_yday % len(facts)]
    return {"title": entry["title"], "extract": entry["text"]}


def board_payload(board_items: list[dict], markets_payload: dict, *, now: datetime) -> dict:
    """Baut die dailyBrief-Struktur fuer das Frontend. Kein Netzabruf hier -
    das haelt build_board()/rebuild() ohne Netz reproduzierbar."""
    return {
        "top5": _top5(board_items),
        "fact": _fact_of_the_day(now=now),
        "financeStat": _finance_stat(markets_payload, now=now),
    }
