"""Ablauf: abrufen -> einlesen -> clustern -> ranken -> Board bauen.

Jede Stufe ist idempotent. `rebuild` arbeitet ausschliesslich auf den bereits
gespeicherten Rohantworten und braucht kein Netz - das ist die Grundlage des
Determinismus-Tests: zweimal rebuild auf demselben Stand muss dieselbe
Board-JSON ergeben.
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timedelta, timezone

from . import cluster, config, feedparse, fetch, images, markets, normalize, rank, store, weather


# --------------------------------------------------------------- Einlesen


def _feed_ranks() -> dict[str, int]:
    """Rang jedes Feeds = seine Position in config.all_feeds().

    Damit entscheidet die Konfiguration und nicht die Abrufreihenfolge, welches
    Thema eine Meldung bekommt, die in mehreren Feeds derselben Quelle steht.
    """
    return {url: i for i, (_, url, _) in enumerate(config.all_feeds())}


def ingest_feed(conn, src: dict, feed_url: str, feed_topic: str, body: bytes) -> dict[str, int]:
    """Verarbeitet eine Feed-Antwort in Datenbankzeilen."""
    stats = {"items": 0, "new": 0, "skipped": 0, "with_image": 0}
    feed_rank = _feed_ranks().get(feed_url, 9999)
    for entry in feedparse.parse(body):
        canonical = normalize.canonical_url(entry.link)
        if not canonical:
            stats["skipped"] += 1
            continue

        published = entry.published
        has_date = published is not None
        if published is None:
            # Ohne Datum koennen wir weder Fenster noch Recency bestimmen;
            # wir nehmen den Abrufzeitpunkt, markieren das aber nicht als
            # Publikationszeit einer aelteren Meldung.
            published = datetime.now(timezone.utc)
        # Feeds mit fehlerhaften Zukunftsdaten nicht nach oben spuelen lassen.
        now = datetime.now(timezone.utc)
        if published > now + timedelta(hours=6):
            published = now

        record = {
            "id": normalize.item_id(canonical),
            "source_key": src["key"],
            "canonical_url": canonical,
            "title": entry.title,
            "teaser": entry.teaser,
            # Gefaltete Varianten fuer den Suchindex - dieselbe Faltung, die
            # auch das Clustering benutzt.
            "title_fold": normalize.fold(entry.title),
            "teaser_fold": normalize.fold(entry.teaser),
            "published_at": published.astimezone(timezone.utc).isoformat(timespec="seconds"),
            "has_date": has_date,
            "topic": normalize.topic_for_item(feed_topic, entry.categories),
            "lang": src["lang"],
            "feed_url": feed_url,
            "feed_pos": entry.position,
            "feed_rank": feed_rank,
            "agency": normalize.agency_from(entry.author, entry.teaser),
            "image_url": entry.image,
            "image_kind": "feed" if entry.image else "",
        }
        if store.upsert_item(conn, record):
            stats["new"] += 1
        stats["items"] += 1
        if entry.image:
            stats["with_image"] += 1
    return stats


def fetch_all(conn, *, verbose: bool = False, force: bool = False) -> dict:
    """Holt alle Feeds und schreibt Rohantworten plus Meldungen fort."""
    summary = {"feeds": 0, "ok": 0, "unchanged": 0, "failed": 0, "items": 0, "new": 0}
    failures: list[str] = []

    if verbose:
        print(f"{'QUELLE':<17}{'FEED':<44}{'HTTP':>5}{'ITEMS':>7}{'NEU':>6}{'BILD':>6}")
        print("-" * 85)

    for src, feed_url, feed_topic in config.all_feeds():
        summary["feeds"] += 1
        prev = store.get_feed_state(conn, feed_url)
        result = fetch.fetch(
            feed_url,
            etag=None if force else (prev["etag"] if prev else None),
            last_modified=None if force else (prev["last_modified"] if prev else None),
            known_sha=prev["sha256"] if prev else None,
        )

        if result.not_modified or (result.ok and not result.changed and not force):
            summary["unchanged"] += 1
            store.save_feed_state(
                conn, feed_url, etag=result.etag or (prev["etag"] if prev else None),
                last_modified=result.last_modified or (prev["last_modified"] if prev else None),
                sha256=result.sha256 or (prev["sha256"] if prev else None),
                status=result.status or 304, note="unveraendert",
            )
            if verbose:
                short = feed_url.split("/", 3)[-1][:42]
                print(f"{src['name'][:16]:<17}{short:<44}{'304':>5}{'-':>7}{'-':>6}{'-':>6}")
            continue

        if not result.ok:
            summary["failed"] += 1
            failures.append(f"{src['name']} {feed_url} -> {result.error or result.status}")
            store.save_feed_state(
                conn, feed_url, etag=None, last_modified=None,
                sha256=prev["sha256"] if prev else None,
                status=result.status, note=result.error,
            )
            if verbose:
                short = feed_url.split("/", 3)[-1][:42]
                print(f"{src['name'][:16]:<17}{short:<44}{result.status:>5}{'-':>7}{'-':>6}{'-':>6}  {result.error[:26]}")
            continue

        store.save_raw(
            conn, feed_url, status=result.status, etag=result.etag,
            last_modified=result.last_modified, sha256=result.sha256, body=result.body,
        )
        store.save_feed_state(
            conn, feed_url, etag=result.etag, last_modified=result.last_modified,
            sha256=result.sha256, status=result.status, note="",
        )
        stats = ingest_feed(conn, src, feed_url, feed_topic, result.body)
        summary["ok"] += 1
        summary["items"] += stats["items"]
        summary["new"] += stats["new"]
        conn.commit()

        if verbose:
            short = feed_url.split("/", 3)[-1][:42]
            print(
                f"{src['name'][:16]:<17}{short:<44}{result.status:>5}"
                f"{stats['items']:>7}{stats['new']:>6}{stats['with_image']:>6}"
            )

    summary["failures"] = failures
    conn.commit()
    return summary


def reingest_from_raw(conn) -> dict:
    """Liest alle gespeicherten Rohantworten erneut ein - ohne Netzzugriff."""
    lookup = {feed_url: (src, topic) for src, feed_url, topic in config.all_feeds()}
    summary = {"feeds": 0, "items": 0, "new": 0}
    for row in store.latest_raw(conn):
        entry = lookup.get(row["feed_url"])
        if entry is None:
            continue
        src, topic = entry
        stats = ingest_feed(conn, src, row["feed_url"], topic, row["body"])
        summary["feeds"] += 1
        summary["items"] += stats["items"]
        summary["new"] += stats["new"]
    conn.commit()
    return summary


# --------------------------------------------------------------- Clustern


def rebuild_clusters(conn) -> dict:
    rows = store.items_in_window(conn, config.CLUSTER_WINDOW_HOURS)
    docs = cluster.docs_from_rows(rows)
    clusters = cluster.build(docs)

    by_id = {row["id"]: row for row in rows}
    now = datetime.now(timezone.utc)

    for cl in clusters:
        lead = by_id[cl["lead_item_id"]]
        cl["score"] = rank.score(
            tier=lead["source_tier"],
            source_count=cl["source_count"],
            feed_pos=lead["feed_pos"],
            published_at=datetime.fromisoformat(lead["published_at"]),
            topic=cl["topic"],
            now=now,
        )

    written = store.replace_clusters(conn, clusters)
    multi = sum(1 for c in clusters if c["source_count"] > 1)
    store.set_meta(conn, "clusters_built_at", store.now_iso())
    conn.commit()
    return {
        "items": len(rows),
        "clusters": written,
        "multi_source": multi,
        "largest": max((c["source_count"] for c in clusters), default=0),
    }


def refresh(conn, *, verbose: bool = False, force: bool = False, image_budget: int = 40) -> dict:
    """Vollstaendiger Durchlauf: Feeds, Bilder, Cluster, Wetter."""
    feeds = fetch_all(conn, verbose=verbose, force=force)
    img = images.backfill(conn, hours=config.BOARD_MAX_AGE_HOURS, budget=image_budget, verbose=verbose)
    conn.commit()
    clusters = rebuild_clusters(conn)
    wx = weather.refresh(conn, force=force)
    mk = markets.refresh(conn, force=force, verbose=verbose)
    store.prune_raw(conn)
    store.set_meta(conn, "last_fetch_at", store.now_iso())
    conn.commit()
    return {"feeds": feeds, "images": img, "clusters": clusters, "weather": wx, "markets": mk}


def rebuild(conn) -> dict:
    """Neuaufbau ohne Netz: Rohantworten erneut einlesen, dann clustern."""
    ing = reingest_from_raw(conn)
    # Stufe 3 der Bildlogik ohne Netzzugriff (budget=0 unterbindet og:image).
    img = images.backfill(conn, hours=config.BOARD_MAX_AGE_HOURS, budget=0)
    conn.commit()
    clusters = rebuild_clusters(conn)
    return {"ingest": ing, "images": img, "clusters": clusters}


# --------------------------------------------------------------- Board


def _fmt_meta(row, agency: str, source_name: str) -> str:
    published = datetime.fromisoformat(row["published_at"]).astimezone()
    base = f"{source_name} · {published.strftime('%d.%m.%Y')} · {published.strftime('%H:%M')}"
    return f"{base} · {agency}" if agency else base


def build_board(
    conn,
    *,
    topic: str = "",
    hide_read: bool = False,
    cluster_id: str = "",
    now: datetime | None = None,
) -> dict:
    """Baut die Board-Struktur, die das Frontend rendert.

    `now` ist die einzige Groesse, die sich zwischen zwei Aufrufen mit
    demselben Datenbestand aendern kann - die Aktualitaetskomponente des
    Rankings haengt daran. Fuer Reproduzierbarkeitspruefungen laesst sie sich
    deshalb festhalten.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=config.BOARD_MAX_AGE_HOURS)).isoformat(timespec="seconds")

    rows = conn.execute(
        """SELECT i.*, s.name AS source_name, s.tier AS source_tier,
                  st.read_at, st.saved_at,
                  c.id AS cluster_id, c.source_count, c.size AS cluster_size,
                  c.score, c.topic AS cluster_topic
           FROM item i
           JOIN source s ON s.key = i.source_key
           LEFT JOIN state st ON st.item_id = i.id
           LEFT JOIN cluster_item ci ON ci.item_id = i.id
           LEFT JOIN cluster c ON c.id = ci.cluster_id
           WHERE i.published_at >= ?
           ORDER BY i.id""",
        (cutoff,),
    ).fetchall()

    # Je Cluster nur den Aufmacher zeigen; die uebrigen Mitglieder haengen als
    # Quellenliste daran.
    leads: dict[str, dict] = {}
    extras: dict[str, list[dict]] = {}

    for row in rows:
        cid = row["cluster_id"] or f"solo:{row['id']}"
        entry = _item_payload(row, now)
        # Bei einem Cluster gilt das Mehrheitsthema der Gruppe, nicht das
        # Ressort des Aufmachers: die Paramount-Uebernahme ist Wirtschaft,
        # auch wenn sie beim Handelsblatt im Technologie-Feed steht.
        if row["cluster_topic"]:
            entry["topic"] = row["cluster_topic"]
            label = config.TOPIC_LABELS.get(row["cluster_topic"], row["cluster_topic"])
            entry["topicLabel"] = label
            entry["kicker"] = label.upper()
        lead_row = leads.get(cid)
        if lead_row is None:
            leads[cid] = entry
            extras[cid] = []
        else:
            # Aufmacher ist der mit besserem Tier, dann frueher, dann id.
            challenger = (row["source_tier"], row["published_at"], row["id"])
            champion = (lead_row["_tier"], lead_row["_published"], lead_row["id"])
            if challenger < champion:
                extras[cid].append(lead_row)
                leads[cid] = entry
            else:
                extras[cid].append(entry)

    items: list[dict] = []
    for cid, entry in leads.items():
        others = sorted(extras[cid], key=lambda e: (e["_tier"], e["_published"], e["id"]))
        entry["cluster"] = {
            "id": cid if not cid.startswith("solo:") else "",
            "sourceCount": len({entry["source"]} | {o["source"] for o in others}),
            "size": 1 + len(others),
            "sources": _unique([entry["source"]] + [o["source"] for o in others]),
            "others": [_strip_private(o) for o in others],
        }
        entry["score"] = rank.score(
            tier=entry["_tier"],
            source_count=entry["cluster"]["sourceCount"],
            feed_pos=entry["_pos"],
            published_at=datetime.fromisoformat(entry["_published"]),
            topic=entry["topic"],
            now=now,
        )
        items.append(entry)

    items.sort(key=lambda e: (-e["score"], e["_published"], e["id"]))

    total_before_filter = len(items)
    if cluster_id:
        items = [e for e in items if e["cluster"]["id"] == cluster_id]
    if topic:
        items = [e for e in items if e["topic"] == topic]
    if hide_read:
        items = [e for e in items if not e["read"]]

    strip = _cluster_strip(items)
    items = items[: config.BOARD_LIMIT]
    payload_items = [_strip_private(e) for e in items]

    read_count, saved_count = store.state_counts(conn)
    counts = {t: 0 for t in config.TOPICS}
    for entry in leads.values():
        if entry["topic"] in counts:
            counts[entry["topic"]] += 1

    return {
        "generatedAt": now.isoformat(timespec="seconds"),
        "lastFetchAt": store.get_meta(conn, "last_fetch_at", ""),
        "leads": payload_items[: config.LEAD_COUNT],
        "briefs": payload_items[config.LEAD_COUNT :],
        "clusterStrip": strip,
        "topics": [
            {"key": t, "label": config.TOPIC_LABELS[t], "count": counts.get(t, 0)}
            for t in config.TOPICS
        ],
        "activeTopic": topic,
        "activeCluster": cluster_id,
        "hideRead": hide_read,
        "stats": {
            "total": total_before_filter,
            "shown": len(payload_items),
            "read": read_count,
            "saved": saved_count,
            "sources": len({e["source"] for e in leads.values()}),
        },
    }


