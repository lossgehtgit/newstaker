# Architecture Decision Records

Ein ADR pro nennenswerter Architekturentscheidung, als
`wiki/decisions/<kurzer-slug>.md`. Frontmatter wie jede andere Wiki-Seite
(`type: decision`), Inhalt in drei Abschnitten:

```markdown
---
title: "<Entscheidung in einem Satz>"
type: decision
project: newstaker
updated: YYYY-MM-DD
---

## Context
Was war die Ausgangslage/das Problem?

## Decision
Was wurde entschieden?

## Consequences
Was folgt daraus — Trade-offs, was dadurch bewusst NICHT geht?
```

Nach dem Anlegen: Eintrag in `wiki/index.md` ergänzen und in `wiki/log.md`
darauf verlinken.
