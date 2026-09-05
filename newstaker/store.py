"""SQLite-Persistenz.

Enthaelt Schema, Upserts und alle Leseabfragen fuers Board. Bewusst ohne ORM:
das Schema ist klein und die Abfragen sollen lesbar bleiben.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from . import config

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source (
    key        TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    tier       INTEGER NOT NULL,
    lang       TEXT NOT NULL,
    home       TEXT
);

CREATE TABLE IF NOT EXISTS item (
    id            TEXT PRIMARY KEY,          -- sha256(canonical_url)
    source_key    TEXT NOT NULL REFERENCES source(key),
    canonical_url TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    teaser        TEXT NOT NULL DEFAULT '',
    published_at  TEXT NOT NULL,             -- ISO-8601 UTC
    first_seen_at TEXT NOT NULL,
    topic         TEXT NOT NULL,
    lang          TEXT NOT NULL,
    feed_url      TEXT NOT NULL,
    feed_pos      INTEGER NOT NULL DEFAULT 0,
    -- Position des Feeds in config.all_feeds(). Dieselbe Meldung steht oft in
    -- mehreren Feeds derselben Quelle (Tagesschau "index" und "ausland"), und
    -- jeder Feed bringt ein anderes Thema mit. Gewinner ist der Feed mit dem
    -- kleinsten Rang - eine Eigenschaft der Konfiguration, nicht der
    -- Verarbeitungsreihenfolge. Sonst haengt das Thema davon ab, in welcher
    -- Reihenfolge abgerufen wurde, und "fetch" und "rebuild" kaemen zu
    -- verschiedenen Ergebnissen.
    feed_rank     INTEGER NOT NULL DEFAULT 9999,
    agency        TEXT NOT NULL DEFAULT '',
    image_url     TEXT NOT NULL DEFAULT '',
    image_kind    TEXT NOT NULL DEFAULT ''   -- feed | og | tile
);

CREATE INDEX IF NOT EXISTS item_published_idx ON item(published_at DESC);
CREATE INDEX IF NOT EXISTS item_topic_idx     ON item(topic);
CREATE INDEX IF NOT EXISTS item_source_idx    ON item(source_key);

-- Gelesen-/Merk-Status liegt serverseitig, damit Mac und iPhone denselben
-- Stand sehen.
CREATE TABLE IF NOT EXISTS state (
    item_id  TEXT PRIMARY KEY REFERENCES item(id) ON DELETE CASCADE,
    read_at  TEXT,
    saved_at TEXT
);

-- Cluster werden bei jedem Rebuild vollstaendig neu berechnet.
CREATE TABLE IF NOT EXISTS cluster (
    id           TEXT PRIMARY KEY,
    lead_item_id TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    size         INTEGER NOT NULL,
    source_count INTEGER NOT NULL,
    topic        TEXT NOT NULL,
    lang         TEXT NOT NULL,
    score        REAL NOT NULL,
    built_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cluster_item (
    cluster_id TEXT NOT NULL REFERENCES cluster(id) ON DELETE CASCADE,
    item_id    TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    PRIMARY KEY (cluster_id, item_id)
);

CREATE INDEX IF NOT EXISTS cluster_item_item_idx ON cluster_item(item_id);

-- Rohantworten: macht jeden Board-Zustand rekonstruierbar und erlaubt
-- 'rebuild' ohne erneuten Netzzugriff.
CREATE TABLE IF NOT EXISTS raw_fetch (
    feed_url      TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    status        INTEGER NOT NULL,
    etag          TEXT,
    last_modified TEXT,
    sha256        TEXT NOT NULL,
    body          BLOB,
    PRIMARY KEY (feed_url, fetched_at)
);

-- Letzter bekannter Stand je Feed fuer conditional GET.
CREATE TABLE IF NOT EXISTS feed_state (
    feed_url      TEXT PRIMARY KEY,
    etag          TEXT,
    last_modified TEXT,
    sha256        TEXT,
    fetched_at    TEXT,
    status        INTEGER,
    note          TEXT
);

-- Ergebnis der og:image-Stufe, damit eine blockierte Seite nie zweimal
-- angefasst wird.
CREATE TABLE IF NOT EXISTS og_cache (
    canonical_url TEXT PRIMARY KEY,
    image_url     TEXT NOT NULL DEFAULT '',
    checked_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weather (
    city       TEXT NOT NULL,
    day        TEXT NOT NULL,
    code       INTEGER NOT NULL,
    hi         REAL NOT NULL,
    lo         REAL NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (city, day)
);

-- Stundenwerte, ausschliesslich fuer den heutigen Tag (siehe weather.py) -
-- die Detailansicht "Tagesverlauf zum Durchscrollen" braucht keine Historie.
CREATE TABLE IF NOT EXISTS weather_hour (
    city       TEXT NOT NULL,
    hour       TEXT NOT NULL,   -- ISO-Zeit, z. B. "2026-09-05T14:00"
    code       INTEGER NOT NULL,
    temp       REAL NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (city, hour)
);

CREATE TABLE IF NOT EXISTS market (
    symbol      TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,   -- 'etf' | 'stock'
    name        TEXT NOT NULL,
    price       REAL NOT NULL,
    currency    TEXT NOT NULL,
    change_pct  REAL NOT NULL,   -- Veraenderung ueber config.MARKETS_LOOKBACK_YEARS
    spark       TEXT NOT NULL DEFAULT '[]',  -- JSON-Liste, abgetastete Kursreihe fuer die Mini-Grafik
    fetched_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Der Suchindex speichert GEFALTETEN Text (normalize.fold: ae/oe/ue/ss).
-- Wichtig: die eingebaute Faltung von FTS5 (remove_diacritics) macht aus "ö"
-- ein "o", unsere aber ein "oe". Wuerden wir den Originaltext indizieren und
-- mit gefalteter Eingabe suchen, faende "Zoelle" das indizierte "zolle" nie.
-- Deshalb wird beidseitig dieselbe Faltung angewendet und der Index explizit
-- gepflegt (Trigger koennten die Python-Faltung nicht ausfuehren).
CREATE VIRTUAL TABLE IF NOT EXISTS item_fts USING fts5(
    item_id UNINDEXED,
    title,
    teaser,
    tokenize='unicode61 remove_diacritics 2'
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    config.VAR_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Nachtraeglich hinzugekommene Spalten ergaenzen.

    Haelt bestehende Datenbanken lauffaehig, ohne dass jemand var/news.db
    loeschen muss.
    """
    have = {row["name"] for row in conn.execute("PRAGMA table_info(item)")}
    if have and "feed_rank" not in have:
        conn.execute("ALTER TABLE item ADD COLUMN feed_rank INTEGER NOT NULL DEFAULT 9999")

    have_market = {row["name"] for row in conn.execute("PRAGMA table_info(market)")}
    if have_market and "spark" not in have_market:
        conn.execute("ALTER TABLE market ADD COLUMN spark TEXT NOT NULL DEFAULT '[]'")


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)
    for src in config.SOURCES:
        conn.execute(
            """INSERT INTO source(key, name, tier, lang, home) VALUES(?,?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                   name=excluded.name, tier=excluded.tier,
                   lang=excluded.lang, home=excluded.home""",
            (src["key"], src["name"], src["tier"], src["lang"], src.get("home", "")),
        )
    conn.commit()


