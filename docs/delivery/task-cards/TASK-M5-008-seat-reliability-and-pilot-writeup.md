---
id: TASK-M5-008
type: task-card
status: current
authority: normative
description: Author docs/delivery/seat-reliability.md (model hangs/rate-limits per seat) and a pilot write-up recording what this migration's first delivery (m5-omp-harness-pilot) actually observed.
implements:
  - ADR-0007
verifies: []
---

# TASK-M5-008 — `docs/delivery/seat-reliability.md` + pilot write-up

Design source: `ADR-0007`; `M5-OMP-FIRST-DELIVERY` Phase 4;
`nother-guide`'s rung-4 seat-reliability log. Depends on
`m5-omp-harness-pilot`'s own ledger journal (this pilot's run) and at
least one subsequent M5 card's delivery for comparison data.

## The gap

`nother-guide`'s adoption ladder names a seat-reliability log as a rung-4
artifact — "model hangs/rate-limits per seat, appended same-day" — and
`ADR-0007`'s Consequences section commits to feeding this pilot's own
findings into it. No such log exists yet in orc-werk, and the pilot run
that is the migration's acceptance evidence (`m5-omp-harness-pilot`) has
no durable write-up distinguishing what actually happened (hangs, retries,
model-family friction, hook false-positives/negatives) from what
`ADR-0007` predicted.

## Outcome

`docs/delivery/seat-reliability.md` exists as an append-only log: one
dated entry per observed seat reliability event (a model hang, a
rate-limit, a hook misfire, a schema-rejection surprise), each entry
naming the seat (scout/ship/verify), the run/work id, the model, and the
observed symptom — appended the same day an event is observed, never
retroactively reconstructed from memory (`T5`/`T6`). The pilot write-up
(`docs/reports/2026-09-07-m5-pilot-retrospective.md`) records what
`m5-omp-harness-pilot`'s own run, and the ten deliveries after it, actually
showed: the capability test's predictions (`TASK-M5-001`) held at the
mechanism level, with one corrected card premise (no OMP-native worktree
auto-creation); the hook guards (`TASK-M5-005`) could not have fired under
real seat traffic because that card had not shipped yet as of this
write-up (still `EXECUTING` in the ledger) — discipline held by agent
definition and convention only; and the `V7` model-family pairing (ship on
`anthropic`, verify nominally on `openai-codex`) surfaced real friction —
Codex usage-limit deaths forced a same-day substitution to
`google-antigravity/gemini-3.8-flash`, which then became the standing,
unamended practice across the whole wave (see the write-up's `V7` section
and the log's 2026-09-07 entries).

## In scope

- `docs/delivery/seat-reliability.md` — new file, append-only log
  structure, seeded with this pilot's own first entry (or entries). The
  log file and its first four entries landed early, in
  `fix-verify-seat-fallback`, because the same-day rule required
  recording the day's events immediately; two further entries (the `V7`
  family-pairing drift and a live `test_hung_observer` hit) landed with
  this card's own delivery, same-day per `T5`/`T6`.
- The pilot write-up drawing on `m5-omp-harness-pilot`'s ledger journal
  (`orc history m5-omp-harness-pilot`), the PR, and any recorded
  verdict — delivered as
  `docs/reports/2026-09-07-m5-pilot-retrospective.md`, extended beyond the
  pilot alone to the ten further deliveries the ledger accumulated by the
  time this card was picked up, per its own "at least one subsequent M5
  card's delivery for comparison data" dependency.

## Out of scope

Building tooling that auto-generates the log from the ledger (a rung-5
"generated retro," explicitly dormant per `M5-OMP-FIRST-DELIVERY`'s Phase
4, with its own named trigger — the first week of real M5 ledger data).
This card is the log's format and its first hand-written entries, not
automation.

## Acceptance

- `docs/delivery/seat-reliability.md` exists, passes `docs_check.py`'s
  frontmatter check, and contains at least one dated entry referencing
  `m5-omp-harness-pilot` by run id.
- Each entry names the seat, the run/work id, the model, and the observed
  symptom — not a vague narrative summary.
- The pilot write-up states, with evidence (ledger history, PR, or
  verdict citation), whether `TASK-M5-001`'s capability-test predictions
  held for this real run, and whether the `V7` model-family pairing
  surfaced any friction.
- The log is append-only in practice: a later PR touching this file adds
  entries rather than rewriting or deleting earlier ones.

## Status

Fully delivered. `docs/delivery/seat-reliability.md`'s format and first
four entries landed in `fix-verify-seat-fallback` (PR #268); this card's
own PR adds the two 2026-09-07 entries above and the pilot write-up
(`docs/reports/2026-09-07-m5-pilot-retrospective.md`). Nothing in this
card's scope remains open. One finding surfaced by the write-up is
explicitly out of this card's own scope and left for an operator/ADR
decision: `ADR-0007`'s `V7` ruling names `openai-codex` specifically as
the verify family, but observed practice has been
`google-antigravity/gemini-3.8-flash` for the entire 2026-09-07 wave with
no `openai-codex` verdict recorded since the pilot's own day-one deaths —
per `AGENTS.md` rule 4, this needs a formal `ADR-0007` amendment rather
than a continuing silent deviation.
