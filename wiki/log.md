# Änderungsprotokoll

Append-only. Ein Eintrag pro abgeschlossener Aufgabe. **Diese Datei nie
komplett lesen** — wird mit der Zeit groß. Stattdessen:

```bash
grep "^## \[" wiki/log.md | tail -3
```

Neue Einträge immer **anhängen**, nie bestehende Einträge ändern oder löschen.

---

## [2026-09-05] docs — Git-Workflow in CLAUDE.md verbindlich festgehalten
Abschnitt „Git Workflow" in `CLAUDE.md` ergänzt: Feature-Branches/Worktrees
statt direkt auf `main`, Conventional Commits, PR-Merge-Gate (`gh pr checks`
vor jedem Merge grün — Pflicht, da `main` keine Branch Protection hat und der
einzige Workflow `update.yml` nicht auf `pull_request` läuft), Aufräumen nach
Merge, Secrets nie committen, destruktive Git-Ops nur nach Rückfrage. Ist-Zustand
geprüft: Repo public, Default-Branch `main`, kein Branch Protection, Solo-Projekt
(ein Collaborator).

## [2026-09-05] docs — Wiki-System eingerichtet

Persistentes, dateibasiertes Wiki unter `wiki/` angelegt als externes
Gedächtnis für künftige Sessions (Einzelprojekt-Repo, daher ohne
`<projekt>/`-Unterordner). Angelegt: `wiki/index.md`, `wiki/overview.md`,
`wiki/architecture.md`, `wiki/database.md`, `wiki/decisions/README.md`
(ADR-Vorlage), `wiki/log.md` (diese Datei). `CLAUDE.md` neu angelegt mit
Abschnitt „Wiki" (Struktur, Query-/Update-Routine, Session-Start-Protokoll,
Token-Sparregeln). Keine Code-Änderungen, kein ADR nötig für diesen Schritt
selbst.

## [2026-09-05] fix — Wiki-PR nach externem History-Rewrite neu gemergt

Der ursprüngliche Wiki-PR wurde gemergt, verschwand aber wieder aus `main`,
weil zwischenzeitlich unabhängig ein weiterer privacy-motivierter
History-Rewrite auf `main` stattfand (Commit „Kommentare neutralisiert
(Personenbezug entfernt)"), der die gesamte Historie inkl. aller Hashes
ersetzte und den Merge-Commit dabei mit ausschloss. Inhalt war nicht
verloren (identischer Commit lag mit neuem Hash weiter auf dem alten
Feature-Branch), wurde per Cherry-Pick auf einen frischen, von aktuellem
`main` abgezweigten Branch übertragen und erneut per PR gemergt.
`wiki/architecture.md` um eine vierte „bekannte Falle" ergänzt (History-
Rewrites auf `main` — nie lokalen Stand draufpushen, immer `reset --hard
origin/main`, PR-Status „merged" nicht blind vertrauen). Betroffene
Dateien: `wiki/architecture.md`, `wiki/log.md` (diese Datei).

## [2026-09-05] docs — Hygiene-Regeln in CLAUDE.md ergänzt, erster Beispiel-Skill angelegt

Neuer Abschnitt „Hygiene-Regeln" in `CLAUDE.md`: fünf feste Arbeitsweisen
(Bugfix ⇒ Bugklassen-Sweep; Detail-Änderung ⇒ Zusammenfassung mitziehen;
"kann nicht passieren" ⇒ als Test verankern statt als Kommentar; "behoben"
⇒ tatsächliche Ausgabe prüfen statt nur Log/Exception; neue Automatisierung
⇒ echten Effekt statt Exit-Code prüfen, plus Idempotenz-Check vor
Branch/PR/Issue-Erstellung). Jede Regel trägt einen Platzhalter für
Präzedenzfälle, der bei Eintreten real ergänzt wird. Zusätzlich Abschnitt
„Wiederkehrende Routinen als Skills": Kandidaten-Kriterium (>2x manuell
erklärt) plus Verweis auf den ersten Beispiel-Skill
`.claude/skills/bug-class-sweep/SKILL.md`, der Regel 1 automatisiert
(Grep-Suche nach demselben Bug-Muster über die gesamte Codebase, alle
Treffer in einem Durchgang fixen, Verifikationslauf). Betroffene Dateien:
`CLAUDE.md`, `.claude/skills/bug-class-sweep/SKILL.md`, `wiki/log.md`
(diese Datei). Kein ADR nötig (Prozess-/Tooling-Konvention, keine
Architekturentscheidung).

