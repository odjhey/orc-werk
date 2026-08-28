---
id: DFS-001
type: scenario
status: current
authority: informative
description: Single work, single attempt, accepted on the first try — the CLI's straight-line happy path.
---

# DFS-001: happy path, single work

## Concern tags

`happy-path`, `cli-output`

## Intent

The most basic thing the CLI has to get right: submit an intent, dispatch
one Work, one execution attempt completes, one candidate is accepted, the
Work reaches ACCEPTED. If this is not clean and legible, nothing else
matters. Also a baseline for comparing `status`/`history` output shape
against the retry/DAG/budget scenarios.

## Setup

None beyond a scratch journal directory. Uses this directory's
`config.json` (single work, single scripted attempt, `outcome: completed`,
`assurance.verdict: accepted`).

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-001"

PYTHONPATH=src python3 -m orc_werk.cli dispatch "write the changelog" \
  --config dogfood/scenarios/DFS-001-happy-path-single-work/config.json \
  --run-id s1-happy \
  --journal "$JOURNAL_DIR"

PYTHONPATH=src python3 -m orc_werk.cli status "$JOURNAL_DIR/s1-happy.jsonl"

PYTHONPATH=src python3 -m orc_werk.cli history "$JOURNAL_DIR/s1-happy.jsonl"
```

## Expected observable outcomes

- `dispatch` exit code `0`.
- `dispatch` stdout: `work work-1: state=ACCEPTED attempts=1 candidate_fingerprint=<fp>` (no
  `blocked_reason` suffix).
- `status` on the same journal reports the same line, plus `intent: s1-happy`, exit `0`.
- `history` shows exactly 19 records, seq 1..19, ending
  `FACT-WORK-COMPLETED`; the sequence is
  `FACT-INTENT-SUBMITTED, FX-CREATE-WORK, FACT-WORK-CREATED, FX-CLAIM-WORK,
  FACT-WORK-CLAIMED, FACT-WORK-READY, DEC-DISPATCH, FX-START-EXECUTION,
  FACT-EXEC-STARTED, FACT-EXEC-SETTLED, FX-IDENTIFY-CANDIDATE,
  FACT-CANDIDATE-OBSERVED, DEC-REQUEST-ASSURANCE, FX-START-ASSURANCE,
  FACT-ASSURE-STARTED, FACT-ASSURE-SETTLED, DEC-ACCEPT, FX-COMPLETE-WORK,
  FACT-WORK-COMPLETED` — no `DEC-RETRY`, no `DEC-BLOCK`.
- No `blocked_reason` anywhere in `status`/`dispatch` output.

## Judgment notes

None expected here beyond the mechanical checks above — this scenario is
the legibility baseline other scenarios' output gets compared against.

## Verification

Executed against `master` (worktree `feat/dogfood-corpus`) on 2026-08-28:
exit `0`, `work work-1: state=ACCEPTED attempts=1
candidate_fingerprint=fp-32f9dbceb02fbe89eb72171f` — fingerprint matches
the round-1 dogfooding run byte-for-byte (deterministic candidate
identity). Confirmed known-good.