def _item_payload(row, now: datetime) -> dict:
    published = datetime.fromisoformat(row["published_at"])
    local = published.astimezone()
    agency = row["agency"] or ""
    return {
        "id": row["id"],
        "title": row["title"],
        "teaser": row["teaser"],
        "url": row["canonical_url"],
        "source": row["source_name"],
        "agency": agency,
        "topic": row["topic"],
        "topicLabel": config.TOPIC_LABELS.get(row["topic"], row["topic"]),
        "kicker": config.TOPIC_LABELS.get(row["topic"], row["topic"]).upper(),
        "image": row["image_url"],
        "imageKind": row["image_kind"],
        "meta": _fmt_meta(row, agency, row["source_name"]),
        "dateShort": local.strftime("%d.%m."),
        "time": local.strftime("%H:%M"),
        "read": bool(row["read_at"]),
        "saved": bool(row["saved_at"]),
        # Interne Felder fuers Sortieren, werden vor der Auslieferung entfernt.
        "_tier": row["source_tier"],
        "_published": row["published_at"],
        "_pos": row["feed_pos"],
    }


def _strip_private(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if not k.startswith("_")}


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _cluster_strip(items: list[dict]) -> list[dict]:
    """Die Uebersicht oben: die groessten Themen des Tages.

    Nur echte Cluster (mehr als eine Quelle) - eine Einzelmeldung ist kein
    Thema, das mehrere Redaktionen beschaeftigt.
    """
    candidates = [e for e in items if e["cluster"]["sourceCount"] > 1]
    candidates.sort(key=lambda e: (-e["cluster"]["sourceCount"], -e["score"], e["id"]))
    strip = []
    for entry in candidates[: config.CLUSTER_STRIP_LIMIT]:
        strip.append(
            {
                "id": entry["cluster"]["id"],
                "title": entry["title"],
                "topic": entry["topic"],
                "topicLabel": config.TOPIC_LABELS.get(entry["topic"], entry["topic"]),
                "sourceCount": entry["cluster"]["sourceCount"],
                "sources": entry["cluster"]["sources"],
            }
        )
    return strip


