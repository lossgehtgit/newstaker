#!/usr/bin/env python3
"""News-Taker - Kommandozeile.

    python3 run.py init      Datenbank anlegen
    python3 run.py fetch     Feeds abrufen, Bilder, Cluster, Wetter
    python3 run.py serve     Board ausliefern
    python3 run.py rebuild   Neu berechnen aus gespeicherten Rohantworten
    python3 run.py export    Statischen Export nach docs/ schreiben (fuer GitHub Pages)
    python3 run.py status    Kurzer Zustandsbericht
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from newstaker import config, export, pipeline, server, store


def cmd_init(args: argparse.Namespace) -> int:
    conn = store.connect()
    store.init(conn)
    feeds = len(config.all_feeds())
    print(f"Datenbank angelegt: {config.DB_PATH}")
    print(f"{len(config.SOURCES)} Quellen, {feeds} Feeds registriert")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    conn = store.connect()
    store.init(conn)
    result = pipeline.refresh(
        conn, verbose=args.verbose, force=args.force, image_budget=args.image_budget
    )
    feeds = result["feeds"]
    failures = feeds.get("failures", [])

    print()
    print(f"Feeds       {feeds['ok']} geladen, {feeds['unchanged']} unveraendert, "
          f"{feeds['failed']} fehlgeschlagen (von {feeds['feeds']})")
    print(f"Meldungen   {feeds['items']} gesehen, {feeds['new']} neu")
    img = result["images"]
    print(f"Bilder      og-Treffer {img['og_hit']}, og-Fehlschlaege {img['og_miss']}, "
          f"Kacheln {img['tile']}, uebersprungen {img['skipped']}")
    cl = result["clusters"]
    print(f"Cluster     {cl['clusters']} gesamt, {cl['multi_source']} mit mehreren Quellen, "
          f"groesster {cl['largest']} Quellen")
    print(f"Wetter      {result['weather'].get('cities', 0)} Staedte aktualisiert")

    if failures:
        print("\nNicht erreichbar:")
        for line in failures:
            print(f"  {line}")
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    conn = store.connect()
    store.init(conn)
    # "rebuild" reprozessiert ausschliesslich bereits gespeicherte Rohdaten
    # (kein neuer Fetch) - der sinnvolle Bezugspunkt fuer die Aktualitaets-
    # Komponente des Rankings ist deshalb der Zeitpunkt des letzten
    # tatsaechlichen Abrufs, nicht der Moment, in dem dieser Befehl gerade
    # getippt wird. Ein blosses `datetime.now()` je Aufruf reicht NICHT: ein
    # unabhaengiger Audit fand, dass schon 17 Sekunden Abstand zwischen zwei
    # Laeufen die Sortierreihenfolge kippen (Recency-Score nahe beieinander
    # liegender Meldungen), obwohl now= innerhalb jedes einzelnen Aufrufs
    # bereits konsistent durchgereicht wurde - vier echte CLI-Laeufe
    # hintereinander ergaben trotzdem vier verschiedene Fingerabdruecke.
    # Verankert an last_fetch_at bleibt der Bezugspunkt stabil, solange
    # zwischen zwei rebuild-Aufrufen kein neuer fetch/refresh lief - genau
    # das Szenario, das die README-Zusicherung ("zweimal denselben
    # Fingerabdruck") tatsaechlich meint. Fehlt last_fetch_at (frisch
    # angelegte Datenbank, noch nie abgerufen), bleibt nur die reale Uhrzeit
    # als Rueckfallwert.
    last_fetch = store.get_meta(conn, "last_fetch_at")
    now = datetime.fromisoformat(last_fetch) if last_fetch else datetime.now(timezone.utc)
    result = pipeline.rebuild(conn, now=now)
    board = pipeline.build_board(conn, now=now)
    print(f"Neu eingelesen: {result['ingest']['feeds']} Feeds, {result['ingest']['items']} Meldungen")
    print(f"Cluster: {result['clusters']['clusters']} "
          f"({result['clusters']['multi_source']} mit mehreren Quellen)")
    print(f"Board-Fingerabdruck: {pipeline.board_digest(board)}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    conn = store.connect()
    store.init(conn)
    result = export.run(
        conn, fetch_first=not args.no_fetch, image_budget=args.image_budget, verbose=args.verbose
    )

    if "refresh" in result:
        feeds = result["refresh"]["feeds"]
        print(f"Feeds       {feeds['ok']} geladen, {feeds['unchanged']} unveraendert, "
              f"{feeds['failed']} fehlgeschlagen (von {feeds['feeds']})")
        for line in feeds.get("failures", []):
            print(f"  Nicht erreichbar: {line}")

    ex = result["export"]
    print(f"Export      {ex['board_items']} Meldungen, {ex['search_items']} im Suchindex, "
          f"{ex['tiles_written']} neue Kacheln")
    print(f"Ziel        {export.DOCS_DIR}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    conn = store.connect()
    store.init(conn)
    count = conn.execute("SELECT COUNT(*) c FROM item").fetchone()["c"]
    if count == 0:
        print("Noch keine Meldungen in der Datenbank.")
        print("Erst einmal abrufen:  python3 run.py fetch")
        print()
    conn.close()
    server.serve(args.host, args.port)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    conn = store.connect()
    store.init(conn)
    items = conn.execute("SELECT COUNT(*) c FROM item").fetchone()["c"]
    clusters = conn.execute("SELECT COUNT(*) c FROM cluster WHERE source_count>1").fetchone()["c"]
    read, saved = store.state_counts(conn)
    print(f"Datenbank      {config.DB_PATH}")
    print(f"Letzter Abruf  {store.get_meta(conn, 'last_fetch_at', 'noch nie')}")
    print(f"Meldungen      {items}")
    print(f"Cluster        {clusters} mit mehreren Quellen")
    print(f"Status         {read} gelesen, {saved} gemerkt")

    print("\nFeeds mit Problemen:")
    rows = conn.execute(
        "SELECT feed_url, status, note FROM feed_state WHERE status <> 200 AND status <> 304"
    ).fetchall()
    if not rows:
        print("  keine")
    for row in rows:
        print(f"  {row['status']:>4}  {row['feed_url']}  {row['note']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run.py", description="News-Taker - deterministischer Newstracker"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Datenbank anlegen").set_defaults(func=cmd_init)

    p_fetch = sub.add_parser("fetch", help="Feeds abrufen und Board neu berechnen")
    p_fetch.add_argument("-v", "--verbose", action="store_true", help="Tabelle je Feed ausgeben")
    p_fetch.add_argument("--force", action="store_true", help="Caching ignorieren")
    p_fetch.add_argument("--image-budget", type=int, default=40,
                         help="Maximale Zahl an Artikelseiten-Aufrufen fuer og:image")
    p_fetch.set_defaults(func=cmd_fetch)

    p_rebuild = sub.add_parser("rebuild", help="Neu berechnen ohne Netzzugriff")
    p_rebuild.set_defaults(func=cmd_rebuild)

    p_export = sub.add_parser("export", help="Statischen Export nach docs/ schreiben")
    p_export.add_argument("--no-fetch", action="store_true", help="Nur exportieren, nicht neu abrufen")
    p_export.add_argument("--image-budget", type=int, default=60)
    p_export.add_argument("-v", "--verbose", action="store_true")
    p_export.set_defaults(func=cmd_export)

    p_serve = sub.add_parser("serve", help="Board ausliefern")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.set_defaults(func=cmd_serve)

    sub.add_parser("status", help="Zustandsbericht").set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
