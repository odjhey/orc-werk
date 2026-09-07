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
retroactively reconstructed from memory (`T5`/`T6`). A pilot write-up
(as a dated entry or a linked report under `docs/reports/`) records what
`m5-omp-harness-pilot`'s own run actually showed: whether the capability
test's predictions (`TASK-M5-001`) held, what the seat-hook capability
cycle (`TASK-M5-005` — tested to exhaustion across three attempt cycles
and abandoned 2026-09-07; it never fired in production) actually cost in
attempts and model time and what it taught about the limits of
`tool_call`-hook enforcement, and whether the `V7` model-family pairing
(ship on `anthropic`, verify on `openai-codex`) surfaced any friction.

## In scope

- `docs/delivery/seat-reliability.md` — new file, append-only log
  structure, seeded with this pilot's own first entry (or entries). The
  log file and its first four entries landed early, in
  `fix-verify-seat-fallback`, because the same-day rule required
  recording the day's events immediately; the pilot write-up below
  remains this card's open deliverable.
- The pilot write-up drawing on `m5-omp-harness-pilot`'s ledger journal
  (`orc history m5-omp-harness-pilot`), the PR, and any recorded verdict.

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

## Closure — 2026-09-07 (write-up half delivered)

`docs/delivery/seat-reliability.md`'s append-only log (the first half of
this card) landed early in `fix-verify-seat-fallback`, and its 2026-09-07
entries (hook misfires from `TASK-M5-005`'s three run identities, each
naming a seat, run/work id, model, symptom, and consequence per this
card's own log contract) are appended in that same log, dated, additive.
The hook's retirement itself is an operator ruling spanning all three run
identities, not a single seat/run/work/model event the log's own contract
can name — it is recorded instead in `ADR-0007`'s hook-retirement
amendment and narrated, with citations, in the pilot write-up's §3.

The pilot write-up (the second half) is delivered as
`docs/reports/2026-09-07-m5-pilot-retrospective.md`. It declares its own
cutoff anchor (a `master` commit and an ISO instant) up front and derives
every count in it against that anchor, or against an individually dated
instant where a narrower fact is stated — per the counting lesson (issue
#285) the milestone itself produced. It answers, with cited evidence: which
of `TASK-M5-001`'s capability predictions held and which were falsified by
the seat-hook cycle (§1); where seat discipline held under real seat
traffic and where it needed operator judgment (§2); what the seat-hook
capability cycle cost and taught (§3, `TASK-M5-005`); the counting lesson
itself (§4); and which of the eight TASK-M5 cards carry a terminal
delivery, and on which rungs seat discipline now rests (§5).

The pilot write-up also states, with evidence, whether the `V7`
model-family pairing surfaced friction (§2, item 4): it did — two
`openai-codex` verify spawns died at `usage_limit_reached` on 2026-09-06
and were hand-substituted to `google-antigravity/gemini-3.8-flash`, per
`docs/delivery/seat-reliability.md`'s 2026-09-06 entries and `ADR-0007`'s
`V7` amendment.

Both halves of this card are now delivered; nothing in this card's own
In scope/Acceptance sections above is rewritten — this section is additive.
