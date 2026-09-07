---
id: SEAT-RELIABILITY
type: log
status: current
authority: informative
description: Append-only log of observed seat reliability events (model hangs, rate-limits, usage-limit deaths, hook misfires) per `TASK-M5-008`, seeded from `m5-omp-harness-pilot`'s own run.
---

# Seat reliability log

This is an append-only log: one dated entry per observed seat reliability
event (a model hang, a rate-limit, a usage-limit death, a hook misfire, a
schema-rejection surprise). Each entry names the seat (scout/ship/verify),
the run/work id, the model, and the observed symptom and its consequence.
Entries are appended the same day the event is observed and are never
retroactively reconstructed from memory (`T5`/`T6`) — see `TASK-M5-008` for
the format's origin and the pilot write-up this log feeds.

## 2026-09-06

- **verify** / `m5-omp-harness-pilot` `docs` / `openai-codex/gpt-5.6-sol:high`
  — spawn `VerifyM5Pilot` died within 8.8s of
  `Codex error event: The usage limit has been reached
  (code=usage_limit_reached)`. Consequence: nothing recorded in the ledger
  for this spawn; the run's assurance budget was not spent (no
  `FACT-ASSURE-SETTLED`), so the kernel could re-request assurance of the
  same candidate on the next spawn.
- **verify** / `m5-omp-harness-pilot` `docs` / `openai-codex/gpt-5.6-sol:high`
  — second spawn `VerifyM5PilotB` (09:13:01Z) died within 6.1s of the same
  `usage_limit_reached` error. This spawn's `.omp/agents/verify.md` already
  carried a 3-entry prioritized `model` list; OMP did not fall through to
  entry 2 on a spawn-time usage-limit error — frontmatter list order is
  resolution preference only, and runtime quota fallback requires a
  `retry.fallbackChains` key on the exact model, which this user config
  lacked. Consequence: same as above, nothing recorded; this observation is
  the direct trigger for the present PR (verify seat model list reordered
  so the model with quota goes first, since spawn-time fallthrough cannot
  be relied on).
- **verify** / `m5-omp-harness-pilot` `docs` / `google-antigravity/gemini-3.8-flash:high`
  — spawn `VerifyM5PilotC`, substituted in by hand after the two Codex
  deaths above, completed in 4m37s. Verdict `accepted`, ledger seq 16 of
  `m5-omp-harness-pilot` (`orc history m5-omp-harness-pilot --limit 0`).
  `V7` (verify family ≠ ship family) was satisfied — ship ran
  `anthropic/claude-sonnet-5`, verify ran `google-antigravity/gemini-3.8-flash`,
  a non-Anthropic family — but `ADR-0007`'s stated pairing (verify on the
  `openai-codex` family specifically) deviated in practice. This is a
  recorded deviation, not an amendment: revisit once Codex quota is
  restored, or once a `retry.fallbackChains` key is added so a future
  usage-limit death falls through automatically instead of requiring a
  hand substitution.
- **ship** / `m5-omp-harness-pilot` `docs` / `anthropic/claude-sonnet-5` — no
  incident; completed in 11m19s. Recorded here as a clean baseline row: the
  ship seat for the same run/work, same day, with nothing to report.

## 2026-09-07

- **verify** / ten settled runs (`fix-262-docs-polish` `polish` ×2,
  `task-m5-003` `docs`, `fix-254-active-filter` `filter`, `task-m5-006`
  `skill`, `fix-266-reobservation` `obs`, `task-m5-001` `report`,
  `adopt-270-attempt-binding` `adopt`, `docs-external-candidate-lane`
  `lane`, `chore-verify-followups` `cleanup`) / `google-antigravity/gemini-3.8-flash`
  — every verify verdict recorded on this date for these ten named
  deliveries ran on this one model; `openai-codex` did not fire once across
  the whole wave (checked directly against each run's
  `executor-identity/v1.model`). This count is scoped to the ten deliveries
  this card's write-up tracks and is a same-day correction of this row (it
  originally said "nine," missing `chore-verify-followups`' seq-16 settlement
  at `01:37:18Z`, which predates this row's own authoring); it is a snapshot
  as of `2026-09-07T02:07:16Z`. A whole-ledger recount as of the same cutoff
  finds more 2026-09-07 verify settlements outside this ten-delivery scope
  (e.g. `task-m5-002`, `gh-pr:279`) — see the pilot write-up's live-ledger
  note (`docs/reports/2026-09-07-m5-pilot-retrospective.md`) for the
  whole-ledger figures and cutoff discipline. Consequence: `V7`'s
  risk-control purpose (verify on a materially different family than ship)
  held throughout, but the 2026-09-06 entry above called the Codex
  substitution "a recorded deviation, not an amendment: revisit once Codex
  quota is restored" — by end of this date that substitution is the standing
  practice across two calendar days and ten deliveries with no `openai-codex`
  verdict in between. `ADR-0007`'s `V7` text still names `openai-codex`
  specifically; this now needs a formal amendment rather than a second week
  of quiet deviation (see
  `docs/reports/2026-09-07-m5-pilot-retrospective.md`).
- **verify** / `task-m5-006` `skill` / `google-antigravity/gemini-3.8-flash`
  (`VerifyM5006`) — during PR #275's audit, a first full-suite `bash
  scripts/check.sh` run failed on the flaky `test_hung_observer` test
  (unchanged test, `EXIT 1`, no `check: green` line); a second run passed.
  Consequence: a live, independent reproduction of open issue #232
  (`ObserverHungObserverTest residual flakiness under concurrent machine
  load`) under real verify-seat load, not a synthetic probe — ledger
  citation `.orc/task-m5-006/journal.jsonl` seq 16
  (`FACT-ASSURE-SETTLED`, `review-findings/v1`).
