# Änderungsprotokoll

Append-only. Ein Eintrag pro abgeschlossener Aufgabe. **Diese Datei nie
komplett lesen** — wird mit der Zeit groß. Stattdessen:

```bash
grep "^## \[" wiki/log.md | tail -3
```

Neue Einträge immer **anhängen**, nie bestehende Einträge ändern oder löschen.

---

## [2026-09-05] docs — Wiki-System eingerichtet

Persistentes, dateibasiertes Wiki unter `wiki/` angelegt als externes
Gedächtnis für künftige Sessions (Einzelprojekt-Repo, daher ohne
`<projekt>/`-Unterordner). Angelegt: `wiki/index.md`, `wiki/overview.md`,
`wiki/architecture.md`, `wiki/database.md`, `wiki/decisions/README.md`
(ADR-Vorlage), `wiki/log.md` (diese Datei). `CLAUDE.md` neu angelegt mit
Abschnitt „Wiki" (Struktur, Query-/Update-Routine, Session-Start-Protokoll,
Token-Sparregeln). Keine Code-Änderungen, kein ADR nötig für diesen Schritt
selbst.
