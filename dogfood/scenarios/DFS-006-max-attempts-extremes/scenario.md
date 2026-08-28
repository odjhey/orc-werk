---
id: DFS-006
type: scenario
status: current
authority: informative
description: max_attempts extremes — override to 1, override to a very large budget, and config value 0 (expected canonical ERR-VALIDATION post-fix).
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
   replaced by the default (`3`) instead of rejected, because
   `build_run_config` computes `max_attempts_override or
   config.get("max_attempts") or RunConfig().max_attempts` (`src/orc_werk/cli/config.py`)
   and `0` is falsy in Python, so it is indistinguishable from "not
   supplied." **Expected (post-fix) behavior is canonical `ERR-VALIDATION`
   at config-load time**, before any dispatch — `0` is a nonsensical retry
   budget (`INV-018`/`INV-019` require the ability to make at least one
   attempt), not a synonym for "use the default."

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

**3 (`max_attempts: 0`) — expected (post-fix):** exit `2`, canonical
`{"error": "ERR-VALIDATION", ...}` on stderr, **no journal file created**
(rejected at config-load, before the journal is even opened).

**3 — actual on current `master` (known-failing, pending fix):** `0` is
silently treated as "not supplied" and the run proceeds with the default
`max_attempts=3`. Because `config-zero.json`'s `attempts` only scripts one
`failed` attempt, attempts 2-3 hit `ScriptedExecution`'s "no scripted
outcome for this attempt" path (`ERR-NOT-FOUND`), which the orchestrator
converts into a *synthetic* failed execution
(`exec-capability-failure-s9d-zeromax-work-1-2`, `...-3`) rather than
propagating the load-time config error — this is the same masking pattern
as issue #16/#17. Exit `1`, `blocked_reason=retry-budget-exhausted`, 21
journal records. This divergence is expected and tracked (see DFS-README's
issue #17 note); do not "fix" this scenario file to match — it stays
pinned to the *correct* contract behavior until the config-validation fix
lands.

## Judgment notes

Case 3 is the one to watch closely on every checker run: report BUG (not
FRICTION) as long as it reproduces the "silent fallback to default 3, with
synthetic capability-failure attempts standing in for the real config
error" behavior described above, quoting the actual exit code and
`blocked_reason` observed. The moment this scenario's actual run starts
producing `ERR-VALIDATION`/exit `2` with no journal file, it has passed —
flip the "known-failing" framing away in the same PR that ships the fix.

## Verification

Not executed as part of this seeding pass (only DFS-001/DFS-002 were run to
confirm the harness works end-to-end). Cases 1 and 2 are carried over
unmodified from the round-1 dogfooding session (`s4d`, `s4e`), where they
produced the outcomes described above; case 3's "actual on current
master" description is likewise transcribed from round 1's `s9d-zeromax`
run and cross-checked by reading `src/orc_werk/cli/config.py`'s
`build_run_config` (the `... or ...` falsy-drop) directly.
