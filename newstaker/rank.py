"""Deterministisches Ranking.

Kein Modell entscheidet, was oben steht - fuenf sichtbare Komponenten tun es.
Jede ist auf 0..1 normiert, damit die Gewichte in config.RANK_WEIGHTS direkt
miteinander vergleichbar sind.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from . import config

# Hoechstes Tier in der Registry, fuer die Normierung.
_MAX_TIER = 3


def source_component(tier: int) -> float:
    """Tier 1 -> 1.0, Tier 3 -> 0.0."""
    tier = max(1, min(_MAX_TIER, tier))
    return (_MAX_TIER - tier) / (_MAX_TIER - 1)


def cluster_component(source_count: int) -> float:
    """Wie viele unabhaengige Quellen bringen die Story?

    Logarithmisch gedaempft: der Sprung von einer auf zwei Quellen ist das
    starke Signal, der von sechs auf sieben kaum noch.
    """
    return min(1.0, math.log(max(1, source_count), 2) / math.log(6, 2))


def position_component(feed_pos: int) -> float:
    """Platzierung im Feed = redaktionelles Urteil der Quelle.

    Position 0 (Aufmacher) -> 1.0, faellt danach zuegig ab.
    """
    return 1.0 / (1.0 + max(0, feed_pos) / 5.0)


def recency_component(published_at: datetime, now: datetime) -> float:
    """Exponentieller Abfall mit der konfigurierten Halbwertszeit."""
    age_hours = max(0.0, (now - published_at).total_seconds() / 3600.0)
    return 0.5 ** (age_hours / config.RECENCY_HALFLIFE_HOURS)


def topic_component(topic: str) -> float:
    return config.TOPIC_BOOST.get(topic, 0.5)


def score(
    *,
    tier: int,
    source_count: int,
    feed_pos: int,
    published_at: datetime,
    topic: str,
    now: datetime | None = None,
) -> float:
    now = now or datetime.now(timezone.utc)
    w = config.RANK_WEIGHTS
    return (
        w["source"] * source_component(tier)
        + w["cluster"] * cluster_component(source_count)
        + w["position"] * position_component(feed_pos)
        + w["recency"] * recency_component(published_at, now)
        + w["topic"] * topic_component(topic)
    )


def explain(
    *,
    tier: int,
    source_count: int,
    feed_pos: int,
    published_at: datetime,
    topic: str,
    now: datetime | None = None,
) -> dict[str, float]:
    """Aufschluesselung des Scores - fuer Nachvollziehbarkeit im Debug-Modus."""
    now = now or datetime.now(timezone.utc)
    w = config.RANK_WEIGHTS
    parts = {
        "source": w["source"] * source_component(tier),
        "cluster": w["cluster"] * cluster_component(source_count),
        "position": w["position"] * position_component(feed_pos),
        "recency": w["recency"] * recency_component(published_at, now),
        "topic": w["topic"] * topic_component(topic),
    }
    parts["total"] = sum(parts.values())
    return {k: round(v, 4) for k, v in parts.items()}
