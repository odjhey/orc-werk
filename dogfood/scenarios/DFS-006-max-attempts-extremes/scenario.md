---
id: DFS-006
type: scenario
status: current
authority: informative
description: max_attempts extremes — override to 1, override to a very large budget, and config value 0 (rejected with canonical ERR-VALIDATION at load time).
---

# DFS-006: `--max-attempts`/config extremes: 1, very large, 0

## Concern tags

`budget`, `config-validation`, `cli-errors`

## Intent

Boundary-test the retry-budget knob at both ends, plus the degenerate `0`
case that round 1 found silently mishandled:

1. `max_attempts=1` (via `--max-attempts` CLI override) — the tightest
   possible budget: a single failed attempt must block immediately, no
   retry.
2. A very large `max_attempts` override — confirms nothing overflows or
   behaves oddly at scale; a failure followed by a success should simply
   retry-then-accept exactly as DFS-002 does, just with room to spare.
3. `max_attempts: 0` **in the config file** — round 1 found this silently
   replaced by the default (`3`) instead of rejected (`0` was falsy-dropped
   by an `or`-chain in `build_run_config`). Fixed in the round-1 fix PR:
   correct behavior is canonical `ERR-VALIDATION` before any dispatch —
   `0` is a nonsensical retry budget (`INV-018`/`INV-019` require the
   ability to make at least one attempt), not a synonym for "use the
   default."

## Setup

None beyond a scratch journal directory. Three configs in this directory:
`config-one.json` (single failing attempt, no CLI override baked in —
pass `--max-attempts 1`), `config-large.json` (fail then succeed, pass
`--max-attempts 1000000000`), `config-zero.json` (`max_attempts: 0` in the
file itself, no CLI override).

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-006"

# 1: override to 1 — must block after exactly one failed attempt
PYTHONPATH=src python3 -m orc_werk.cli dispatch "override to 1 attempt" \
  --config dogfood/scenarios/DFS-006-max-attempts-extremes/config-one.json \
  --run-id s4d-override1 --max-attempts 1 \
  --journal "$JOURNAL_DIR"

# 2: override to a very large budget — fail once, then succeed on retry 2
PYTHONPATH=src python3 -m orc_werk.cli dispatch "override huge budget" \
  --config dogfood/scenarios/DFS-006-max-attempts-extremes/config-large.json \
  --run-id s4e-overridebig --max-attempts 1000000000 \
  --journal "$JOURNAL_DIR"

# 3: max_attempts: 0 in the config file, no CLI override
PYTHONPATH=src python3 -m orc_werk.cli dispatch "zero max_attempts" \
  --config dogfood/scenarios/DFS-006-max-attempts-extremes/config-zero.json \
  --journal "$JOURNAL_DIR"
```

## Expected observable outcomes

**1 (override to 1):** exit `1`. `status`: `work work-1: state=BLOCKED
attempts=1 candidate_fingerprint=- blocked_reason=retry-budget-exhausted`.
`history`: 13 records — `FACT-EXEC-SETTLED` (`outcome: failed`) then
straight to `DEC-BLOCK`/`FX-BLOCK-WORK`/`FACT-WORK-BLOCKED`, **no**
`DEC-RETRY` at all, because the budget was already exhausted after attempt
1.

**2 (very large override):** exit `0`. `status`: `work work-1:
state=ACCEPTED attempts=2 candidate_fingerprint=<fp of "OK">`. `history`:
23 records — one `FACT-EXEC-SETTLED` (`outcome: failed`), one `DEC-RETRY`,
then a normal completed/accepted attempt 2. A budget of a billion made no
functional difference versus the default 3 here; it exists only to prove
the override plumbs through and nothing chokes on a large int.

**3 (`max_attempts: 0`) — correct, confirmed:** exit `2`, stderr
`{"error": "ERR-VALIDATION", "message": "max_attempts (config
max_attempts) must be a positive integer, got 0", "details":
{"max_attempts": 0, "source": "config max_attempts"}}`. No `.jsonl`
journal file is written (the journal *directory* is created empty, since
`JSONLJournal` is constructed before the run config is validated — a
cosmetic quirk, not state corruption). The same rejection fires for
`--max-attempts 0` on the flag (with `"source": "--max-attempts flag"`)
and for negative/non-integer values. This case regressed in round 1
(round-1 BUG-2: `0` is falsy in Python, so the loader's old
`override or config or default` chain silently replaced an explicit `0`
with the default `3` and the run proceeded to a misleading
`retry-budget-exhausted` block) and was fixed by the round-1 fix PR
(`_validate_max_attempts` + explicit `is not None` precedence in
`src/orc_werk/cli/config.py`); guarded by
`tests/scenarios/test_cli_dogfood_fixes.py`. The broader
strict-config-schema work (unknown keys, attempts coverage) remains open
as issue #17 — see DFS-010.

## Judgment notes

Case 3 is a regressed-then-fixed case: if any checker run ever sees the
old behavior again (exit `1`, silent fallback to the default budget,
synthetic capability-failure attempts standing in for the real config
error), escalate as BUG immediately — the deterministic guard lives in
`tests/scenarios/test_cli_dogfood_fixes.py`, so a reappearance means that
suite has a hole. Cases 1 and 2 are mechanical boundary checks; nothing
judgment-heavy expected there.

## Verification

Cases 1 and 2 were not executed as part of this seeding pass; they are
carried over unmodified from the round-1 dogfooding session (`s4d`,
`s4e`), where they produced the outcomes described above. Case 3 was
executed against post-round-1-fix `master` (merged into this branch) on
2026-08-28: both the config-embedded `0` and the `--max-attempts 0` flag
variant produced the canonical `ERR-VALIDATION`/exit `2` outputs
transcribed verbatim above.
