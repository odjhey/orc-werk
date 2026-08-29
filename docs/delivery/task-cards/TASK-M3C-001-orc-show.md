---
id: TASK-M3C-001
type: task-card
status: current
authority: normative
description: orc show — terminal narrative view of a run (briefs, prompts-as-derived, executions, candidates, verdicts, refs), composing existing readers only.
implements: []
verifies: []
---

# TASK-M3C-001 — `orc show <run> [work]`

Design source: `M3-HARDEN-THE-LOOP` Phase M3c (the operator's four-level
review staircase; this card is levels two and three). Details firm up at
dispatch. Non-negotiables carried from the phase note:

- Pure composition of existing readers (journal, persisted config, times
  sidecar, extension payloads) — no new storage, no new recording.
- Prompt provenance is derived and displayed, never guessed: per work,
  show which text actually became the executor's prompt (briefs entry vs
  intent fallback), the issue #111 lesson.
- Reference-first: full content is pointed at via resolve commands (the
  `orc refs` vocabulary), never inlined from provider stores.
- Born conforming to the issue #113 listing convention.

## Acceptance (firmed at dispatch)

A reviewer answers "what was asked, who did it, what was produced, what
was judged, where's the full content" for every work/attempt of a real
multi-work run (e.g. `task-m2-003-practice`) from `orc show` output
alone, with each deeper level one named command away.
