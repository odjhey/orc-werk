---
id: TASK-M3C-002
type: task-card
status: draft
authority: normative
description: orc refs --resolve — shell out to the provider's own tooling to show referenced content inline; version-fragility documented, never silent.
implements: []
verifies: []
---

# TASK-M3C-002 — `orc refs --resolve`

Design source: `M3-HARDEN-THE-LOOP` Phase M3c (level four of the review
staircase); the issue #100 deferred nice-to-have. Details firm up at
dispatch. Non-negotiables carried from the phase note:

- Resolution executes the SAME command the ref row already displays —
  no second command vocabulary; what you see is what runs.
- Fragility documented per the TOON known-issues pattern: assumes the
  provider CLI surface at its pinned version; a provider upgrade
  re-probes before trust; failures surface honestly (the ref remains
  valid even when resolution fails — print the error and the manual
  command, never fabricate content).
- Read-only guarantee: resolution must never execute a mutating
  provider command; the resolve vocabulary is vetted read-only at
  construction (same judge-only bar as the assurance adapter).

## Acceptance (firmed at dispatch)

Each ref kind with a runnable resolve command (transcript, session,
candidate, mirror, command-bearing evidence) resolves inline against
real ledger data; a deliberately-broken ref degrades to the error plus
the manual command, exit code honest.
