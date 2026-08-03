"""Marktuebersicht: Tagespreis und 3-Jahres-Veraenderung, deterministisch.

Ersetzt die "Themen des Tages"-Cluster-Uebersicht oben im Board. Liv baut
langfristig Vermoegen mit nicht-dividendenzahlenden ETFs und Wachstumsaktien
auf; gezeigt werden reine, berechnete Kennzahlen aus echten Kursdaten - keine
Prognose, keine KI-Einschaetzung, keine Anlageempfehlung.

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


def _metrics_from_chart(symbol: str, chart: dict) -> dict | None:
    """Berechnet Preis und 3-Jahres-Veraenderung; None wenn nicht dividendenfrei
    oder die Datenlage zu duenn ist."""
    quote = chart.get("indicators", {}).get("quote", [{}])[0]
    closes = [c for c in quote.get("close", []) if c is not None]
    # Weniger als ~2 Handelsjahre: zu duenn fuer eine belastbare 3J-Kennzahl
    # (neu gelistete Titel, Datenluecken).
    if len(closes) < 400:
        return None

    dividend_events = chart.get("events", {}).get("dividends", {})
    if dividend_events:
        return None  # zahlt Dividende -> passt nicht zu Livs Anlagestil

    meta = chart.get("meta", {})
    change_pct = (closes[-1] / closes[0] - 1) * 100

    return {
        "symbol": symbol,
        "name": meta.get("longName") or meta.get("shortName") or symbol,
        "price": round(meta.get("regularMarketPrice", closes[-1]), 2),
        "currency": meta.get("currency", ""),
        "changePct": round(change_pct, 1),
    }


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


def refresh(conn, *, force: bool = False, verbose: bool = False) -> dict:
    """Holt Kursdaten, wenn der letzte Stand aelter als MARKETS_TTL_MINUTES ist."""
    age = store.market_age_minutes(conn)
    if not force and age is not None and age < config.MARKETS_TTL_MINUTES:
        return {"refreshed": False, "age_minutes": round(age, 1)}

    etfs = _refresh_group(config.CANDIDATE_ETFS, verbose=verbose)
    stocks = _refresh_group(config.CANDIDATE_STOCKS, verbose=verbose)
    store.save_markets(conn, etfs, stocks)
    return {"refreshed": True, "etfs": len(etfs), "stocks": len(stocks)}


def board_payload(conn) -> dict:
    """Liefert die Top-N je Kategorie fuer die Anzeige."""
    etfs, stocks, checked_at = store.load_markets(conn)
    top_etfs = etfs[: config.MARKETS_TOP_N]
    top_stocks = stocks[: config.MARKETS_TOP_N]
    return {
        "lookbackYears": config.MARKETS_LOOKBACK_YEARS,
        "checkedAt": checked_at,
        "etfs": top_etfs,
        "stocks": top_stocks,
    }
