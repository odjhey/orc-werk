---
id: DFS-005
type: scenario
status: current
authority: informative
description: Budget exhaustion via three straight assurance rejections, plus the distinct single-attempt assurance-budget exhaustion by inconclusive verdicts.
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
2. A single attempt whose assurances all settle `inconclusive` blocks on
   attempt 1 with a *different* reason (`assurance-inconclusive`) and
   without consuming any of the retry budget. Since `ADR-0006` this is
   explicitly a **second, separate budget**, not a one-shot rule: an
   `inconclusive` settlement with assurance budget remaining re-requests
   assurance of the *same* candidate under a new assurance identity
   (`INV-021`, `STATE-DELIVERY` item 11); only exhausting
   `max_assurance_attempts` blocks the Work. So case 2 now settles
   `inconclusive` twice under the default budget of `2` — one re-request,
   then the block. Setting `max_assurance_attempts: 1` reproduces the
   pre-`ADR-0006` behavior (block on the first `inconclusive`) exactly, and
   is also what every journal written before that field existed folds
   under.

## Setup

None beyond a scratch journal directory. Two configs in this directory:
`config-rejections.json` (three attempts, each `completed` +
`assurance.verdict: rejected`) and `config-inconclusive.json` (one attempt,
`completed` + `assurances: [{inconclusive}, {inconclusive}]` under the
default `max_assurance_attempts: 2` — the ordered per-attempt settlement
array `INV-021` needs, since one candidate now receives more than one
assurance within the one attempt).

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
  `attempts=1`, not `3`; the *retry* budget was never touched, this is a
  different block path entirely.
- `next:` names which budget ran out and which did not: `(assurance budget
  exhausted: 2 of 2 assurances of this candidate settled inconclusive --
  INV-021; the execution retry budget was never consumed, 2 of 3 attempts
  remain unused)`.
- `history`: exactly 23 records — DFS-001's happy-path shape up through the
  first `FACT-ASSURE-SETTLED(inconclusive)`, then a SECOND
  `DEC-REQUEST-ASSURANCE` (basis: that inconclusive settlement) +
  `FX-START-ASSURANCE` + `FACT-ASSURE-STARTED` for the *same* candidate
  under a new assurance id, a second `FACT-ASSURE-SETTLED(inconclusive)`,
  then `DEC-BLOCK` (basis: that second fact, `attempt_number` 1,
  `assurance_number` 2, `max_assurance_attempts` 2), `FX-BLOCK-WORK`,
  `FACT-WORK-BLOCKED` with `reason: assurance-inconclusive` — no
  `DEC-RETRY` and no second `FACT-EXEC-STARTED` at all.
- The two `FX-START-ASSURANCE` idempotency keys differ only by a trailing
  `|2` on the second (`INV-020` as amended by `ADR-0006`): the first keeps
  the pre-decision key form verbatim.

## Judgment notes

The two block reasons (`retry-budget-exhausted` vs.
`assurance-inconclusive`) are the intended, correct way `status` lets a
human tell these apart *without* reading `history` — this is the positive
counter-example to DFS-007's capability-mismatch friction, where the
surface string collapses distinct causes into one. If a future change ever
makes an `inconclusive` verdict consume `max_attempts`, or makes it emit
`retry-budget-exhausted`, that is a contract-relevant regression, not just
friction — escalate accordingly. (`ADR-0006` deliberately changed *when*
`inconclusive` blocks — after the assurance budget is exhausted rather than
on the first settlement — while keeping both invariants above: a distinct
reason string, and zero retry-budget consumption.)

## Verification

`config-rejections.json` is carried over unmodified from the round-1
dogfooding session, where it produced the outcomes above and was not
re-executed for this restatement. `config-inconclusive.json` was re-run
against the `ADR-0006` implementation (issue #264) and produced exactly the
outcomes recorded above: exit `1`, `attempts=1`,
`blocked_reason=assurance-inconclusive`, 23 journal records, two
`FACT-ASSURE-SETTLED(inconclusive)` for one candidate in one attempt.