def board_digest(board: dict) -> str:
    """Stabiler Fingerabdruck eines Boards - fuer den Determinismus-Test.

    Zeitabhaengige Felder bleiben aussen vor, denn sie aendern sich per
    Definition zwischen zwei Laeufen.
    """
    volatile = {"generatedAt", "lastFetchAt", "score"}

    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in sorted(value.items()) if k not in volatile}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value

    canonical = json.dumps(clean(board), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def search(conn, query: str, *, saved_only: bool = False, limit: int = 60) -> list[dict]:
    """Volltextsuche ueber alle archivierten Meldungen."""
    now = datetime.now(timezone.utc)
    query = (query or "").strip()

    if saved_only and not query:
        rows = conn.execute(
            """SELECT i.*, s.name AS source_name, s.tier AS source_tier,
                      st.read_at, st.saved_at
               FROM item i
               JOIN source s ON s.key = i.source_key
               JOIN state st ON st.item_id = i.id
               WHERE st.saved_at IS NOT NULL
               ORDER BY st.saved_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    elif not query:
        return []
    else:
        rows = conn.execute(
            f"""SELECT i.*, s.name AS source_name, s.tier AS source_tier,
                       st.read_at, st.saved_at
                FROM item_fts
                JOIN item i ON i.id = item_fts.item_id
                JOIN source s ON s.key = i.source_key
                LEFT JOIN state st ON st.item_id = i.id
                WHERE item_fts MATCH ?
                  {"AND st.saved_at IS NOT NULL" if saved_only else ""}
                ORDER BY bm25(item_fts, 2.0, 1.0), i.published_at DESC
                LIMIT ?""",
            (_fts_query(query), limit),
        ).fetchall()

    return [_strip_private(_item_payload(row, now)) for row in rows]


def _fts_query(raw: str) -> str:
    """Baut eine sichere FTS5-Abfrage aus freier Eingabe.

    Anwenderzeichen wie " oder * wuerden die FTS-Syntax sonst zerschiessen.
    Jedes Wort wird als Praefix gesucht, alle Woerter muessen vorkommen.
    """
    words = [w for w in normalize._WORD_RE.findall(normalize.fold(raw)) if w]
    if not words:
        return '""'
    return " AND ".join(f'"{w}"*' for w in words)
