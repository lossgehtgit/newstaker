"""Marktuebersicht: Tagespreis und 3-Jahres-Veraenderung, deterministisch.

Ersetzt die "Themen des Tages"-Cluster-Uebersicht oben im Board. Gezeigt
werden Titel ohne Dividendenausschuettung mit Wachstumsfokus - reine,
berechnete Kennzahlen aus echten Kursdaten, keine Prognose, keine
KI-Einschaetzung, keine Anlageempfehlung.

Datenquelle ist die inoffizielle Yahoo-Finance-Chart-API (kein API-Key,
funktioniert ohne Anmeldung). Das ist keine dokumentierte, garantierte
Schnittstelle - faellt sie aus, bleibt die Marktuebersicht schlicht leer
(BOARD_MAX_AGE_HOURS-Fenster gibt es hier nicht, es wird einfach der letzte
erfolgreiche Stand aus der Datenbank weiterverwendet, siehe board_payload()).

"Regelbasiert" heisst: aus config.CANDIDATE_ETFS/CANDIDATE_STOCKS faellt jeder
Titel automatisch raus, der in den letzten MARKETS_LOOKBACK_YEARS auch nur
einmal Dividende gezahlt hat - das wird bei jedem Abruf neu anhand der
tatsaechlichen Dividendenhistorie geprueft, nicht aus einer Annahme uebernommen
(Dividendenpolitik aendert sich, siehe Meta/Alphabet 2024). Von den
verbleibenden Titeln zeigt jede Box die MARKETS_TOP_N mit der groessten
3-Jahres-Kurssteigerung.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from . import config, fetch, store


def _fetch_chart(symbol: str) -> dict | None:
    """Kursverlauf + Dividendenereignisse der letzten MARKETS_LOOKBACK_YEARS."""
    url = config.YAHOO_CHART_URL.format(symbol=symbol)
    payload = fetch.fetch_json(
        url,
        {
            "range": f"{config.MARKETS_LOOKBACK_YEARS}y",
            "interval": "1d",
            "events": "div,splits",
        },
    )
    if not payload:
        return None
    results = (payload.get("chart") or {}).get("result")
    if not results:
        return None
    return results[0]


_NAME_BOILERPLATE = [
    # Reihenfolge zaehlt: laengere/spezifischere Muster zuerst, damit z.B.
    # "UCITS ETF" schon weg ist, bevor das kuerzere "ETF" alleine greifen wuerde.
    r"\bUCITS ETF\b", r"\bUCITS\b",
    r"\(Acc\)", r"\(Dist\)", r"\bAccumulating\b", r"\bDistributing\b",
    r"\(USD\)", r"\(EUR\)", r"\(GBP\)",
    r"\bUSD Acc\b", r"\bEUR Acc\b", r"\bUSD\b", r"\bEUR\b", r"\bGBP\b",
    r"\bClass A Common Stock\b", r"\bCommon Stock\b", r"\bOrdinary Shares\b",
    r"\bDepositary Receipt\b", r"\bETF\b",
    r"\bInc\.?(?=\s|$)", r"\bCorp(oration)?\.?(?=\s|$)", r"\bCo\.?(?=\s|$)",
    r"\bPLC\b", r"\bAG\b", r"\bSE\b", r"\bN\.V\.\b", r"\bLtd\.?(?=\s|$)",
    r"\([A-Z.]{1,6}\)\s*$",  # Ticker-in-Klammern am Ende, z.B. "(AAPL)"
]
_NAME_BOILERPLATE_RE = re.compile("|".join(_NAME_BOILERPLATE))


def _simplify_name(name: str) -> str:
    """Kuerzt Yahoo-Titel um verbreitetes Boilerplate (Fondsstruktur-Suffixe,
    Rechtsformen, Ticker-in-Klammern). Bewusst eine kurze Allowlist statt
    einem allgemeinen Parser - deckt die real vorkommenden Muster ab, ist
    kein Anspruch auf Vollstaendigkeit fuer beliebige Namen."""
    out = _NAME_BOILERPLATE_RE.sub("", name)
    out = re.sub(r"\s{2,}", " ", out).strip(" -,")
    return out or name


def _metrics_from_chart(
    symbol: str, chart: dict, *, require_dividend_free: bool = True, min_history: int = 400
) -> dict | None:
    """Berechnet Preis, Tages- und 3-Jahres-Veraenderung; None wenn die
    Datenlage zu duenn ist oder (falls gefordert) der Titel Dividende zahlt."""
    quote = chart.get("indicators", {}).get("quote", [{}])[0]
    closes = [c for c in quote.get("close", []) if c is not None]
    # Weniger als ~2 Handelsjahre: zu duenn fuer eine belastbare 3J-Kennzahl
    # (neu gelistete Titel, Datenluecken). Fuer den ungefilterten Suchindex
    # (min_history klein) reicht dagegen schon eine kurze Reihe fuer Preis +
    # Tagesveraenderung.
    if len(closes) < min_history:
        return None

    if require_dividend_free and chart.get("events", {}).get("dividends", {}):
        return None  # zahlt Dividende -> passt nicht zum Dividenden-Filter

    meta = chart.get("meta", {})
    change_pct = (closes[-1] / closes[0] - 1) * 100
    change_pct_daily = (closes[-1] / closes[-2] - 1) * 100 if len(closes) >= 2 else 0.0
    raw_name = meta.get("shortName") or meta.get("longName") or symbol

    return {
        "symbol": symbol,
        "name": _simplify_name(raw_name),
        "price": round(meta.get("regularMarketPrice", closes[-1]), 2),
        "currency": meta.get("currency", ""),
        "changePct": round(change_pct, 1),
        "changePctDaily": round(change_pct_daily, 1),
        "spark": _downsample(closes, config.MARKETS_SPARK_POINTS),
    }


def _downsample(values: list[float], points: int) -> list[float]:
    """Reduziert eine taegliche Kursreihe auf `points` gleichmaessig verteilte
    Stuetzstellen fuer die Mini-Grafik - Anfang und Ende bleiben immer erhalten."""
    if len(values) <= points:
        return [round(v, 2) for v in values]
    step = (len(values) - 1) / (points - 1)
    return [round(values[round(i * step)], 2) for i in range(points)]


def _refresh_group(symbols: list[str], *, verbose: bool = False) -> list[dict]:
    out = []
    for symbol in symbols:
        chart = _fetch_chart(symbol)
        if chart is None:
            if verbose:
                print(f"  markt {symbol}: nicht erreichbar")
            continue
        metrics = _metrics_from_chart(symbol, chart)
        if metrics is None:
            if verbose:
                print(f"  markt {symbol}: ausgeschlossen (Dividende oder zu wenig Historie)")
            continue
        out.append(metrics)
    out.sort(key=lambda m: (-m["changePct"], m["symbol"]))
    return out


def _refresh_search_group(symbols: list[str], *, verbose: bool = False) -> list[dict]:
    """Wie `_refresh_group`, aber ohne Dividenden-Filter und ohne 3J-Mindest-
    historie - fuer den freien Firmen-/Ticker-Suchindex (config.
    SEARCH_INDEX_STOCKS), der bewusst nicht der Wachstums-/Dividendenfrei-
    Regel unterliegt (siehe Modul-Docstring)."""
    out = []
    for symbol in symbols:
        chart = _fetch_chart(symbol)
        if chart is None:
            if verbose:
                print(f"  suche {symbol}: nicht erreichbar")
            continue
        metrics = _metrics_from_chart(symbol, chart, require_dividend_free=False, min_history=2)
        if metrics is None:
            if verbose:
                print(f"  suche {symbol}: zu wenig Historie")
            continue
        out.append(metrics)
    out.sort(key=lambda m: m["symbol"])
    return out


def refresh(conn, *, force: bool = False, verbose: bool = False) -> dict:
    """Holt Kursdaten, wenn der letzte Stand aelter als MARKETS_TTL_MINUTES ist."""
    age = store.market_age_minutes(conn)
    if not force and age is not None and age < config.MARKETS_TTL_MINUTES:
        return {"refreshed": False, "age_minutes": round(age, 1)}

    etfs = _refresh_group(config.CANDIDATE_ETFS, verbose=verbose)
    stocks = _refresh_group(config.CANDIDATE_STOCKS, verbose=verbose)
    search = _refresh_search_group(config.SEARCH_INDEX_STOCKS, verbose=verbose)

    # Faellt Yahoo komplett aus (Sperre, Formataenderung, Netzwerkfehler),
    # liefern beide Gruppen eine leere Liste. Ein unbedingtes save_markets()
    # wuerde dann per DELETE+INSERT den zuletzt erfolgreichen Marktstand
    # ersatzlos loeschen, obwohl keine neuen Daten da sind - genau das
    # Gegenteil vom im Modul-Docstring versprochenen Verhalten ("bleibt
    # einfach der letzte erfolgreiche Stand stehen"). Gefunden durch einen
    # unabhaengigen Audit. Bei Totalausfall bleibt der alte Stand deshalb
    # unangetastet. `search` bekommt dieselbe Behandlung, aber unabhaengig
    # von etfs/stocks (store.save_markets ersetzt beide Gruppen getrennt):
    # faellt nur die breitere Suchliste aus, bleibt der alte Suchindex
    # stehen, auch wenn etfs/stocks frisch sind (und umgekehrt).
    if not etfs and not stocks and not search:
        return {"refreshed": False, "etfs": 0, "stocks": 0, "search": 0, "failed": True}

    store.save_markets(conn, etfs, stocks, search if search else None)
    return {"refreshed": True, "etfs": len(etfs), "stocks": len(stocks), "search": len(search)}


def board_payload(conn) -> dict:
    """Liefert die Top-N je Kategorie fuer die Anzeige, plus den ungekappten,
    ungefilterten Suchindex fuer die Freitext-Suche im Frontend."""
    etfs, stocks, search, checked_at = store.load_markets(conn)
    top_etfs = etfs[: config.MARKETS_TOP_N]
    top_stocks = stocks[: config.MARKETS_TOP_N]
    return {
        "lookbackYears": config.MARKETS_LOOKBACK_YEARS,
        "checkedAt": checked_at,
        "etfs": top_etfs,
        "stocks": top_stocks,
        "searchIndex": search,
    }