# ------------------------------------------------------------------ Feeds


def get_feed_state(conn: sqlite3.Connection, feed_url: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM feed_state WHERE feed_url=?", (feed_url,)).fetchone()


def save_feed_state(
    conn: sqlite3.Connection,
    feed_url: str,
    *,
    etag: str | None,
    last_modified: str | None,
    sha256: str | None,
    status: int,
    note: str = "",
) -> None:
    conn.execute(
        """INSERT INTO feed_state(feed_url, etag, last_modified, sha256, fetched_at, status, note)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(feed_url) DO UPDATE SET
               etag=excluded.etag, last_modified=excluded.last_modified,
               sha256=excluded.sha256, fetched_at=excluded.fetched_at,
               status=excluded.status, note=excluded.note""",
        (feed_url, etag, last_modified, sha256, now_iso(), status, note),
    )


def save_raw(
    conn: sqlite3.Connection,
    feed_url: str,
    *,
    status: int,
    etag: str | None,
    last_modified: str | None,
    sha256: str,
    body: bytes,
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO raw_fetch(feed_url, fetched_at, status, etag, last_modified, sha256, body)
           VALUES(?,?,?,?,?,?,?)""",
        (feed_url, now_iso(), status, etag, last_modified, sha256, body),
    )


def latest_raw(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Neueste gespeicherte Rohantwort je Feed - Grundlage fuer 'rebuild'."""
    return conn.execute(
        """SELECT r.* FROM raw_fetch r
           JOIN (SELECT feed_url, MAX(fetched_at) AS m FROM raw_fetch GROUP BY feed_url) t
             ON r.feed_url = t.feed_url AND r.fetched_at = t.m
           ORDER BY r.feed_url"""
    ).fetchall()


def prune_raw(conn: sqlite3.Connection) -> int:
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=config.RAW_RETENTION_DAYS)
    ).isoformat(timespec="seconds")
    cur = conn.execute(
        """DELETE FROM raw_fetch
           WHERE fetched_at < ?
             AND (feed_url, fetched_at) NOT IN
                 (SELECT feed_url, MAX(fetched_at) FROM raw_fetch GROUP BY feed_url)""",
        (cutoff,),
    )
    return cur.rowcount


