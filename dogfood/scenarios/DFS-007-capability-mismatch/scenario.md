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
mismatch is knowable before the first attempt — yet the current CLI
retries it to exhaustion like any organically flaky run and reports the
same `retry-budget-exhausted` string DFS-004 and DFS-005 use for genuinely
retryable failures. This is known friction (issue #16), not a contract
violation: the *correct* canonical outcome per `CONTRACT-ERRORS` is that
each doomed attempt fails with `ERR-UNSUPPORTED-CAPABILITY`, and that is
exactly what is journaled — it is just not surfaced anywhere a human would
look first.

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
  candidate_fingerprint=- blocked_reason=retry-budget-exhausted` —
  **indistinguishable at this surface from DFS-004's genuine execution
  failures.** This is the friction, not a bug: the string is contractually
  correct (`retry-budget-exhausted` is the right block reason once the
  budget is exhausted — `docs/domain/state-machines/delivery.md`), it is
  just uninformative about *why* every attempt failed.
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

**Known friction — issue #16.** Report FRICTION (not BUG) each time this
scenario reproduces cleanly: the canonical error is present and correct in
`history`, it is only invisible from `status`/`dispatch`'s summary line
without digging into `dispatch_result.error`. If a future change starts
surfacing `blocked_reason=retry-budget-exhausted
(root_cause=ERR-UNSUPPORTED-CAPABILITY)` or similar as issue #16 proposes,
treat that as the friction resolving — update this scenario's expected
`status` line in the same PR, do not silently leave it stale.

## Verification

Not executed as part of this seeding pass (only DFS-001/DFS-002 were run to
confirm the harness works end-to-end); this config is carried over
unmodified from the round-1 dogfooding session (`s5-capmismatch`), which
produced exactly the `history`/`status` shapes described above.
