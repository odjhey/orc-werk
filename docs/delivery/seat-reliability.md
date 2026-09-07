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

- **verify** / `task-m5-005` `hook` / `google-antigravity/gemini-3.8-flash`
  — hook misfire: attempt 2 (seq 26) probed the freshly-installed
  `.omp/extensions/orc-seat.ts` guard live and found it satisfiable by
  command text that merely mentions `orc record` without invoking it
  (`echo fake-orc-record --command "orc record run-x --work w --verdict
  accepted"` yielded `{recorded:true}`). Consequence: rejected; filed as
  issue #290 (command-text-bound enforcement).
- **verify** / `task-m5-005-guards` `guards` / `google-antigravity/gemini-3.8-flash`
  — hook misfire: attempt 2 (seq 26) found the rewritten worktree fence
  bypassable via a symlinked write/edit, a colon-split path
  (`./safe:/../../outside-probe/...`), and a `://`-containing path the
  guard's own extractor skips outright — while the same fence denied a
  legitimate own-worktree path on a case-insensitive filesystem.
  Consequence: rejected; filed as issues #296/#297 (path canonicalization).
- **verify** / `task-m5-005-sensor` `sensor` / `google-antigravity/gemini-3.8-flash`
  — hook misfire: attempt 3 (seq 36) found the *fix* for #296/#297 itself
  introduced a new escape — a case-insensitive `local://` scheme match
  (`LOCAL_SCHEME_RE = /^local:\/\//i`) that the installed write tool does
  not share (case-sensitive `local:` only), letting `Local://../../sibling/
  hit.txt` land outside the ship's own worktree while the guard reported
  `ALLOW`. Consequence: rejected; filed as issue #298 (scheme
  adjudication) — the third escape class, introduced by the fix for the
  second.
- **operator** / `TASK-M5-005` — after three run identities (`task-m5-005`,
  `task-m5-005-guards`, `task-m5-005-sensor`) each exhausted a three-attempt
  budget on a new escape class every time (above), the `tool_call` hook
  rung was retired by operator ruling rather than re-attempted a fourth
  time. Landed as PR #300 (`hook-retire-decision`) and PR #299
  (`docs/delivery/M5-omp-first-delivery.md`, `TASK-M5-005`'s and
  `TASK-M5-008`'s cards, `README.md`, `.omp/agents/verify.md`). Seat
  discipline now rests on tool restriction, GitHub branch protection, and
  after-the-fact ledger audit (`docs/reports/2026-09-07-m5-pilot-retrospective.md`
  §5). No `tool_call`-hook event is expected in this log after this date;
  the mechanism no longer exists on `master`.
