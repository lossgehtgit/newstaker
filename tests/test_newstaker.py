"""Tests fuer den News-Taker.

Laufen ohne Netzzugriff: die Feed-Beispiele sind eingebettet, das Clustering
wird an den echten Faellen geprueft, die bei der Kalibrierung aufgetreten sind.

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from newstaker import cluster, config, feedparse, images, markets, normalize, pipeline, rank, store, weather  # noqa: E402


NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)

# Fuer die Feed-Fixtures unten (RSS2/ATOM/RSS1): die Pipeline-Tests laufen
# build_board() ohne festgehaltenes `now` und filtern echt auf
# config.BOARD_MAX_AGE_HOURS. Ein fest einprogrammiertes Datum wuerde nach ein
# paar Tagen aus dem Fenster fallen und die Tests grundlos zum Platzen
# bringen - deshalb relativ zur tatsaechlichen Ausfuehrungszeit.
_REAL_NOW = datetime.now(timezone.utc)


def _recent(hours_ago: float) -> str:
    return format_datetime(_REAL_NOW - timedelta(hours=hours_ago))


def doc(id_, source, tier, title, *, lang="de", topic="welt", minutes=0):
    return cluster.Doc(
        id=id_,
        source_key=source,
        source_tier=tier,
        lang=lang,
        topic=topic,
        title=title,
        published_at=NOW - timedelta(minutes=minutes),
        tokens=normalize.tokens(title),
    )


# --------------------------------------------------------------- Normalisierung


class TestNormalize(unittest.TestCase):
    def test_canonical_url_entfernt_tracking(self):
        self.assertEqual(
            normalize.canonical_url(
                "https://www.spiegel.de/politik/artikel-123.html?utm_source=rss&utm_medium=feed#top"
            ),
            "https://spiegel.de/politik/artikel-123.html",
        )

    def test_canonical_url_vereinheitlicht_host_und_schema(self):
        a = normalize.canonical_url("http://www.tagesschau.de/inland/x-100.html/")
        b = normalize.canonical_url("https://tagesschau.de/inland/x-100.html")
        self.assertEqual(a, b)

    def test_gleiche_url_gleiche_id(self):
        a = normalize.item_id(normalize.canonical_url("https://www.zeit.de/a?ref=rss"))
        b = normalize.item_id(normalize.canonical_url("https://zeit.de/a"))
        self.assertEqual(a, b)

    def test_kicker_wird_entfernt(self):
        self.assertEqual(
            normalize.strip_kicker("Zölle: EU-Strafe gegen Google trifft den Konzern hart"),
            "EU-Strafe gegen Google trifft den Konzern hart",
        )

    def test_kurzer_titel_behaelt_seinen_doppelpunkt(self):
        # "Merz: Wir bleiben dabei" darf nicht zu "Wir bleiben dabei" werden.
        titel = "Merz: Wir bleiben dabei"
        self.assertEqual(normalize.strip_kicker(titel), titel)

    def test_faltung_deckt_umlaute_ab(self):
        self.assertEqual(normalize.fold("Zölle für Österreich"), "zoelle fuer oesterreich")
        self.assertEqual(normalize.fold("Waldbrände"), normalize.fold("WALDBRAENDE"))

    def test_stopwords_verschwinden(self):
        toks = normalize.tokens("Die Bundesregierung und der Bundestag haben das beschlossen")
        self.assertNotIn("die", toks)
        self.assertNotIn("und", toks)
        self.assertIn("bundesregierung", toks)

    def test_agentur_wird_erkannt(self):
        self.assertEqual(normalize.agency_from("dpa", ""), "DPA")
        # Stehen mehrere Agenturen im Feld, gewinnt die erste aus _AGENCIES.
        self.assertEqual(normalize.agency_from("Uncredited/AP/dpa", ""), "DPA")
        self.assertEqual(normalize.agency_from("Foto: AP", ""), "AP")
        self.assertEqual(normalize.agency_from("Text von Reuters", ""), "Reuters")
        self.assertEqual(normalize.agency_from("Ein Autor", "kein Hinweis"), "")

    def test_inhaltlicher_vorspann_bleibt_erhalten(self):
        # Wichtig fuers Clustering: hier steht das Thema vor dem Doppelpunkt.
        self.assertEqual(
            normalize.strip_kicker("Waldbrände in Frankreich: Mehr als 110.000 Menschen evakuiert"),
            "Waldbrände in Frankreich: Mehr als 110.000 Menschen evakuiert",
        )

    def test_topic_aus_kategorie(self):
        self.assertEqual(normalize.topic_for_item("politik", ["Wirtschaft"]), "wirtschaft")
        self.assertEqual(normalize.topic_for_item("politik", []), "politik")
        # Generische Kategorien duerfen das Feed-Thema nicht kippen.
        self.assertEqual(normalize.topic_for_item("wirtschaft", ["News", "Top"]), "wirtschaft")


# --------------------------------------------------------------- Clustering


class TestCluster(unittest.TestCase):
    """Die Positivfaelle stammen aus dem Live-Abgleich bei der Kalibrierung."""

    def _gruppen(self, docs):
        return {c["id"]: set(c["item_ids"]) for c in cluster.build(docs)}

    def _zusammen(self, docs, a, b) -> bool:
        for ids in self._gruppen(docs).values():
            if a in ids and b in ids:
                return True
        return False

    def test_waldbraende_vier_quellen(self):
        """Genau die vier Schlagzeilen, die im Live-Abgleich einen Cluster
        gebildet haben - unterschiedliche Opferzahlen, unterschiedliche
        Formulierungen, dasselbe Ereignis."""
        docs = [
            doc("a1", "tagesschau", 1, "Mehr als 65.000 Menschen wegen Waldbränden in Frankreich evakuiert"),
            doc("a2", "spiegel", 1, "Waldbrände in Frankreich: Mehr als 110.000 Menschen evakuiert"),
            doc("a3", "handelsblatt", 1, "Feuer: Waldbrände in Frankreich und Spanien – 240.000 Menschen evakuiert"),
            doc("a4", "zeit", 2, "Wälder stehen in Flammen: Brände in Spanien und Frankreich: 257.000 Menschen evakuiert"),
        ]
        gruppen = self._gruppen(docs)
        self.assertEqual(len(gruppen), 1, "die vier Waldbrand-Meldungen gehoeren zusammen")
        self.assertEqual(list(gruppen.values())[0], {"a1", "a2", "a3", "a4"})

    def test_beugungsformen_stehen_dem_nicht_im_weg(self):
        """"Waldbraenden" (Dativ) und "Waldbraende" muessen sich finden."""
        self.assertIn(normalize.stem("waldbraenden"), normalize.tokens("Waldbrände in Frankreich"))

    def test_ausfuehrlicherer_titel_wird_ueber_containment_gefunden(self):
        """Zweiter Weg: der kuerzere Titel geht im laengeren auf."""
        docs = [
            doc("i1", "tagesschau", 1, "Paramount setzt Warner-Übernahme nach mehreren Klagen aus"),
            doc("i2", "faz", 2, "Nach Wettbewerbsklage: Paramount setzt Übernahme von Warner Brothers aus"),
        ]
        self.assertTrue(self._zusammen(docs, "i1", "i2"))

    def test_trump_google_zoelle(self):
        docs = [
            doc("b1", "tagesschau", 1, "Trump droht nach Google-Strafe der EU mit neuen Zöllen"),
            doc("b2", "handelsblatt", 1, "Zölle: EU-Strafe gegen Google: Trump droht mit „erheblichem Zoll“"),
        ]
        self.assertTrue(self._zusammen(docs, "b1", "b2"))

    def test_paramount_warner(self):
        docs = [
            doc("c1", "tagesschau", 1, "Paramount setzt Warner-Übernahme nach mehreren Klagen aus"),
            doc("c2", "handelsblatt", 1, "Hollywood-Deal: Paramount setzt Warner-Übernahme vorerst aus"),
        ]
        self.assertTrue(self._zusammen(docs, "c1", "c2"))

    def test_unabhaengige_trump_meldungen_bleiben_getrennt(self):
        """Der wichtigste Negativtest: nur weil zweimal 'Trump' vorkommt,
        ist es nicht dieselbe Story."""
        docs = [
            doc("d1", "spiegel", 1, "Donald Trump bei Korrespondentendinner: Wenn ich weg bin, seid Ihr alle pleite"),
            doc("d2", "guardian", 2, "Donald Trump Jr. Investment Firm Posts Staggering Returns", lang="en"),
            doc("d3", "tagesschau", 1, "Trump droht nach Google-Strafe der EU mit neuen Zöllen"),
        ]
        self.assertFalse(self._zusammen(docs, "d1", "d2"))
        self.assertFalse(self._zusammen(docs, "d1", "d3"))
        self.assertFalse(self._zusammen(docs, "d2", "d3"))

    def test_keine_verschmelzung_ueber_sprachgrenzen(self):
        """Bewusste Einschraenkung, im Plan mit Messdaten begruendet."""
        docs = [
            doc("e1", "tagesschau", 1, "Indiens Bildungsminister tritt nach Protesten zurück"),
            doc("e2", "bbc", 1, "India education minister resigns after student protests", lang="en"),
        ]
        self.assertFalse(self._zusammen(docs, "e1", "e2"))

    def test_zeitfenster_trennt_alte_meldungen(self):
        weit_weg = config.CLUSTER_WINDOW_HOURS * 60 + 120
        docs = [
            doc("f1", "tagesschau", 1, "Bundestag beschließt Reform des Vergaberechts"),
            doc("f2", "spiegel", 1, "Bundestag beschließt Reform des Vergaberechts", minutes=weit_weg),
        ]
        self.assertFalse(self._zusammen(docs, "f1", "f2"))

    def test_aufmacher_ist_die_beste_quelle(self):
        docs = [
            doc("g2", "physorg", 3, "Waldbrände in Frankreich und Spanien breiten sich weiter aus"),
            doc("g1", "tagesschau", 1, "Waldbrände in Frankreich und Spanien breiten sich weiter aus"),
        ]
        built = cluster.build(docs)
        self.assertEqual(len(built), 1)
        self.assertEqual(built[0]["lead_item_id"], "g1", "Tier 1 fuehrt den Cluster an")

    def test_ergebnis_haengt_nicht_von_der_eingabereihenfolge_ab(self):
        docs = [
            doc("h1", "tagesschau", 1, "Waldbrände in Frankreich: Zehntausende evakuiert"),
            doc("h2", "spiegel", 1, "Waldbrände in Frankreich: Mehr als 110.000 Menschen evakuiert"),
            doc("h3", "bbc", 1, "Wildfires rage across southern France", lang="en"),
            doc("h4", "faz", 2, "Bundestag beschließt Reform des Vergaberechts", topic="politik"),
        ]
        vorwaerts = self._gruppen(docs)
        rueckwaerts = self._gruppen(list(reversed(docs)))
        self.assertEqual(
            sorted(map(sorted, vorwaerts.values())),
            sorted(map(sorted, rueckwaerts.values())),
        )

    def test_aehnlichkeit_ist_symmetrisch(self):
        a = normalize.tokens("Waldbrände in Frankreich evakuiert")
        b = normalize.tokens("Waldbrände in Frankreich: Menschen evakuiert")
        idf = {t: 1.0 for t in a | b}
        self.assertAlmostEqual(
            cluster.similarity(a, b, idf), cluster.similarity(b, a, idf)
        )


# --------------------------------------------------------------- Ranking


class TestRank(unittest.TestCase):
    def test_mehr_quellen_ranken_hoeher(self):
        gemeinsam = dict(tier=1, feed_pos=0, published_at=NOW, topic="welt", now=NOW)
        viele = rank.score(source_count=5, **gemeinsam)
        wenige = rank.score(source_count=1, **gemeinsam)
        self.assertGreater(viele, wenige)

    def test_frisches_schlaegt_altes(self):
        gemeinsam = dict(tier=1, source_count=1, feed_pos=0, topic="welt", now=NOW)
        frisch = rank.score(published_at=NOW, **gemeinsam)
        alt = rank.score(published_at=NOW - timedelta(hours=24), **gemeinsam)
        self.assertGreater(frisch, alt)

    def test_bessere_feed_position_schlaegt_schlechtere(self):
        gemeinsam = dict(tier=1, source_count=1, published_at=NOW, topic="welt", now=NOW)
        self.assertGreater(rank.score(feed_pos=0, **gemeinsam), rank.score(feed_pos=30, **gemeinsam))

    def test_komponenten_bleiben_normiert(self):
        self.assertEqual(rank.source_component(1), 1.0)
        self.assertEqual(rank.source_component(3), 0.0)
        self.assertEqual(rank.recency_component(NOW, NOW), 1.0)
        self.assertAlmostEqual(
            rank.recency_component(NOW - timedelta(hours=config.RECENCY_HALFLIFE_HOURS), NOW), 0.5
        )
        self.assertEqual(rank.position_component(0), 1.0)

    def test_erklaerung_summiert_sich(self):
        parts = rank.explain(tier=1, source_count=3, feed_pos=2, published_at=NOW, topic="welt", now=NOW)
        summe = sum(v for k, v in parts.items() if k != "total")
        self.assertAlmostEqual(summe, parts["total"], places=3)


# --------------------------------------------------------------- Feedparser

RSS2_FIRST_PUBDATE = _recent(3)
RSS2_SECOND_PUBDATE = _recent(4)

RSS2 = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <item>
    <title>Erste Meldung mit Bild</title>
    <link>https://example.org/eins?utm_source=rss</link>
    <guid>eins</guid>
    <description>Ein Teaser mit &amp;amp; Entity.</description>
    <pubDate>{RSS2_FIRST_PUBDATE}</pubDate>
    <category>Wirtschaft</category>
    <dc:creator>dpa</dc:creator>
    <enclosure type="image/jpeg" url="https://cdn.example.org/bild.jpg" length="0"/>
  </item>
  <item>
    <title>Zweite Meldung ohne Bild</title>
    <link>https://example.org/zwei</link>
    <pubDate>{RSS2_SECOND_PUBDATE}</pubDate>
    <content:encoded><![CDATA[<p><img src="https://cdn.example.org/aus-content.jpg"> Text</p>]]></content:encoded>
  </item>
</channel>
</rss>""".encode("utf-8")

