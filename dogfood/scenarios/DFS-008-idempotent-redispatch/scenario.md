---
id: DFS-008
type: scenario
status: current
authority: informative
description: Re-running dispatch with the same run id against an already-completed journal must be a true no-op — zero new lines, zero new effects.
---

# DFS-008: idempotent re-dispatch over a completed journal

## Concern tags

`idempotency`

## Intent

An operator re-running the exact same `dispatch` command — say, a retry of
a flaky invocation, or a script that re-invokes dispatch defensively —
against a journal directory where that `run_id` already reached a terminal
state must not duplicate effects, re-execute anything, or grow the
journal. This is a direct, CLI-level check of `INV-*` idempotency
guarantees (effect idempotency keys derived from `delivery_run_id` +
`work_id` + `attempt_number` + effect id) as observed by a human just
running the command twice.

## Setup

Reuses DFS-001's config content (same `run_id: s1-happy`, same single
accepted attempt) so this scenario can be run standalone: first dispatch
to completion, then dispatch again unchanged.

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-008"

PYTHONPATH=src python3 -m orc_werk.cli dispatch "write the changelog" \
  --config dogfood/scenarios/DFS-008-idempotent-redispatch/config.json \
  --run-id s1-happy \
  --journal "$JOURNAL_DIR"

LINES_BEFORE=$(wc -l < "$JOURNAL_DIR/s1-happy.jsonl")

PYTHONPATH=src python3 -m orc_werk.cli dispatch "write the changelog" \
  --config dogfood/scenarios/DFS-008-idempotent-redispatch/config.json \
  --run-id s1-happy \
  --journal "$JOURNAL_DIR"

LINES_AFTER=$(wc -l < "$JOURNAL_DIR/s1-happy.jsonl")
echo "before=$LINES_BEFORE after=$LINES_AFTER"
```

## Expected observable outcomes

- Both `dispatch` invocations: exit `0`, identical stdout (`work work-1:
  state=ACCEPTED attempts=1 candidate_fingerprint=<same fp both times>`).
- `LINES_BEFORE` equals `LINES_AFTER` exactly (`19` for this config) — the
  second dispatch appended **zero** new journal records. Re-running
  `orchestrator.run()` against an already-terminal projection must not
  re-emit `FACT-WORK-READY`, must not re-dispatch an execution, must not
  re-request assurance.
- No new `.jsonl` file, no second run id, no stray directory created.

## Judgment notes

If the second dispatch instead re-appends the full sequence (line count
roughly doubles) or errors instead of no-op'ing, that is a hard idempotency
regression — escalate as BUG immediately, this is a hard bar
(`DELIVERY-STANCE`'s "journal integrity and portability" / determinism
bars), not a soft one.

## Verification

Executed against `master` (worktree `feat/dogfood-corpus`) on 2026-08-28 as
part of confirming DFS-001/DFS-002: dispatching the identical command
twice against the same journal directory left the line count at `19`
before and after, with byte-identical stdout on both runs. Confirmed
known-good.
