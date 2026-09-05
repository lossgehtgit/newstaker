---
name: bug-class-sweep
description: Use immediately after confirming a bug in a specific file/line. Instead of fixing only that one spot, searches the whole codebase for the same pattern and fixes every occurrence in one pass. Trigger phrases: "sweep this bug class", "find all instances of this bug", or any time a bug is confirmed and Hygiene-Regel 1 (Bugklassen-Sweep) applies.
---

# Bug-Class Sweep

Ein bestätigter Bug ist nie nur eine Fundstelle — er ist ein Muster, das an
mehreren Stellen im Code vorkommen kann. Dieser Skill setzt Hygiene-Regel 1
aus `CLAUDE.md` um: jeder Bug wird sofort als Klasse behandelt.

## Ablauf

1. **Bug verstehen.** Fasse in 1-2 Sätzen zusammen, was genau falsch ist —
   nicht nur die Symptomzeile, sondern das zugrunde liegende Muster (z. B.
   "off-by-one bei Datumsvergleich mit `<` statt `<=`", "fehlendes
   `.strip()` vor Vergleich mit externem Feed-Feld", "unbehandelter
   `None`-Fall bei optionalem JSON-Feld").
2. **Muster ableiten.** Formuliere daraus eine oder mehrere konkrete
   Grep-Suchen (Funktionsname, API-Aufruf, Vergleichsoperator im Kontext,
   Feldname, Regex) — kein zu generisches Muster (sonst zu viel Rauschen),
   aber breit genug, um Varianten zu erfassen.
3. **Codebase durchsuchen.** Mit `Grep` (nicht `grep` via Bash) die gesamte
   Codebase nach dem Muster durchsuchen — `newstaker/`, `web/`, `docs/`,
   Tests, ggf. Konfigs/Workflows. Bei Bedarf mehrere Suchläufe mit
   verwandten Varianten (Umbenennungen, ähnliche Funktionen).
4. **Treffer bewerten.** Jeden Treffer einzeln prüfen: liegt hier wirklich
   dieselbe Bug-Klasse vor, oder ist der Kontext anders (z. B. bewusst
   andere Semantik)? Nur echte Treffer in die Fix-Liste aufnehmen.
5. **Alle echten Treffer in einem Durchgang fixen.** Nicht nacheinander mit
   Rückfragen — einen zusammenhängenden Satz von Edits, dann einmal
   berichten. Bei sehr vielen/heterogenen Treffern: kurz auflisten und
   fragen, falls die Fixes nicht mechanisch gleich sind.
6. **Verifizieren.** Nach den Fixes erneut mit demselben Grep-Muster suchen,
   um zu bestätigen, dass keine Instanz übersehen wurde (abgesehen von
   bewusst ausgenommenen, klar kommentierten Sonderfällen).
7. **Kurz berichten:** Anzahl gefundener Treffer, Anzahl gefixter Stellen,
   Dateien. Bei einer nennenswerten Bug-Klasse (nicht nur Tippfehler): Eintrag
   in `wiki/log.md` gemäß Update-Protokoll aus `CLAUDE.md`, plus Ergänzung des
   Präzedenzfall-Satzes bei Hygiene-Regel 1 in `CLAUDE.md`.

## Nicht tun

- Nicht nur die ursprünglich gemeldete Stelle fixen und den Rest als
  "kommt später dran" liegen lassen.
- Nicht so generisch suchen, dass massenhaft unrelated Treffer entstehen,
  die dann ungeprüft "mitgefixt" werden.
- Nicht ohne Verifikationslauf (Schritt 6) abschließen.
