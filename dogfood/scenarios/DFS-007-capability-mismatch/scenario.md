---
id: DFS-007
type: scenario
status: current
authority: informative
description: Policy requires exact-resume but the provider only advertises best-effort — a statically-doomed run that burns the full retry budget before blocking.
---

# DFS-007: capability mismatch, resume-exact vs. best-effort

## Concern tags

`capability`, `cli-errors`

## Intent

`RunConfig.resume_capability` is set to `CAP-EXEC-RESUME-EXACT`, but the
scripted execution adapter only advertises `CAP-EXEC-RESUME-BEST-EFFORT`.
This is a *statically* doomed run — no retry could ever succeed, the
mismatch is knowable before the first attempt — yet the CLI retries it to
exhaustion like any organically flaky run before blocking. The *correct*
canonical outcome per `CONTRACT-ERRORS` is that each doomed attempt fails
with `ERR-UNSUPPORTED-CAPABILITY`, and that is exactly what is journaled.
**Fixed, confirmed (issue #16):** the CLI now also surfaces the root cause
in its own `status`/`dispatch` summary line, not just in `history`'s
`dispatch_result.error`.

## Setup

None beyond a scratch journal directory. Uses this directory's
`config.json`: `resume_capability: CAP-EXEC-RESUME-EXACT`,
`execution_capabilities: [CAP-EXEC-RESUME-BEST-EFFORT]` (the mismatch),
single scripted attempt content that is never reached.

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-007"

PYTHONPATH=src python3 -m orc_werk.cli dispatch "resume exact but only best-effort supported" \
  --config dogfood/scenarios/DFS-007-capability-mismatch/config.json \
  --run-id s5-capmismatch \
  --journal "$JOURNAL_DIR"

PYTHONPATH=src python3 -m orc_werk.cli status "$JOURNAL_DIR/s5-capmismatch.jsonl"
PYTHONPATH=src python3 -m orc_werk.cli history "$JOURNAL_DIR/s5-capmismatch.jsonl"
```

## Expected observable outcomes

- `dispatch`/`status` exit `1`.
- `status`: `work work-1: state=BLOCKED attempts=3
  candidate_fingerprint=- blocked_reason=retry-budget-exhausted
  (root_cause=ERR-UNSUPPORTED-CAPABILITY)` — issue #16's fix: the summary
  line now distinguishes this from DFS-004's genuine execution failures
  without requiring a dig into `history`. `retry-budget-exhausted` remains
  the contractually correct block reason once the budget is exhausted
  (`docs/domain/state-machines/delivery.md`); the `root_cause=` suffix is
  presentation-only surfacing of the same `dispatch_result.error` `history`
  already carried.
- `history` seq 8 (`FX-START-EXECUTION`, attempt 1) carries the real cause
  in `dispatch_result.error`: `ERR-UNSUPPORTED-CAPABILITY`, with
  `dispatch_result.details.capability: CAP-EXEC-RESUME-EXACT` and
  `operation: resume`. All three attempts show the same
  `ERR-UNSUPPORTED-CAPABILITY` in their `FX-START-EXECUTION` records.
  Synthetic execution ids follow the pattern
  `exec-capability-failure-s5-capmismatch-work-1-<n>` for every attempt —
  note this naming is used for *every* dispatch-gate failure regardless of
  actual cause (issue #16 point 3), so grepping history for
  `capability-failure` is not a reliable way to find capability mismatches
  specifically.

## Judgment notes

**Fixed, confirmed (issue #16).** Report a plain PASS each time this
scenario reproduces the `root_cause=` suffix above; the canonical error
was always present and correct in `history` — the fix only changed what
`status`/`dispatch`'s summary line surfaces. If a future change ever
regresses the suffix (back to a bare `retry-budget-exhausted` with no
root-cause hint), that is a regression to report, not a return to
baseline.

## Verification

Not executed as part of this seeding pass (only DFS-001/DFS-002 were run to
confirm the harness works end-to-end); this config is carried over
unmodified from the round-1 dogfooding session (`s5-capmismatch`), which
produced exactly the `history`/`status` shapes described above (pre-fix,
without the `root_cause=` suffix).

Re-executed against `master` for the M1 close-out sweep (2026-08-28,
`m1-closeout` checker run): confirmed live — `status` line reads exactly
`blocked_reason=retry-budget-exhausted (root_cause=ERR-UNSUPPORTED-CAPABILITY)`,
matching this doc's now-current expectation.