# ------------------------------------------------------------------ Items


def index_item(conn: sqlite3.Connection, item_id: str, title: str, teaser: str) -> None:
    """Haelt den Suchindex aktuell. Erwartet bereits gefalteten Text."""
    conn.execute("DELETE FROM item_fts WHERE item_id=?", (item_id,))
    conn.execute(
        "INSERT INTO item_fts(item_id, title, teaser) VALUES(?,?,?)",
        (item_id, title, teaser),
    )


def upsert_item(conn: sqlite3.Connection, item: dict[str, Any]) -> bool:
    """Legt eine Meldung an oder aktualisiert sie. True, wenn neu."""
    existing = conn.execute("SELECT id FROM item WHERE id=?", (item["id"],)).fetchone()
    if existing:
        # Titel und Teaser koennen nachtraeglich korrigiert werden, die
        # Erstsichtung bleibt stehen. feed_pos nur verbessern (kleiner = weiter
        # oben), damit ein Artikel, der in einem Feed prominent stand, seine
        # Platzierung nicht durch einen anderen Feed verliert.
        #
        # Thema und Herkunftsfeed uebernimmt nur der Feed mit dem kleineren
        # Rang - siehe Kommentar an der Spalte feed_rank. In SQLite sehen alle
        # rechten Seiten eines UPDATE die alten Werte, die Reihenfolge der
        # Zuweisungen spielt also keine Rolle.
        #
        # published_at wird nur uebernommen, wenn der Feed wirklich ein Datum
        # geliefert hat. Sonst wuerde ein Ersatzdatum bei jedem Durchlauf neu
        # gesetzt und das Board waere nicht mehr reproduzierbar.
        conn.execute(
            """UPDATE item SET
                   title=?, teaser=?,
                   published_at=CASE WHEN ? THEN ? ELSE published_at END,
                   topic=CASE WHEN ? < feed_rank THEN ? ELSE topic END,
                   feed_url=CASE WHEN ? < feed_rank THEN ? ELSE feed_url END,
                   feed_rank=MIN(feed_rank, ?),
                   feed_pos=MIN(feed_pos, ?),
                   agency=?,
                   image_url=CASE WHEN ?='' THEN image_url ELSE ? END,
                   image_kind=CASE WHEN ?='' THEN image_kind ELSE ? END
               WHERE id=?""",
            (
                item["title"], item["teaser"],
                1 if item["has_date"] else 0, item["published_at"],
                item["feed_rank"], item["topic"],
                item["feed_rank"], item["feed_url"],
                item["feed_rank"],
                item["feed_pos"], item["agency"],
                item["image_url"], item["image_url"],
                item["image_kind"], item["image_kind"],
                item["id"],
            ),
        )
        index_item(conn, item["id"], item["title_fold"], item["teaser_fold"])
        return False

    conn.execute(
        """INSERT INTO item(id, source_key, canonical_url, title, teaser, published_at,
                            first_seen_at, topic, lang, feed_url, feed_pos, feed_rank,
                            agency, image_url, image_kind)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            item["id"], item["source_key"], item["canonical_url"], item["title"],
            item["teaser"], item["published_at"], now_iso(), item["topic"],
            item["lang"], item["feed_url"], item["feed_pos"], item["feed_rank"],
            item["agency"], item["image_url"], item["image_kind"],
        ),
    )
    index_item(conn, item["id"], item["title_fold"], item["teaser_fold"])
    return True


def set_image(conn: sqlite3.Connection, item_id: str, url: str, kind: str) -> None:
    conn.execute("UPDATE item SET image_url=?, image_kind=? WHERE id=?", (url, kind, item_id))


def items_in_window(
    conn: sqlite3.Connection, hours: int, *, now: datetime | None = None
) -> list[sqlite3.Row]:
    """`now` durchreichbar: ohne das verschiebt sich das Zeitfenster bei jedem
    Aufruf um ein paar Sekunden, wodurch Meldungen an der Fensterkante zwischen
    zwei rebuild()-Laeufen rein- oder rausfallen koennen - das aendert die
    Cluster-Mitgliedschaft und damit den Board-Fingerabdruck, obwohl dieselben
    Rohdaten verarbeitet werden. Gefunden durch einen unabhaengigen Audit."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=hours)).isoformat(timespec="seconds")
    return conn.execute(
        """SELECT i.*, s.name AS source_name, s.tier AS source_tier
           FROM item i JOIN source s ON s.key = i.source_key
           WHERE i.published_at >= ?
           ORDER BY i.id""",
        # Sortierung nach id ist entscheidend: sie macht das Clustering
        # reproduzierbar, weil Union-Find in fester Reihenfolge laeuft.
        (cutoff,),
    ).fetchall()


def items_missing_image(
    conn: sqlite3.Connection, hours: int, *, now: datetime | None = None
) -> list[sqlite3.Row]:
    """`now` durchreichbar - gleicher Grund wie bei items_in_window(): sonst
    koennte ein rebuild() zwischen zwei Laeufen unterschiedliche Meldungen mit
    einer Kachel versehen, nur weil die reale Uhrzeit weitergelaufen ist."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=hours)).isoformat(timespec="seconds")
    return conn.execute(
        """SELECT i.* FROM item i
           WHERE i.published_at >= ? AND (i.image_url = '' OR i.image_kind = 'tile')
           ORDER BY i.id""",
        (cutoff,),
    ).fetchall()


# ------------------------------------------------------------------ og:image


def og_cached(conn: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM og_cache WHERE canonical_url=?", (url,)).fetchone()


def og_store(conn: sqlite3.Connection, url: str, image_url: str) -> None:
    conn.execute(
        """INSERT INTO og_cache(canonical_url, image_url, checked_at) VALUES(?,?,?)
           ON CONFLICT(canonical_url) DO UPDATE SET
               image_url=excluded.image_url, checked_at=excluded.checked_at""",
        (url, image_url, now_iso()),
    )


# ------------------------------------------------------------------ Cluster


def replace_clusters(conn: sqlite3.Connection, clusters: Iterable[dict[str, Any]]) -> int:
    conn.execute("DELETE FROM cluster_item")
    conn.execute("DELETE FROM cluster")
    built = now_iso()
    n = 0
    for cl in clusters:
        conn.execute(
            """INSERT INTO cluster(id, lead_item_id, size, source_count, topic, lang, score, built_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (cl["id"], cl["lead_item_id"], cl["size"], cl["source_count"],
             cl["topic"], cl["lang"], cl["score"], built),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO cluster_item(cluster_id, item_id) VALUES(?,?)",
            [(cl["id"], iid) for iid in cl["item_ids"]],
        )
        n += 1
    return n


def cluster_members(conn: sqlite3.Connection, cluster_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT i.*, s.name AS source_name, s.tier AS source_tier
           FROM cluster_item ci
           JOIN item i ON i.id = ci.item_id
           JOIN source s ON s.key = i.source_key
           WHERE ci.cluster_id = ?
           ORDER BY s.tier, i.published_at, i.id""",
        (cluster_id,),
    ).fetchall()


# ------------------------------------------------------------------ Status


def set_state(conn: sqlite3.Connection, item_id: str, field: str, on: bool) -> None:
    if field not in ("read", "saved"):
        raise ValueError(f"unbekanntes Statusfeld: {field}")
    column = "read_at" if field == "read" else "saved_at"
    value = now_iso() if on else None
    conn.execute(
        f"""INSERT INTO state(item_id, {column}) VALUES(?,?)
            ON CONFLICT(item_id) DO UPDATE SET {column}=excluded.{column}""",
        (item_id, value),
    )


def state_counts(conn: sqlite3.Connection) -> tuple[int, int]:
    row = conn.execute(
        """SELECT COUNT(read_at) AS r, COUNT(saved_at) AS s FROM state"""
    ).fetchone()
    return row["r"] or 0, row["s"] or 0


# ------------------------------------------------------------------ Meta


def set_meta(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


def get_meta(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


# ------------------------------------------------------------------ Wetter


def save_weather(conn: sqlite3.Connection, city: str, days: list[dict[str, Any]]) -> None:
    fetched = now_iso()
    conn.execute("DELETE FROM weather WHERE city=?", (city,))
    conn.executemany(
        "INSERT INTO weather(city, day, code, hi, lo, fetched_at) VALUES(?,?,?,?,?,?)",
        [(city, d["day"], d["code"], d["hi"], d["lo"], fetched) for d in days],
    )


def load_weather(conn: sqlite3.Connection, city: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM weather WHERE city=? ORDER BY day", (city,)
    ).fetchall()


def weather_age_minutes(conn: sqlite3.Connection, city: str) -> float | None:
    row = conn.execute(
        "SELECT MAX(fetched_at) AS f FROM weather WHERE city=?", (city,)
    ).fetchone()
    if not row or not row["f"]:
        return None
    fetched = datetime.fromisoformat(row["f"])
    return (datetime.now(timezone.utc) - fetched).total_seconds() / 60.0


def save_weather_hours(conn: sqlite3.Connection, city: str, hours: list[dict[str, Any]]) -> None:
    """Ersetzt die Stundenwerte einer Stadt (nur der heutige Tag wird gehalten)."""
    fetched = now_iso()
    conn.execute("DELETE FROM weather_hour WHERE city=?", (city,))
    conn.executemany(
        "INSERT INTO weather_hour(city, hour, code, temp, fetched_at) VALUES(?,?,?,?,?)",
        [(city, h["hour"], h["code"], h["temp"], fetched) for h in hours],
    )


def load_weather_hours(conn: sqlite3.Connection, city: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM weather_hour WHERE city=? ORDER BY hour", (city,)
    ).fetchall()


# ------------------------------------------------------------------ Maerkte


def save_markets(conn: sqlite3.Connection, etfs: list[dict[str, Any]], stocks: list[dict[str, Any]]) -> None:
    """Ersetzt den kompletten Marktstand durch einen frischen Abruf.

    Ein voller Ersatz statt Upsert je Symbol: faellt ein Titel aus der
    Kandidatenliste raus (z.B. weil er jetzt Dividende zahlt), soll er nicht
    als veralteter Datensatz liegen bleiben.
    """
    fetched = now_iso()
    conn.execute("DELETE FROM market")
    rows = [(m, "etf") for m in etfs] + [(m, "stock") for m in stocks]
    conn.executemany(
        """INSERT INTO market(symbol, kind, name, price, currency, change_pct, spark, fetched_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        [
            (
                m["symbol"], kind, m["name"], m["price"], m["currency"], m["changePct"],
                json.dumps(m.get("spark", [])), fetched,
            )
            for m, kind in rows
        ],
    )


def load_markets(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Liefert (etfs, stocks, checked_at) - jeweils schon nach Veraenderung sortiert."""
    rows = conn.execute(
        "SELECT * FROM market ORDER BY kind, change_pct DESC, symbol"
    ).fetchall()

    def to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "symbol": row["symbol"],
            "name": row["name"],
            "price": row["price"],
            "currency": row["currency"],
            "changePct": row["change_pct"],
            "spark": json.loads(row["spark"]) if row["spark"] else [],
        }

    etfs = [to_dict(r) for r in rows if r["kind"] == "etf"]
    stocks = [to_dict(r) for r in rows if r["kind"] == "stock"]
    checked_at = rows[0]["fetched_at"] if rows else ""
    return etfs, stocks, checked_at


def market_age_minutes(conn: sqlite3.Connection) -> float | None:
    row = conn.execute("SELECT MAX(fetched_at) AS f FROM market").fetchone()
    if not row or not row["f"]:
        return None
    fetched = datetime.fromisoformat(row["f"])
    return (datetime.now(timezone.utc) - fetched).total_seconds() / 60.0
