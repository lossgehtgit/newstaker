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

## Git Workflow

Ist-Zustand bei Einführung dieser Regeln (Stand 2026-09-05, per `gh`-Äquivalent
über die GitHub-API geprüft): Repo `lossgehtgit/newstaker` ist **public**,
Default-Branch ist **`main`**. Für `main` ist **keine Branch Protection**
aktiv (`protected: false`, keine Required Status Checks, kein Review-Zwang).
Solo-Projekt — ein einziger Collaborator (`lossgehtgit`). Einziger
GitHub-Actions-Workflow ist `.github/workflows/update.yml` (Feed-Abruf +
`docs/`-Publish per Cron/`workflow_dispatch`/Push auf `main`); er läuft
**nicht** auf `pull_request`-Events — es gibt also aktuell keinen
automatischen CI-Check, der auf einem PR erscheinen würde.

Konsequenz: Nichts davon verhindert technisch, dass ein PR mit rotem CI oder
ganz ohne CI-Bestätigung gemerged wird. Die folgenden Regeln sind reine
Selbstdisziplin — es gibt keinen GitHub-Mechanismus, der sie erzwingt.

1. **Hauptbranch bleibt sauber.** Für jede nicht-triviale Änderung einen
   eigenen Feature-Branch (`feature/<kurzbeschreibung>` oder
   `fix/<kurzbeschreibung>`), nie direkt auf `main` entwickeln. Wenn möglich
   dafür einen git worktree nutzen (`git worktree add
   ../<repo>-worktrees/<branchname> -b <branchname>`), damit der Hauptordner
   immer auf `main` bleibt, während die Feature-Arbeit isoliert in einem
   eigenen Ordner läuft. In einer Claude-Code-Session entspricht das dem
   `EnterWorktree`-Tool bzw. der expliziten Bitte "in einem Worktree
   arbeiten".
2. **Commit-Konvention:** Conventional Commits — `feat:`, `fix:`, `docs:`,
   `refactor:`, `chore:`, `test:` als Präfix, danach eine kurze,
   aussagekräftige Beschreibung im Imperativ.
3. **PR-Merge-Gate ist Pflicht**, unabhängig davon ob GitHub es technisch
   erzwingt: Vor jedem Merge die Checks des PRs prüfen (`gh pr checks <n>`
   bzw. äquivalent über die GitHub-API/-MCP-Tools) und bestätigen, dass alle
   relevanten Jobs grün sind. Laufen Checks noch: warten, nicht mergen in der
   Annahme, Probleme fallen später schon auf. Da dieses Repo **kein Branch
   Protection** hat, ist das der einzige Schutzmechanismus — er wird nie
   übersprungen, auch nicht bei kleinen PRs. Hinweis: Aktuell läuft keine CI
   auf `pull_request`-Events (siehe oben), `gh pr checks` zeigt also bis auf
   Weiteres nichts an — die Regel gilt trotzdem, sobald/falls ein
   PR-getriggerter Check hinzukommt, und bis dahin ersetzt eine bewusste
   Diff-Durchsicht vor dem Merge die fehlende automatische Bestätigung.
4. **Nach einem gemergten PR sofort aufräumen:** Remote-Branch und ggf.
   lokalen Worktree löschen, statt sie liegen zu lassen.
5. **Secrets nie committen:** keine echten Secrets (`*_SECRET`, `*_KEY`,
   Tokens, private Keys, JWTs) in getrackten Dateien. Secrets leben nur in
   `.env` (gitignored) oder im Secret-Management der Hosting-Plattform. Vor
   jedem Commit kurz gegenchecken, dass der Diff nichts Verdächtiges enthält
   — auch bei generierten Config-/Beispieldateien, die harmlos aussehen.
6. **Destruktive Git-Operationen** (force-push, `reset --hard`,
   History-Rewrites, `branch -D`) nur nach expliziter Rückfrage im Chat —
   eine einmalige Zustimmung gilt nicht automatisch für spätere, ähnliche
   Fälle.

