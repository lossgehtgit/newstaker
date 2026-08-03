"""Statischer Export fuer GitHub Pages.

Der Cloud-Weg: GitHub Actions ruft periodisch `run.py fetch` und `run.py
export` auf einem Runner auf, der nicht schlaeft. Das Ergebnis landet als
JSON und vorgerenderte Bild-Kacheln unter docs/ und wird von dort als
statische Seite ausgeliefert - kein Server, kein wacher Mac noetig.

Zwei Dinge aendern sich dadurch gegenueber dem lokalen Live-Server:

  1. Themen-/Cluster-Filter und "Gelesene ausblenden" laufen im Browser statt
     als Serverabfrage. Deshalb exportiert board.json ALLE Meldungen im
     Zeitfenster (nicht nur die 120 des sichtbaren Boards) - das Frontend
     filtert und begrenzt selbst.
  2. Gelesen/Gemerkt kann nicht mehr serverseitig gespeichert werden, denn
     eine statische Seite hat keinen Schreibzugriff. Der Status liegt jetzt
     in localStorage je Geraet - Mac und iPhone sehen ihn dann nicht mehr
     synchron, dafuer braucht es keinen Server mehr.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, images, markets, pipeline, store, weather

DOCS_DIR = config.ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"
TILES_DIR = DOCS_DIR / "tiles"


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # sort_keys, damit sich in git nur die tatsaechlich geaenderten Werte
    # zeigen, nicht auch noch die Schluesselreihenfolge.
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
        encoding="utf-8",
    )


def _uncapped_board(conn, *, now: datetime) -> dict:
    """Wie pipeline.build_board(), aber ohne die 120er-Deckelung.

    Der Server deckelt, weil eine Live-Seite nicht 700 Eintraege auf einmal
    ausliefern muss - fuer den statischen Export soll aber alles drin sein,
    damit Themen-Pills und Cluster-Filter im Browser echte Zahlen zeigen.
    """
    original_limit = config.BOARD_LIMIT
    config.BOARD_LIMIT = 100_000
    try:
        return pipeline.build_board(conn, now=now)
    finally:
        config.BOARD_LIMIT = original_limit


def export_board(conn, *, now: datetime) -> dict:
    """Flache, vollstaendig sortierte Meldungsliste plus Themenzaehler.

    Anders als beim Live-Server entscheidet hier der Browser ueber Themen-,
    Cluster- und Gelesen-Filter - die Werkzeuge dafuer muss er selbst
    mitbringen. `items` ist daher die komplette, nach Score sortierte Liste
    (das ist exakt `leads + briefs` unmittelbar vor der servertypischen
    Kappung); jede weitere Ableitung (Aufmacher, Kurzmeldungen, Cluster-
    Uebersicht, Statuszeile) berechnet app.js daraus - in derselben
    Reihenfolge, in der auch pipeline.build_board() filtert: erst Cluster,
    dann Thema, dann Gelesen-Status, danach die ersten drei als Aufmacher.

    `topics`-Zaehler bleiben dagegen absichtlich serverseitig vorberechnet:
    sie sind laut pipeline.build_board() ohnehin unabhaengig von jedem Filter
    (gezaehlt wird immer ueber den vollen Bestand), muessen also nicht bei
    jeder Filteraenderung im Browser neu ermittelt werden.
    """
    full = _uncapped_board(conn, now=now)
    items = full["leads"] + full["briefs"]
    for entry in items:
        entry.pop("read", None)
        entry.pop("saved", None)
    _rewrite_tile_urls(items)
    return {
        "generatedAt": full["generatedAt"],
        "lastFetchAt": full["lastFetchAt"],
        "items": items,
        "topics": full["topics"],
    }


def export_search_index(conn, *, hours: int = 24 * 7) -> list[dict]:
    """Archiv fuer die Volltextsuche - reicht weiter zurueck als das Board.

    Liv soll auch eine Meldung von vorgestern wiederfinden, auch wenn sie
    nicht mehr auf der Startseite steht.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    rows = conn.execute(
        """SELECT i.*, s.name AS source_name, s.tier AS source_tier,
                  st.read_at, st.saved_at
           FROM item i
           JOIN source s ON s.key = i.source_key
           LEFT JOIN state st ON st.item_id = i.id
           WHERE i.published_at >= ?
           ORDER BY i.published_at DESC""",
        (cutoff,),
    ).fetchall()
    now = datetime.now(timezone.utc)
    out = []
    for row in rows:
        entry = pipeline._item_payload(row, now)
        out.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "teaser": entry["teaser"],
                "url": entry["url"],
                "source": entry["source"],
                "topic": entry["topic"],
                "topicLabel": entry["topicLabel"],
                "kicker": entry["kicker"],
                "image": entry["image"],
                "meta": entry["meta"],
                "dateShort": entry["dateShort"],
                "time": entry["time"],
                "publishedAt": row["published_at"],
            }
        )
    return out


