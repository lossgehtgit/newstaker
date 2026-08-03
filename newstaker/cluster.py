"""Deterministisches Zusammenfassen gleicher Meldungen.

Verfahren: IDF-gewichtete Jaccard-Aehnlichkeit ueber die Inhaltstoken der
Schlagzeile, danach Single-Linkage per Union-Find.

Kalibrierung gegen 484 echte Meldungen aus sieben deutschen Quellen:
  0.28 -> mehr Cluster, beginnende Unschaerfe
  0.34 -> 10 saubere Multi-Quellen-Cluster, kein Fehltreffer   <- gewaehlt
  0.42 -> zu streng, maximal zwei Quellen je Cluster

Bewusste Einschraenkung: es wird ausschliesslich innerhalb einer Sprache
zusammengefasst. Ein Test mit Eigennamen-Overlap ueber 302 deutsche und 247
englische Meldungen lieferte 7 Kandidaten, davon nur 2 korrekt - die restlichen
waren Namenskoinzidenzen ("Donald Trump" in drei unabhaengigen Storys). Jede
Verschaerfung, die die Fehltreffer beseitigt, beseitigt auch die Treffer. Ein
falsch verschmolzener Cluster ist in einem Nachrichtentool teurer als ein
fehlender, deshalb bleibt es dabei.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from . import config, normalize


@dataclass
class Doc:
    id: str
    source_key: str
    source_tier: int
    lang: str
    topic: str
    title: str
    published_at: datetime
    tokens: frozenset[str]


class _UnionFind:
    """Union-Find mit Pfadkompression.

    Der Repraesentant ist immer der kleinste Index der Gruppe. Zusammen mit
    einer nach id sortierten Eingabe macht das die Gruppierung reproduzierbar.
    """

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            lo, hi = (ra, rb) if ra < rb else (rb, ra)
            self.parent[hi] = lo


def _idf_table(docs: list[Doc]) -> dict[str, float]:
    """IDF ueber genau die Dokumente, die geclustert werden.

    Damit ist der Wert allein durch die Eingabemenge bestimmt - kein globaler
    Zustand, keine Historie, also reproduzierbar.
    """
    df: dict[str, int] = defaultdict(int)
    for doc in docs:
        for token in doc.tokens:
            df[token] += 1
    n = len(docs)
    return {token: math.log((n + 1) / (count + 1)) + 1.0 for token, count in df.items()}


def similarity(a: frozenset[str], b: frozenset[str], idf: dict[str, float]) -> float:
    """IDF-gewichtete Jaccard-Aehnlichkeit."""
    if not a or not b:
        return 0.0
    inter = a & b
    if not inter:
        return 0.0
    union = a | b
    top = sum(idf.get(t, 1.0) for t in inter)
    bottom = sum(idf.get(t, 1.0) for t in union)
    return top / bottom if bottom else 0.0


def containment(a: frozenset[str], b: frozenset[str], idf: dict[str, float]) -> float:
    """Wie stark steckt die kuerzere Schlagzeile in der laengeren?

    Jaccard bestraft es, wenn eine Redaktion ausfuehrlicher titelt als die
    andere: "Waldbraende in Frankreich: 110.000 evakuiert" und "Frankreich und
    Spanien: Waldbraende zwingen 160.000 Menschen zur Flucht" teilen dasselbe
    Ereignis, aber die zweite bringt vier zusaetzliche Woerter mit, die die
    Vereinigungsmenge aufblaehen. Dieses Mass sieht nur den Anteil am
    kleineren der beiden Titel.
    """
    if not a or not b:
        return 0.0
    inter = a & b
    if not inter:
        return 0.0
    top = sum(idf.get(t, 1.0) for t in inter)
    smaller = min(
        sum(idf.get(t, 1.0) for t in a),
        sum(idf.get(t, 1.0) for t in b),
    )
    return top / smaller if smaller else 0.0


def _matches(a: frozenset[str], b: frozenset[str], idf: dict[str, float], threshold: float) -> bool:
    """Zwei Schlagzeilen beschreiben dasselbe Ereignis.

    Erster Weg ist die Jaccard-Schwelle. Der zweite faengt den Fall ab, dass
    eine Redaktion deutlich ausfuehrlicher titelt: dann muss der kuerzere Titel
    fast vollstaendig im laengeren aufgehen und es muessen genuegend
    Inhaltswoerter geteilt werden. Beide Bedingungen zusammen sind streng genug,
    dass unabhaengige Meldungen mit zufaellig gleichen Namen nicht anschlagen.
    """
    if similarity(a, b, idf) >= threshold:
        return True
    shared = a & b
    if len(shared) < config.CLUSTER_MIN_SHARED:
        return False
    if len(a) < config.CLUSTER_MIN_TOKENS + 1 or len(b) < config.CLUSTER_MIN_TOKENS + 1:
        return False
    return (
        containment(a, b, idf) >= config.CLUSTER_CONTAINMENT
        and similarity(a, b, idf) >= config.CLUSTER_THRESHOLD_FLOOR
    )


def build(docs: list[Doc]) -> list[dict]:
    """Gruppiert Meldungen und liefert die Cluster in stabiler Reihenfolge."""
    docs = sorted(docs, key=lambda d: d.id)
    n = len(docs)
    if n == 0:
        return []

    idf = _idf_table(docs)
    window = config.CLUSTER_WINDOW_HOURS * 3600

    # Kandidaten vorfiltern: nur Paare, die mindestens ein Inhaltstoken teilen,
    # kommen ueberhaupt in den Vergleich. Das druckt den quadratischen Aufwand
    # auf die tatsaechlich sinnvollen Paare.
    by_token: dict[str, list[int]] = defaultdict(list)
    for i, doc in enumerate(docs):
        for token in doc.tokens:
            by_token[token].append(i)

    uf = _UnionFind(n)
    seen: set[tuple[int, int]] = set()

    for token in sorted(by_token):
        bucket = by_token[token]
        # Allerweltstoken erzeugen riesige Buckets ohne Erkenntniswert.
        if len(bucket) > 60:
            continue
        for pos_a in range(len(bucket)):
            for pos_b in range(pos_a + 1, len(bucket)):
                i, j = bucket[pos_a], bucket[pos_b]
                if (i, j) in seen:
                    continue
                seen.add((i, j))

                a, b = docs[i], docs[j]
                if a.lang != b.lang:
                    continue
                if len(a.tokens) < config.CLUSTER_MIN_TOKENS or len(b.tokens) < config.CLUSTER_MIN_TOKENS:
                    continue
                if abs((a.published_at - b.published_at).total_seconds()) > window:
                    continue
                if uf.find(i) == uf.find(j):
                    continue

                threshold = (
                    config.CLUSTER_THRESHOLD_SAME_SOURCE
                    if a.source_key == b.source_key
                    else config.CLUSTER_THRESHOLD
                )
                if _matches(a.tokens, b.tokens, idf, threshold):
                    uf.union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)

    clusters: list[dict] = []
    for root in sorted(groups):
        members = [docs[i] for i in groups[root]]
        lead = _pick_lead(members)
        source_count = len({m.source_key for m in members})
        clusters.append(
            {
                # Die id des Aufmachers ist stabil, solange die Gruppe stabil
                # ist - dadurch bleibt ein Cluster ueber Rebuilds erkennbar.
                "id": f"c{lead.id[:16]}",
                "lead_item_id": lead.id,
                "item_ids": sorted(m.id for m in members),
                "size": len(members),
                "source_count": source_count,
                "topic": _pick_topic(members),
                "lang": lead.lang,
                "score": 0.0,
            }
        )
    return clusters


def _pick_lead(members: list[Doc]) -> Doc:
    """Waehlt den Aufmacher eines Clusters.

    Kriterien in dieser Reihenfolge: bestes Quellen-Tier (Handelsblatt,
    Tagesschau, Spiegel und die gleichwertigen internationalen Haeuser zuerst),
    dann die frueheste Meldung, dann die id. Vollstaendig deterministisch.
    """
    return sorted(members, key=lambda d: (d.source_tier, d.published_at, d.id))[0]


def _pick_topic(members: list[Doc]) -> str:
    """Mehrheitsthema der Gruppe; bei Gleichstand entscheidet die Reihenfolge
    in config.TOPICS, damit das Ergebnis nicht von der Eingabereihenfolge
    abhaengt."""
    counts: dict[str, int] = defaultdict(int)
    for m in members:
        counts[m.topic] += 1
    order = {t: i for i, t in enumerate(config.TOPICS)}
    return sorted(counts.items(), key=lambda kv: (-kv[1], order.get(kv[0], 99)))[0][0]


def docs_from_rows(rows) -> list[Doc]:
    """Baut Doc-Objekte aus den Datenbankzeilen."""
    out: list[Doc] = []
    for row in rows:
        published = datetime.fromisoformat(row["published_at"])
        out.append(
            Doc(
                id=row["id"],
                source_key=row["source_key"],
                source_tier=row["source_tier"],
                lang=row["lang"],
                topic=row["topic"],
                title=row["title"],
                published_at=published,
                tokens=normalize.tokens(row["title"]),
            )
        )
    return out
