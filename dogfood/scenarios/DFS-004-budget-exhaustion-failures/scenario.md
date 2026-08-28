---
id: DFS-004
type: scenario
status: current
authority: informative
description: Three consecutive execution failures exhaust the default retry budget — Work ends BLOCKED with reason retry-budget-exhausted.
---

# DFS-004: budget exhaustion via execution failures

## Concern tags

`budget`

## Intent

The Work never even produces a candidate — every scripted execution
attempt itself fails (`outcome: failed`), not a rejected candidate. Confirm
the CLI still surfaces exactly `retry-budget-exhausted` (per
`docs/domain/state-machines/delivery.md`'s block-reason vocabulary) and
that `attempts` in `status` reads `3` (the default `max_attempts`) rather
than some off-by-one count.

## Setup

None beyond a scratch journal directory. Uses this directory's
`config.json`: single work, three scripted attempts, all `outcome: failed`.

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-004"

PYTHONPATH=src python3 -m orc_werk.cli dispatch "always fails" \
  --config dogfood/scenarios/DFS-004-budget-exhaustion-failures/config.json \
  --run-id s4a-failexhaust \
  --journal "$JOURNAL_DIR"

PYTHONPATH=src python3 -m orc_werk.cli status "$JOURNAL_DIR/s4a-failexhaust.jsonl"
```

## Expected observable outcomes

- `dispatch` exit code `1` (a Work is BLOCKED, not accepted).
- `status`/`dispatch` line: `work work-1: state=BLOCKED attempts=3
  candidate_fingerprint=- blocked_reason=retry-budget-exhausted` — no
  candidate was ever identified, so the fingerprint field is `-`.
- `history`: three `FACT-EXEC-SETTLED` records with `outcome: failed`, two
  `DEC-RETRY` decisions, one final `DEC-BLOCK` whose basis cites the third
  `FACT-EXEC-SETTLED`, and a terminal `FACT-WORK-BLOCKED` with
  `reason: retry-budget-exhausted`.

## Judgment notes

`blocked_reason=retry-budget-exhausted` on its own does not distinguish
"genuinely flaky/failing execution" from other causes that also exhaust the
budget by construction (see DFS-005's rejection variant, and DFS-007's
capability-mismatch variant, which produce the *identical* surface string).
That ambiguity is expected and accepted at this bar for a real failure
loop; DFS-007's judgment notes cover why it is a known friction item
specifically for the capability-mismatch case (issue #16).

## Verification

Not executed as part of this seeding pass (only DFS-001/DFS-002 were run to
confirm the harness works end-to-end); this config is carried over
unmodified from the round-1 dogfooding session, where it produced the
outcomes above.