def export_tiles(conn, *, hours: int) -> int:
    """Rendert fuer jede Meldung mit Kachel-Bild eine SVG-Datei unter docs/tiles/.

    Ohne Server kann niemand /tile/<id>.svg mehr auf Zuruf erzeugen - die
    Dateien muessen beim Export als echte Dateien vorliegen.
    """
    TILES_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    rows = conn.execute(
        """SELECT i.id, i.topic, i.image_kind, s.name AS source_name
           FROM item i JOIN source s ON s.key = i.source_key
           WHERE i.published_at >= ? AND i.image_kind = 'tile'""",
        (cutoff,),
    ).fetchall()
    written = 0
    keep_ids = set()
    for row in rows:
        keep_ids.add(row["id"])
        path = TILES_DIR / f"{row['id']}.svg"
        if path.exists():
            continue  # aus id abgeleitet, also stabil - kein erneutes Schreiben noetig
        svg = images.render_tile(row["id"], row["source_name"], row["topic"])
        path.write_text(svg, encoding="utf-8")
        written += 1

    # Ohne Aufraeumen wuerde dieser Ordner ueber Monate von Cron-Laeufen
    # unbegrenzt wachsen - jede Meldung, die je eine Kachel brauchte, bliebe
    # fuer immer als Datei liegen und im Git-Verlauf. Alles ausserhalb des
    # Suchindex-Fensters (7 Tage) fliegt raus.
    removed = 0
    for path in TILES_DIR.glob("*.svg"):
        if path.stem not in keep_ids:
            path.unlink()
            removed += 1
    if removed:
        print(f"  {removed} veraltete Kacheln entfernt")
    return written


def _rewrite_tile_urls(entries: list[dict]) -> None:
    """/tile/<id>.svg?... -> relativer Pfad tiles/<id>.svg fuer die statische Seite."""
    for entry in entries:
        if entry.get("imageKind") == "tile" or (
            entry.get("image", "").startswith("/tile/")
        ):
            entry["image"] = f"tiles/{entry['id']}.svg"
        others = entry.get("cluster", {}).get("others") or []
        for other in others:
            if other.get("image", "").startswith("/tile/"):
                other["image"] = f"tiles/{other['id']}.svg"


def export_weather(conn) -> dict:
    return {city: weather.board_payload(conn, city) for city in config.CITIES}


def run(conn, *, fetch_first: bool = True, image_budget: int = 60, verbose: bool = False) -> dict:
    """Kompletter Exportlauf: optional abrufen, dann alles unter docs/ ablegen."""
    summary: dict = {}
    if fetch_first:
        summary["refresh"] = pipeline.refresh(conn, verbose=verbose, image_budget=image_budget)

    now = datetime.now(timezone.utc)
    board = export_board(conn, now=now)

    search_index = export_search_index(conn)
    _rewrite_tile_urls(search_index)

    tiles_written = export_tiles(conn, hours=24 * 7)

    meta = {
        "generatedAt": now.isoformat(timespec="seconds"),
        "lastFetchAt": store.get_meta(conn, "last_fetch_at", ""),
        "mode": "static",
    }

    _write_json(DATA_DIR / "board.json", board)
    _write_json(DATA_DIR / "search.json", search_index)
    _write_json(DATA_DIR / "weather.json", export_weather(conn))
    _write_json(DATA_DIR / "markets.json", markets.board_payload(conn))
    _write_json(DATA_DIR / "meta.json", meta)

    summary["export"] = {
        "board_items": len(board["items"]),
        "search_items": len(search_index),
        "tiles_written": tiles_written,
        "generated_at": meta["generatedAt"],
    }
    return summary
