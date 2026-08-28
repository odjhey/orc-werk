---
id: DFS-010
type: scenario
status: current
authority: informative
description: Six malformed/hostile dispatch configs — four already fail closed correctly, two are silently accepted (issue #17).
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
contrast is visible: four fail loud and correctly, two fail silently
(issue #17).

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

**`missingattempts.json` — known bug, issue #17:** expected (post-fix)
canonical `ERR-VALIDATION` at load time (or an explicit documented
opt-out), rejecting a planned work with no `attempts` coverage, no journal
created. Actual on current `master`: work `a` completes normally, then
work `b` — which has no scripted attempts — hits `ScriptedExecution`'s
"no scripted outcome for this attempt" (`ERR-NOT-FOUND`) on every attempt,
which the orchestrator converts into synthetic
`exec-capability-failure-...` failed attempts (same masking pattern as
DFS-006/DFS-007), exhausting the budget: exit `1`,
`blocked_reason=retry-budget-exhausted` for `b` — the real cause ("this
work was never scripted") is buried exactly like issue #16's cases.

## Judgment notes

The four correct cases are worth re-running on every checker pass mainly
as a regression guard on `MemoryWorkGraph`'s plan validation — they are
unlikely to break, but if they ever silently started succeeding that would
be a serious contract regression (fail-open on plan integrity), not mere
friction. The two known-bug cases: report BUG each time, quoting exit code
and whether the config's mistake was signaled at all — the point of this
scenario is exactly that a human would not otherwise notice their config
had a typo or a validation gap until output looked wrong minutes later.

## Verification

`invalid.json`, `cycle.json`, `dup.json`, `unknowndep.json` executed
against `master` (worktree `feat/dogfood-corpus`) on 2026-08-28: outputs
above (exact error text, `details`, and 1-line-journal-or-none) are
transcribed verbatim from that run. `unknownkey.json` and
`missingattempts.json` were **not** re-executed (both are known-failing
per issue #17); their "actual on current master" descriptions are
transcribed from the round-1 dogfooding session's recorded journals
(`s8d-unknown.jsonl`, 19 records ending `FACT-WORK-COMPLETED`;
`s8h-missing.jsonl`, 38 records ending `FACT-WORK-BLOCKED` with
`reason: retry-budget-exhausted` for work `b`).
