---
id: DFS-010
type: scenario
status: current
authority: informative
description: Six malformed/hostile dispatch configs — four already fail closed correctly, one is silently accepted (issue #17), one now rests pending per SCN-007/PR #29.
---

# DFS-010: config abuse — invalid JSON, cycle, dup id, unknown dep, unknown key, missing attempts

## Concern tags

`config-validation`, `cli-errors`

## Intent

The CLI dispatch-config loader (`src/orc_werk/cli/config.py`) is CLI-owned,
non-normative composition — but it sits directly on the user-facing
boundary, so `DELIVERY-STANCE`'s "canonical errors at user-facing
boundaries" bar still applies to how it fails. Round 1 found it is
fail-open in exactly two ways where the rest of the system (the
`MemoryWorkGraph`/plan-validation layer underneath it) is already
fail-closed. This scenario runs all six abuse cases together so the
contrast is visible: four fail loud and correctly, one fails silently
(issue #17, `unknownkey.json`). The sixth, `missingattempts.json`, was
originally grouped with the issue-#17 failures too, but since PR #29
(pending/incremental mode, `TASK-M1-002`) its missing-`attempts` shape is
the valid fully-incremental case, not a validation gap — see its
expected-outcome entry below.

## Setup

None beyond a scratch journal directory. Six configs in this directory,
each exercising one abuse:

- `invalid.json` — not valid JSON at all (`{ this is not json`).
- `cycle.json` — a two-work plan where `a` depends on `b` and `b` depends
  on `a`.
- `dup.json` — a plan listing `work_id: "a"` twice.
- `unknowndep.json` — work `a` depends on `work_id: "ghost"`, which is not
  in the plan.
- `unknownkey.json` — an otherwise-valid single-work config plus a
  top-level `totally_bogus_key` typo.
- `missingattempts.json` — a two-work plan (`a`, `b`) whose `attempts` only
  scripts outcomes for `a`, leaving `b` with no scripted attempts at all.

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-010"

for name in invalid cycle dup unknowndep unknownkey missingattempts; do
  echo "=== $name ==="
  PYTHONPATH=src python3 -m orc_werk.cli dispatch "config abuse: $name" \
    --config "dogfood/scenarios/DFS-010-config-abuse/$name.json" \
    --journal "$JOURNAL_DIR/$name"
  echo "exit=$?"
done
```

## Expected observable outcomes

**`invalid.json` — correct, confirmed:** exit `2`, stderr
`{"error": "ERR-VALIDATION", "message": "config file is not valid JSON:
...", "details": {"path": "..."}}`. No journal directory/file is created
at all — `load_config` fails before `JSONLJournal` is even constructed.

**`cycle.json` — correct, confirmed:** exit `2`, stderr
`{"error": "ERR-VALIDATION", "message": "work-graph plan has a dependency
cycle involving work_id: 'a'", "details": {"work_id": "a"}}`. Journal file
*is* created but has exactly **1** record (`FACT-INTENT-SUBMITTED`) —
intent submission is journaled before plan validation runs, then the
cycle is rejected before `FX-CREATE-WORK`.

**`dup.json` — correct, confirmed:** exit `2`, stderr
`{"error": "ERR-VALIDATION", "message": "work-graph plan has a duplicate
work_id: 'a'", "details": {"work_id": "a"}}`. Journal: 1 record, same
shape as `cycle.json`.

**`unknowndep.json` — correct, confirmed:** exit `2`, stderr
`{"error": "ERR-VALIDATION", "message": "work-graph plan dependency names
a work not present in the plan: 'ghost'", "details": {"dep_id": "ghost",
"work_id": "a"}}`. Journal: 1 record.

**`unknownkey.json` — known bug, issue #17:** expected (post-fix)
canonical `ERR-VALIDATION` at load time, rejecting the unrecognized
`totally_bogus_key`, no journal created. Actual on current `master`: the
unknown key is silently dropped and the run proceeds to completion exactly
as if it were not there — exit `0`, `work work-1: state=ACCEPTED
attempts=1`, full 19-record journal. A typo'd config key (e.g.
`exeuction_capabilities` for `execution_capabilities`) produces no signal
at all that anything was misspelled.

**`missingattempts.json` — superseded by PR #29 (pending/incremental mode,
`TASK-M1-002`), re-scoped per Item 2's issue-#17 re-scope:** since PR #29,
pending/incremental mode is the M1a default, so a work with no `attempts`
coverage is no longer an error — it is the valid fully-incremental case.
Confirmed on current `master`: work `a` (fully scripted) completes and
reaches `ACCEPTED`; work `b` — which has no scripted attempts at all —
starts its first attempt (`FACT-EXEC-STARTED` journaled) and rests
`EXECUTING`, `pending=true`, `awaiting=execution-outcome`, exactly per
`SCN-007`. `dispatch` exits `3` (run non-terminal, pending operator
input), not `1`/budget-exhausted. Issue #17's *remaining* scope for this
config shape is load-time strict validation only: `unknownkey.json`
(a structurally-unknown top-level key) is still the live bug case, and any
stricter attempts-coverage requirement is opt-in (e.g. `--strict`), never
a load-time rejection of the missing-`attempts` shape itself (per Item 2's
re-scope, PR #29 verification ruling).

## Judgment notes

The four correct cases are worth re-running on every checker pass mainly
as a regression guard on `MemoryWorkGraph`'s plan validation — they are
unlikely to break, but if they ever silently started succeeding that would
be a serious contract regression (fail-open on plan integrity), not mere
friction. The remaining known-bug case (`unknownkey.json`): report BUG
each time, quoting exit code and whether the config's mistake was signaled
at all — the point of this scenario is exactly that a human would not
otherwise notice their config had a typo until output looked wrong minutes
later. `missingattempts.json` is no longer a bug case (see above) but is
still worth re-running as a regression guard on the pending/incremental
default itself.

## Verification

`invalid.json`, `cycle.json`, `dup.json`, `unknowndep.json` executed
against `master` (worktree `feat/dogfood-corpus`) on 2026-08-28: outputs
above (exact error text, `details`, and 1-line-journal-or-none) are
transcribed verbatim from that run. `unknownkey.json` was **not**
re-executed (still known-failing per issue #17); its "actual on current
master" description is transcribed from the round-1 dogfooding session's
recorded journal (`s8d-unknown.jsonl`, 19 records ending
`FACT-WORK-COMPLETED`).

`missingattempts.json` **was** re-executed against `master` (worktree
`docs-m1a-batch`, commit `fab370f`, post-PR-#29) on 2026-08-28:

```sh
JOURNAL_DIR=/tmp/dfs010/missingattempts
PYTHONPATH=src python3 -m orc_werk.cli dispatch "config abuse: missingattempts" \
  --config "dogfood/scenarios/DFS-010-config-abuse/missingattempts.json" \
  --journal "$JOURNAL_DIR"
```

Real output:

```
run: s8h-missing
journal: /tmp/dfs010/missingattempts/s8h-missing.jsonl
work a: state=ACCEPTED attempts=1 candidate_fingerprint=fp-5041bf1f713df204784353e8
work b: state=EXECUTING attempts=1 candidate_fingerprint=- pending=true awaiting=execution-outcome attempt=1
pending: run is non-terminal, awaiting operator-recorded input for: b
exit=3
```

Journal: 26 records, last record `FACT-WORK-COMPLETED` for work `a`
(work `b`'s last record is `FACT-EXEC-STARTED`, attempt 1, matching
`SCN-007` invocation-1 shape) — this supersedes the round-1 recorded
`s8h-missing.jsonl` (38 records ending `FACT-WORK-BLOCKED`,
`reason: retry-budget-exhausted`), which reflected pre-PR-#29 behavior.