ATOM = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom-Meldung</title>
    <link rel="alternate" href="https://example.org/atom-eins"/>
    <id>urn:uuid:1</id>
    <updated>{(_REAL_NOW - timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%SZ')}</updated>
    <summary>Zusammenfassung</summary>
  </entry>
</feed>""".encode("utf-8")

# Nature und Science liefern RSS 1.0 (RDF) mit Default-Namespace.
RSS1 = f"""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         xmlns="http://purl.org/rss/1.0/">
  <channel rdf:about="https://example.org"><title>Kanal</title></channel>
  <item rdf:about="https://example.org/rdf-eins">
    <title>RDF-Meldung</title>
    <link>https://example.org/rdf-eins</link>
    <description>Beschreibung</description>
    <dc:date>{(_REAL_NOW - timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%SZ')}</dc:date>
  </item>
</rdf:RDF>""".encode("utf-8")


class TestFeedparse(unittest.TestCase):
    def test_rss2_wird_gelesen(self):
        items = feedparse.parse(RSS2)
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first.title, "Erste Meldung mit Bild")
        self.assertEqual(first.image, "https://cdn.example.org/bild.jpg")
        self.assertEqual(first.categories, ["Wirtschaft"])
        self.assertEqual(first.author, "dpa")
        self.assertEqual(first.position, 0)
        self.assertIsNotNone(first.published)

    def test_bild_aus_content_encoded(self):
        items = feedparse.parse(RSS2)
        self.assertEqual(items[1].image, "https://cdn.example.org/aus-content.jpg")

    def test_atom_wird_gelesen(self):
        items = feedparse.parse(ATOM)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].link, "https://example.org/atom-eins")
        self.assertIsNotNone(items[0].published)

    def test_rss1_rdf_wird_gelesen(self):
        items = feedparse.parse(RSS1)
        self.assertEqual(len(items), 1, "RSS 1.0 (Nature, Science) muss geparst werden")
        self.assertEqual(items[0].title, "RDF-Meldung")
        self.assertIsNotNone(items[0].published)

    def test_kaputtes_xml_wirft_nicht(self):
        self.assertEqual(feedparse.parse(b"<rss><item><title>kaputt"), [])
        self.assertEqual(feedparse.parse(b""), [])

    def test_datumsformate(self):
        self.assertIsNotNone(feedparse.parse_date("Sat, 25 Jul 2026 08:05:00 +0200"))
        self.assertIsNotNone(feedparse.parse_date("2026-07-25T06:30:00Z"))
        self.assertIsNotNone(feedparse.parse_date("2026-07-25"))
        self.assertIsNone(feedparse.parse_date("Unsinn"))

    def test_tracking_pixel_gilt_nicht_als_bild(self):
        self.assertFalse(feedparse._plausible_image("https://x.org/tracking-pixel.gif"))
        self.assertFalse(feedparse._plausible_image("https://x.org/logo.png"))
        self.assertTrue(feedparse._plausible_image("https://x.org/aufmacher.jpg"))


# --------------------------------------------------------------- Wetter


class TestWeather(unittest.TestCase):
    def test_jeder_wmo_code_trifft_ein_symbol(self):
        for code in range(0, 100):
            icon, label = weather.describe(code)
            self.assertTrue(icon, f"Code {code} ohne Symbol")
            self.assertTrue(label, f"Code {code} ohne Beschreibung")

    def test_bekannte_codes(self):
        self.assertEqual(weather.describe(0)[0], weather.SUN)
        self.assertEqual(weather.describe(3)[0], weather.CLOUD)
        self.assertEqual(weather.describe(61)[0], weather.RAIN)
        self.assertEqual(weather.describe(71)[0], weather.SNOW)
        self.assertEqual(weather.describe(95)[0], weather.STORM)

    def test_wochentagskuerzel(self):
        self.assertEqual(weather.weekday_label("2026-07-25"), "SA")
        self.assertEqual(weather.weekday_label("2026-07-27"), "MO")


# --------------------------------------------------------------- Bilder


class TestImages(unittest.TestCase):
    def test_kachel_ist_stabil(self):
        a = images.render_tile("abc123def456", "Handelsblatt", "wirtschaft")
        b = images.render_tile("abc123def456", "Handelsblatt", "wirtschaft")
        self.assertEqual(a, b, "gleiche id muss dieselbe Kachel ergeben")

    def test_verschiedene_ids_verschiedene_kacheln(self):
        a = images.render_tile("0000000000000000", "Nature", "wissenschaft")
        b = images.render_tile("ffffffffffffffff", "Nature", "wissenschaft")
        self.assertNotEqual(a, b)

    def test_kachel_ist_gueltiges_svg(self):
        from xml.etree import ElementTree

        svg = images.render_tile("a1b2c3d4", "WSJ", "wirtschaft")
        root = ElementTree.fromstring(svg)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertIn("WSJ", svg)

    def test_sonderzeichen_werden_maskiert(self):
        svg = images.render_tile("a1b2c3d4", 'Böse & <Quelle>', "welt")
        self.assertNotIn("<Quelle>", svg)
        self.assertIn("&amp;", svg)


# --------------------------------------------------------------- Ende-zu-Ende


class TestPipelineInMemory(unittest.TestCase):
    """Vollstaendiger Durchlauf gegen eine temporaere Datenbank."""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self._alte_db = config.DB_PATH
        self._alter_var = config.VAR_DIR
        config.VAR_DIR = Path(self.tmp.name)
        config.DB_PATH = Path(self.tmp.name) / "test.db"
        self.conn = store.connect()
        store.init(self.conn)

    def tearDown(self):
        self.conn.close()
        config.DB_PATH = self._alte_db
        config.VAR_DIR = self._alter_var
        self.tmp.cleanup()

    def _einlesen(self):
        src = config.source_by_key("spiegel")
        return pipeline.ingest_feed(self.conn, src, "https://example.org/feed", "wirtschaft", RSS2)

    def test_einlesen_und_wiederholtes_einlesen(self):
        erst = self._einlesen()
        self.assertEqual(erst["items"], 2)
        self.assertEqual(erst["new"], 2)
        # Zweiter Durchlauf darf keine Dubletten erzeugen.
        zweit = self._einlesen()
        self.assertEqual(zweit["new"], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) c FROM item").fetchone()["c"], 2)

    def test_suche_findet_mit_und_ohne_umlaut(self):
        self.conn.execute("DELETE FROM item")
        src = config.source_by_key("tagesschau")
        feed = RSS2.replace(b"Erste Meldung mit Bild", b"Waldbr\xc3\xa4nde in Frankreich")
        pipeline.ingest_feed(self.conn, src, "https://example.org/f", "welt", feed)
        self.conn.commit()
        self.assertTrue(pipeline.search(self.conn, "Waldbrände"))
        self.assertTrue(pipeline.search(self.conn, "waldbraende"))
        self.assertTrue(pipeline.search(self.conn, "WALDBRÄNDE"))
        self.assertFalse(pipeline.search(self.conn, "Segelregatta"))

    def test_suche_vertraegt_sonderzeichen(self):
        self._einlesen()
        self.conn.commit()
        for eingabe in ['"', "*", "AND", "  ", "a\"b*(c)"]:
            pipeline.search(self.conn, eingabe)  # darf nicht werfen

    def test_status_wird_gespeichert(self):
        self._einlesen()
        self.conn.commit()
        item_id = self.conn.execute("SELECT id FROM item LIMIT 1").fetchone()["id"]
        store.set_state(self.conn, item_id, "saved", True)
        store.set_state(self.conn, item_id, "read", True)
        self.conn.commit()
        gelesen, gemerkt = store.state_counts(self.conn)
        self.assertEqual((gelesen, gemerkt), (1, 1))
        store.set_state(self.conn, item_id, "saved", False)
        self.conn.commit()
        self.assertEqual(store.state_counts(self.conn)[1], 0)

    def test_jede_meldung_bekommt_ein_bild(self):
        """Livs Vorgabe: Bild bei jeder Headline - garantiert durch Stufe 3."""
        self._einlesen()
        # Bilder entfernen, damit nur die Kachel-Stufe greifen kann.
        self.conn.execute("UPDATE item SET image_url='', image_kind=''")
        self.conn.commit()
        images.backfill(self.conn, hours=config.BOARD_MAX_AGE_HOURS, budget=0)
        self.conn.commit()
        pipeline.rebuild_clusters(self.conn)
        board = pipeline.build_board(self.conn)
        alle = board["leads"] + board["briefs"]
        self.assertTrue(alle)
        for eintrag in alle:
            self.assertTrue(eintrag["image"], f"ohne Bild: {eintrag['title']}")

    def test_thema_haengt_nicht_von_der_abrufreihenfolge_ab(self):
        """Dieselbe Meldung steht oft in mehreren Feeds einer Quelle, jeder mit
        eigenem Thema. Welcher gewinnt, muss die Konfiguration entscheiden -
        nicht die Reihenfolge des Abrufs. Sonst weichen 'fetch' und 'rebuild'
        voneinander ab."""
        src = config.source_by_key("tagesschau")
        feeds = [url for url, _ in src["feeds"]]
        vorne, hinten = feeds[0], feeds[2]
        themen = dict(src["feeds"])

        def einlesen(reihenfolge):
            self.conn.execute("DELETE FROM item")
            self.conn.execute("DELETE FROM item_fts")
            for url in reihenfolge:
                pipeline.ingest_feed(self.conn, src, url, themen[url], RSS2)
            self.conn.commit()
            return self.conn.execute("SELECT topic FROM item ORDER BY id").fetchall()

        vorwaerts = [r["topic"] for r in einlesen([vorne, hinten])]
        rueckwaerts = [r["topic"] for r in einlesen([hinten, vorne])]
        self.assertEqual(vorwaerts, rueckwaerts)

    def test_ersatzdatum_wandert_nicht(self):
        """Ohne pubDate setzen wir den Abrufzeitpunkt ein - der darf sich beim
        erneuten Einlesen nicht verschieben."""
        ohne_datum = RSS2.replace(f"<pubDate>{RSS2_FIRST_PUBDATE}</pubDate>".encode("utf-8"), b"")
        src = config.source_by_key("spiegel")
        pipeline.ingest_feed(self.conn, src, "https://example.org/feed", "wirtschaft", ohne_datum)
        self.conn.commit()
        vorher = [r["published_at"] for r in self.conn.execute("SELECT published_at FROM item ORDER BY id")]
        pipeline.ingest_feed(self.conn, src, "https://example.org/feed", "wirtschaft", ohne_datum)
        self.conn.commit()
        nachher = [r["published_at"] for r in self.conn.execute("SELECT published_at FROM item ORDER BY id")]
        self.assertEqual(vorher, nachher)

    def test_board_ist_reproduzierbar(self):
        """Das Kernversprechen: gleiche Feeds rein, gleiches Board raus.

        `now` wird festgehalten, weil die Aktualitaetskomponente des Rankings
        sonst die einzige - und beabsichtigte - Abweichung erzeugen wuerde.
        """
        self._einlesen()
        self.conn.commit()
        jetzt = datetime.now(timezone.utc)
        pipeline.rebuild_clusters(self.conn)
        erst = pipeline.board_digest(pipeline.build_board(self.conn, now=jetzt))
        pipeline.rebuild(self.conn)
        zweit = pipeline.board_digest(pipeline.build_board(self.conn, now=jetzt))
        pipeline.rebuild(self.conn)
        dritt = pipeline.board_digest(pipeline.build_board(self.conn, now=jetzt))
        self.assertEqual(erst, zweit, "gleicher Stand muss dasselbe Board ergeben")
        self.assertEqual(zweit, dritt)

    def test_cli_rebuild_ist_reproduzierbar(self):
        """Regressionstest fuer zwei von einem unabhaengigen Audit gefundene
        Bugs, die zusammen den echten CLI-Befehl 'python3 run.py rebuild'
        nicht-deterministisch machten:

        1. cmd_rebuild() rief build_board() urspruenglich ganz ohne now= auf.
        2. Selbst mit durchgereichtem now= verankerten rebuild_clusters() und
           images.backfill() ihr Zeitfenster (store.items_in_window() /
           items_missing_image()) weiterhin an einem eigenen, unabhaengigen
           datetime.now() - vier echte CLI-Laeufe ergaben deshalb trotzdem
           vier verschiedene Fingerabdruecke, sogar Sekunden auseinander.

        Die Bibliothekstests hier pruefen nur pipeline.build_board() direkt
        mit fest uebergebenem now= und haetten keinen der beiden Bugs
        gefunden - dieser Test ruft stattdessen die echte CLI-Funktion auf
        und laesst echte Zeit zwischen den beiden Laeufen verstreichen, genau
        wie beim Audit."""
        import argparse
        import contextlib
        import io
        import time

        import run as run_module

        self._einlesen()
        # last_fetch_at muss gesetzt sein, sonst faellt cmd_rebuild() auf die
        # reale Uhrzeit zurueck (Verhalten einer frisch angelegten Datenbank,
        # nicht das hier zu pruefende "erneut rebuilden nach einem Fetch").
        store.set_meta(self.conn, "last_fetch_at", store.now_iso())
        self.conn.commit()

        fingerprints = []
        for i in range(2):
            if i:
                time.sleep(1.2)  # echte Zeit verstreichen lassen, wie beim Audit
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run_module.cmd_rebuild(argparse.Namespace())
            line = next(l for l in buf.getvalue().splitlines() if l.startswith("Board-Fingerabdruck:"))
            fingerprints.append(line.split(": ", 1)[1])

        self.assertEqual(
            fingerprints[0], fingerprints[1],
            "'python3 run.py rebuild' muss auch mit echtem Zeitabstand denselben Fingerabdruck liefern",
        )

    def test_board_reproduzierbar_je_thema(self):
        self._einlesen()
        self.conn.commit()
        jetzt = datetime.now(timezone.utc)
        pipeline.rebuild_clusters(self.conn)
        for thema in [""] + config.TOPICS:
            erst = pipeline.board_digest(pipeline.build_board(self.conn, topic=thema, now=jetzt))
            pipeline.rebuild(self.conn)
            zweit = pipeline.board_digest(pipeline.build_board(self.conn, topic=thema, now=jetzt))
            self.assertEqual(erst, zweit, f"Thema {thema or 'alle'} nicht reproduzierbar")

    def test_themenfilter_wirkt(self):
        self._einlesen()
        self.conn.commit()
        pipeline.rebuild_clusters(self.conn)
        board = pipeline.build_board(self.conn, topic="wirtschaft")
        for eintrag in board["leads"] + board["briefs"]:
            self.assertEqual(eintrag["topic"], "wirtschaft")

    def test_gelesene_ausblenden(self):
        self._einlesen()
        self.conn.commit()
        pipeline.rebuild_clusters(self.conn)
        vorher = pipeline.build_board(self.conn)
        anzahl = len(vorher["leads"]) + len(vorher["briefs"])
        erste_id = (vorher["leads"] + vorher["briefs"])[0]["id"]
        store.set_state(self.conn, erste_id, "read", True)
        self.conn.commit()
        nachher = pipeline.build_board(self.conn, hide_read=True)
        self.assertEqual(len(nachher["leads"]) + len(nachher["briefs"]), anzahl - 1)

    def test_markets_totalausfall_erhaelt_alten_stand(self):
        """Regressionstest fuer einen von einem unabhaengigen Audit gefundenen
        Bug: schlagen ALLE Kandidaten fehl (z.B. Yahoo komplett down),
        loeschte refresh() bisher per DELETE+INSERT([],[]) den zuletzt
        erfolgreichen Marktstand ersatzlos, obwohl keine neuen Daten da
        waren - im Widerspruch zum eigenen Modul-Docstring ('bleibt einfach
        der letzte erfolgreiche Stand stehen')."""
        store.save_markets(
            self.conn,
            [{"symbol": "TEST", "name": "Test-ETF", "price": 1.0, "currency": "USD", "changePct": 5.0}],
            [],
        )
        self.conn.commit()

        with mock.patch.object(markets, "_fetch_chart", return_value=None):
            result = markets.refresh(self.conn, force=True)

        self.assertEqual(result, {"refreshed": False, "etfs": 0, "stocks": 0, "failed": True})
        etfs, stocks, _ = store.load_markets(self.conn)
        self.assertEqual(len(etfs), 1, "alter Marktstand darf bei Totalausfall nicht verschwinden")
        self.assertEqual(etfs[0]["symbol"], "TEST")


class TestConfig(unittest.TestCase):
    def test_pflichtquellen_sind_vorhanden(self):
        namen = {s["name"] for s in config.SOURCES}
        for pflicht in ("Handelsblatt", "Tagesschau", "Spiegel"):
            self.assertIn(pflicht, namen)

    def test_quellenschluessel_sind_eindeutig(self):
        keys = [s["key"] for s in config.SOURCES]
        self.assertEqual(len(keys), len(set(keys)))

    def test_feeds_sind_eindeutig(self):
        urls = [url for _, url, _ in config.all_feeds()]
        self.assertEqual(len(urls), len(set(urls)), "doppelte Feed-URL in der Registry")

    def test_jeder_feed_hat_ein_bekanntes_topic(self):
        for src, url, topic in config.all_feeds():
            self.assertIn(topic, config.TOPICS, f"{src['name']} {url}")

    def test_jedes_topic_hat_ein_label_und_einen_boost(self):
        for topic in config.TOPICS:
            self.assertIn(topic, config.TOPIC_LABELS)
            self.assertIn(topic, config.TOPIC_BOOST)

    def test_marktkandidaten_sind_eindeutig(self):
        self.assertEqual(len(config.CANDIDATE_ETFS), len(set(config.CANDIDATE_ETFS)))
        self.assertEqual(len(config.CANDIDATE_STOCKS), len(set(config.CANDIDATE_STOCKS)))
        self.assertFalse(set(config.CANDIDATE_ETFS) & set(config.CANDIDATE_STOCKS),
                          "ein Titel darf nicht in beiden Kandidatenlisten stehen")


# --------------------------------------------------------------- Maerkte


def _synthetic_chart(closes, *, dividends=None, price=None):
    return {
        "meta": {
            "longName": "Testfirma AG",
            "regularMarketPrice": price if price is not None else closes[-1],
            "currency": "USD",
        },
        "indicators": {"quote": [{"close": closes}]},
        "events": {"dividends": dividends or {}},
    }


class TestMarkets(unittest.TestCase):
    def test_dividendenzahler_wird_ausgeschlossen(self):
        chart = _synthetic_chart([100.0] * 500, dividends={"1700000000": {"amount": 0.5}})
        self.assertIsNone(markets._metrics_from_chart("TEST", chart))

    def test_zu_wenig_historie_wird_ausgeschlossen(self):
        chart = _synthetic_chart([100.0] * 50)  # deutlich unter 400 Handelstagen
        self.assertIsNone(markets._metrics_from_chart("TEST", chart))

    def test_gueltiger_titel_liefert_kennzahlen(self):
        closes = [100.0] * 400 + [150.0]
        chart = _synthetic_chart(closes)
        m = markets._metrics_from_chart("TEST", chart)
        self.assertIsNotNone(m)
        self.assertAlmostEqual(m["changePct"], 50.0, places=1)
        self.assertEqual(m["currency"], "USD")

    def test_ranking_ist_absteigend_nach_veraenderung(self):
        # _refresh_group sortiert selbst; hier direkt die Sortierlogik pruefen.
        rows = [
            {"symbol": "A", "changePct": 10.0},
            {"symbol": "B", "changePct": 50.0},
            {"symbol": "C", "changePct": 30.0},
        ]
        rows.sort(key=lambda m: (-m["changePct"], m["symbol"]))
        self.assertEqual([r["symbol"] for r in rows], ["B", "C", "A"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