Nachtrag: PR #4 ohne offene CI-Checks (kein `pull_request`-Trigger im Repo)
und ohne Review-Kommentare per `merge`-Commit in `main` gemergt
(`dd909fd`). Lokaler Feature-Branch gelöscht; Löschung des Remote-Branch
`claude/hygiene-rules-codebase-f57tvf` scheiterte an einer 403-Egress-Policy
dieser Session (git push --delete) — laut Proxy-Diagnose ein bewusster
Policy-Block, kein Retry-Fall. Branch liegt bis zur manuellen Löschung durch
den Repo-Owner auf GitHub weiter herum.

## [2026-09-05] feature — Marktleiste faehrt beim Scrollen ein, DE-Quellen bestaetigt, Kurs-Sparklines, Wetter-Tagesverlauf
Vier Frontend-Wuensche umgesetzt: (1) `#markets` bekommt `.is-collapsed`
(app.css) und wird per Scroll-Listener auf `#scroll` in beiden `app.js`
ein-/ausgeblendet, sobald `scrollTop > 24`. (2) Tagesschau/Handelsblatt/FAZ
waren bereits als Tier-1/2-DE-Quellen in `config.SOURCES` vorhanden, keine
Codeaenderung noetig - Gesamtzahl aktuell 21 Quellen/47 Feeds (`run.py init`
zeigt es an). (3) `markets.py::_downsample()` speichert eine abgetastete
3-Jahres-Kursreihe (`config.MARKETS_SPARK_POINTS=24`) in neuer Spalte
`market.spark` (Migration in `store._migrate`), beide `app.js` rendern daraus
eine reine SVG-Polyline (`.mk-spark`, kein Chart-Framework). (4) `weather.py`
holt zusaetzlich `hourly`-Daten im selben Open-Meteo-Request, haelt nur den
heutigen Tag in neuer Tabelle `weather_hour`, `board_payload()` liefert
`hours` mit `isNow`-Flag; `#weather` ist jetzt ein `<div>` mit eigenem
`#weathercity`-Button (Stadtwechsel) und horizontal scrollbarem
`#weatherhours`-Streifen darunter (verschachtelte interaktive Elemente in
einem `<button>` waeren ungueltig gewesen).
Betroffen: `web/app.css` (= `docs/app.css`, Kopie), `web/app.js`,
`docs/app.js`, `web/index.html`, `docs/index.html`, `newstaker/config.py`,
`newstaker/markets.py`, `newstaker/weather.py`, `newstaker/store.py`.
Alle 63 Tests weiterhin gruen. Kein Browser-Screenshot moeglich (Sandbox ohne
Playwright/Netz zu Open-Meteo/Yahoo) - Verifikation ueber lokalen `server.py`-
Smoketest mit synthetischen DB-Daten (curl auf `/api/weather`, `/api/markets`).

## [2026-09-05] feature — Desktop-optimiertes Mehrspalten-Layout und View-Toggle

Das Frontend von News-Taker war bislang fest auf eine 390px breite Mobilkarte beschränkt.
Einführung eines responsiven Magazin-Dashboards für Desktop-Bildschirme (ab 960px):
Zweispaltiges Layout mit News-Feed links und sticky Seitenleiste (Märkte & Filter) rechts,
mehrspaltigem Aufmacher-Raster (großer Hero-Aufmacher + Nebengeschichten), zweispaltigem
Kurzmeldungs-Raster sowie modalem Suchdialog. Über einen neuen Umschalter (View-Toggle)
im Header kann am Desktop jederzeit zwischen Magazin- und Smartphone-Ansicht gewechselt werden
(gespeichert in `localStorage`). Identisch in `web/` und `docs/` umgesetzt. Betroffene Dateien:
`web/index.html`, `web/app.css`, `web/app.js`, `docs/index.html`, `docs/app.css`, `docs/app.js`,
`wiki/overview.md`, `wiki/log.md`.

