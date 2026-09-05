# CLAUDE.md

Projektkontext für Claude Code in diesem Repo (`lossgehtgit/newstaker`,
News-Taker — deterministischer, KI-freier persönlicher Nachrichtentracker).
Kurzfassung: Python-Backend (`newstaker/`) + zwei statische Frontend-Kopien
(`web/` lokal-live, `docs/` GitHub-Pages-Export). Details siehe Wiki.

## Wiki

Dieses Repo hat ein persistentes, dateibasiertes Wiki unter `wiki/` — externes
Gedächtnis, damit nicht jede Session die ganze Codebase neu einlesen muss.

### Struktur

```
wiki/
  index.md          Master-Katalog aller Seiten, immer zuerst lesen
  log.md            append-only Änderungsprotokoll — NIE komplett lesen, nur grep
  overview.md        Tech-Stack, Einstiegspunkte, Run-/Testbefehle
  architecture.md     Pipeline, Modulverantwortung, Determinismus-Mechanik
  database.md         SQLite-Schema im Detail
  decisions/          Architecture Decision Records (Context → Decision → Consequences)
```

Einzelprojekt-Repo, deshalb keine `<projekt>/`- oder `shared/`-Unterordner.

Jede Seite trägt Frontmatter:

```yaml
---
title: "Seitentitel"
type: overview | architecture | database | decision | pattern | ...
project: newstaker
updated: YYYY-MM-DD
---
```

### Query — Pflicht vor jeder nicht-trivialen Aufgabe

1. `wiki/index.md` lesen.
2. `grep "^## \[" wiki/log.md | tail -3` (nicht die ganze Datei).
3. Die passende(n) Seite(n) aus `wiki/` lesen.
4. Kurz zusammenfassen, was du bereits weißt — mit Seitenverweisen — und
   explizit sagen, wenn etwas veraltet wirkt. Lastentragende Aussagen gegen
   den echten Code gegenchecken, nicht blind aus dem Wiki übernehmen.

### Update — Pflicht nach jeder Aufgabe, die Code betroffen hat

1. Relevante Wiki-Seiten selbst aktualisieren (gezielte Edits bevorzugen,
   kompletter Rewrite nur wenn nötig).
2. `wiki/log.md`-Eintrag anhängen, festes Format:
   ```
   ## [YYYY-MM-DD] <tag: feature/fix/docs> — <ein Satz was gemacht wurde>
   Kurzbeschreibung, betroffene Dateien, ggf. Link auf eine ADR.
   ```
3. Bei einer nennenswerten Architekturentscheidung: ADR unter
   `wiki/decisions/<slug>.md` anlegen (Vorlage in `wiki/decisions/README.md`),
   dann `wiki/index.md` und `wiki/log.md` nachziehen.

### Session-Start-Protokoll

1. Diese Datei (automatisch gelesen).
2. `wiki/index.md` lesen.
3. Letzte 3 `log.md`-Einträge per grep (siehe oben) — nie die ganze Datei.
4. Kurz berichten: welche Wiki-Seiten existieren, wann zuletzt aktualisiert,
   ob etwas veraltet wirkt.
5. Fragen, woran heute gearbeitet wird.

### Token-Sparregeln

- `wiki/log.md` nie komplett laden — immer `grep "^## \[" wiki/log.md | tail -N`.
- Andere große, nur-anhängende Dateien (z. B. `SESSION_REPORT.md`) nicht
  komplett laden, sondern gezielt greppen, außer explizit "lies die ganze
  Datei" verlangt wird.
- Bei Wiki-Updates gezielte Edits statt kompletter Neuschreibung bevorzugen.
