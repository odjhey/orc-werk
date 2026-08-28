---
id: DFS-005
type: scenario
status: current
authority: informative
description: Budget exhaustion via three straight assurance rejections, plus the distinct single-attempt inconclusive-verdict block.
---

# DFS-005: budget exhaustion via rejections, and inconclusive

## Concern tags

`budget`

## Intent

Two related but distinct block paths that must not be confused with each
other or with DFS-004's execution-failure path:

1. Every attempt *produces* a candidate, but assurance rejects all three —
   budget exhausted via `retry-budget-exhausted`, same reason string as
   DFS-004 despite a different root cause (execution succeeded, assurance
   disagreed).
2. A single attempt whose assurance verdict is `inconclusive` blocks
   immediately, on attempt 1, with a *different* reason
   (`assurance-inconclusive`) and without consuming the rest of the retry
   budget — `inconclusive` is not a retryable-then-exhausted path, it is
   its own terminal block condition (per
   `docs/domain/state-machines/delivery.md`).

## Setup

None beyond a scratch journal directory. Two configs in this directory:
`config-rejections.json` (three attempts, each `completed` +
`assurance.verdict: rejected`) and `config-inconclusive.json` (one attempt,
`completed` + `assurance.verdict: inconclusive`).

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-005"

PYTHONPATH=src python3 -m orc_werk.cli dispatch "always rejected" \
  --config dogfood/scenarios/DFS-005-budget-exhaustion-rejections-inconclusive/config-rejections.json \
  --run-id s4b-rejexhaust \
  --journal "$JOURNAL_DIR"

PYTHONPATH=src python3 -m orc_werk.cli dispatch "inconclusive verdict" \
  --config dogfood/scenarios/DFS-005-budget-exhaustion-rejections-inconclusive/config-inconclusive.json \
  --run-id s4c-inconclusive \
  --journal "$JOURNAL_DIR"

PYTHONPATH=src python3 -m orc_werk.cli status "$JOURNAL_DIR/s4b-rejexhaust.jsonl"
PYTHONPATH=src python3 -m orc_werk.cli status "$JOURNAL_DIR/s4c-inconclusive.jsonl"
```

## Expected observable outcomes

**Rejections (`s4b-rejexhaust`):**
- `dispatch` exit `1`.
- `status`: `work work-1: state=BLOCKED attempts=3
  candidate_fingerprint=<fp of X3> blocked_reason=retry-budget-exhausted` —
  note a fingerprint *is* present here (unlike DFS-004): a candidate was
  identified and rejected on the final attempt too.
- `history`: three `FACT-ASSURE-SETTLED` records with `verdict: rejected`
  (candidates `X1`, `X2`, `X3`), two `DEC-RETRY`, one `DEC-BLOCK`, terminal
  `FACT-WORK-BLOCKED` with `reason: retry-budget-exhausted`.

**Inconclusive (`s4c-inconclusive`):**
- `dispatch` exit `1`.
- `status`: `work work-1: state=BLOCKED attempts=1
  candidate_fingerprint=<fp of Y1> blocked_reason=assurance-inconclusive` —
  `attempts=1`, not `3`; the budget was never exhausted, this is a
  different block path entirely.
- `history`: exactly 19 records (same shape as DFS-001's happy path up
  through `FACT-ASSURE-SETTLED`), with `FACT-ASSURE-SETTLED.verdict:
  inconclusive`, then `DEC-BLOCK` (basis: that same fact, attempt_number
  1), `FX-BLOCK-WORK`, `FACT-WORK-BLOCKED` with `reason:
  assurance-inconclusive` — no `DEC-RETRY` at all.

## Judgment notes

The two block reasons (`retry-budget-exhausted` vs.
`assurance-inconclusive`) are the intended, correct way `status` lets a
human tell these apart *without* reading `history` — this is the positive
counter-example to DFS-007's capability-mismatch friction, where the
surface string collapses distinct causes into one. If a future change ever
makes `inconclusive` retry instead of block-immediately, or makes it emit
`retry-budget-exhausted` too, that is a contract-relevant regression, not
just friction — escalate accordingly.

## Verification

Not executed as part of this seeding pass (only DFS-001/DFS-002 were run to
confirm the harness works end-to-end); both configs are carried over
unmodified from the round-1 dogfooding session, where they produced the
outcomes above.
