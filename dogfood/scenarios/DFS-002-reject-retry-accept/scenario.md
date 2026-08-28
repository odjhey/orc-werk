---
id: DFS-002
type: scenario
status: current
authority: informative
description: First candidate rejected, second candidate accepted — the retry loop over an assurance rejection.
---

# DFS-002: reject → retry → accept

## Concern tags

`retry`, `cli-output`

## Intent

Exercise the retry loop driven by an assurance rejection (not an execution
failure): attempt 1 completes and identifies a candidate, that candidate is
rejected, attempt 2 completes with a different candidate, that one is
accepted. Confirms `DEC-RETRY` is journaled with the right basis and that
`status` reflects the *final* attempt count and *final* candidate
fingerprint, not the rejected one.

## Setup

None beyond a scratch journal directory. Uses this directory's
`config.json` (single work, two scripted attempts: candidate `C1`
rejected, candidate `C2` accepted).

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-002"

PYTHONPATH=src python3 -m orc_werk.cli dispatch "fix the flaky test" \
  --config dogfood/scenarios/DFS-002-reject-retry-accept/config.json \
  --run-id s2-retry \
  --journal "$JOURNAL_DIR"

PYTHONPATH=src python3 -m orc_werk.cli history "$JOURNAL_DIR/s2-retry.jsonl"
```

## Expected observable outcomes

- `dispatch` exit code `0`.
- `dispatch`/`status` report `work work-1: state=ACCEPTED attempts=2
  candidate_fingerprint=<fp of C2>` — the fingerprint of the *accepted*
  candidate (`C2`), not the rejected one (`C1`).
- `history` shows 29 records ending `FACT-WORK-COMPLETED`, with exactly one
  `DEC-RETRY` (seq 17) whose `basis` cites the `FACT-ASSURE-SETTLED` record
  carrying `verdict: rejected` for `C1`'s fingerprint, and one `DEC-ACCEPT`
  (seq 27) whose basis cites the `FACT-ASSURE-SETTLED` for `C2`'s
  fingerprint with `verdict: accepted`.
- The rejected candidate's fingerprint (`C1`) appears in history (as
  `FACT-CANDIDATE-OBSERVED`/`FACT-ASSURE-SETTLED`) but never in the final
  `status` line.

## Judgment notes

A human reading only the final `status` line should not need to guess
whether there was a retry — `attempts=2` is the signal — but confirming
*why* (a rejection, not a failure) requires `history`. That split is
expected and fine at this milestone: `status` answers "where did it end
up", `history` answers "how did it get there".

## Verification

Executed against `master` (worktree `feat/dogfood-corpus`) on 2026-08-28:
exit `0`, `work work-1: state=ACCEPTED attempts=2
candidate_fingerprint=fp-5db4be00cf68bc7cb5dff7de` — fingerprint matches
the round-1 dogfooding run's accepted (`C2`) candidate byte-for-byte.
Confirmed known-good. Re-dispatching the identical command against the
same journal directory (see DFS-008) reproduced the same output with zero
new journal lines, confirming idempotency along the way.