## Hygiene-Regeln

Feste Arbeitsweise ab 2026-09-05, damit Fehler und manuelle Routinen nicht bei
jeder Session neu auftauchen bzw. neu erklärt werden müssen.

1. **Bugfix ⇒ Bugklassen-Sweep.** Jeder gefundene Bug wird sofort als Klasse
   behandelt: mit grep/Suche die gesamte Codebase nach dem gleichen Muster
   durchsuchen und alle Treffer in einem Durchgang fixen — nicht nur die eine
   Fundstelle, und nicht "beim nächsten Mal wieder einzeln finden". Siehe
   Skill `.claude/skills/bug-class-sweep/` als Vorlage für diesen Ablauf.
   *Präzedenzfälle:* noch keiner.
2. **Detail-Änderung ⇒ Zusammenfassung mitziehen.** Wer einen
   Status/Checkbox/Zähler an einer Stelle ändert (TODO-Liste, Statusseite,
   Wiki-Index), aktualisiert im selben Schritt auch die Stelle, die das
   aggregiert (Fortschrittstabelle, `index.md`-Header, Dashboard-Zahl). Sonst
   laufen Detail und Zusammenfassung leise auseinander.
   *Präzedenzfälle:* noch keiner.
3. **"Kann nicht passieren" ⇒ als Test verankern, nicht als Kommentar.** Wenn
   ein Befund mit einer Begründung wie "das Feld ist immer gesetzt" oder
   "dieser Pfad ist aktuell nicht erreichbar" geschlossen wird, dann wird
   genau die Annahme, von der das abhängt, in einem automatisierten Test
   verankert. Sonst entwertet die nächste Vertragsänderung diese
   Entscheidung, ohne dass irgendwo etwas anschlägt.
   *Präzedenzfälle:* noch keiner.
4. **"Behoben" ⇒ die falsche Ausgabe muss tatsächlich weg sein.** Eine
   zusätzliche Logzeile oder ein abgefangener Fehler ist kein Fix. Vor dem
   Abhaken den tatsächlichen Fehlerpfad auslösen und prüfen, was am Ende
   ankommt (UI, API-Response, Datei) — nicht nur, dass intern etwas geloggt
   wird.
   *Präzedenzfälle:* noch keiner.
5. **Neue Automatisierung ⇒ echten Effekt prüfen, nicht Exit-Code.** Jeder
   wiederkehrende/geplante Job muss seinen tatsächlichen Effekt verifizieren
   (Inhalt der Antwort, erzeugtes Artefakt, geänderter Zustand) statt nur
   "kein Fehler geworfen". Zusätzlich vor dem Erzeugen von
   Branches/PRs/Issues prüfen, ob dafür nicht schon ein offener Vorgang
   existiert (Idempotenz).
   *Präzedenzfälle:* noch keiner.

Sobald real einer dieser Fälle eintritt, wird direkt ein kurzer
Präzedenzfall-Satz zur jeweiligen Regel ergänzt (was ist passiert, wann,
wodurch jetzt abgesichert) — das macht die Regel nachvollziehbar statt
abstrakt und hilft bei Grenzfällen.

## Wiederkehrende Routinen als Skills

Jede manuelle Routine, die mehr als zweimal in ähnlicher Form erklärt wird,
ist ein Kandidat für einen eigenen, wiederverwendbaren Claude-Code-Skill
(Slash-Command) unter `.claude/skills/<name>/SKILL.md`, statt sie jedes Mal im
Fließtext zu wiederholen. Vorlage: `.claude/skills/bug-class-sweep/SKILL.md`
(automatisiert Hygiene-Regel 1). Neue Skills nach demselben Muster anlegen:
kurzer, fokussierter Name, klare "wann greift das"-Beschreibung im
Frontmatter, prägnante Schritt-für-Schritt-Anweisungen im Body.
