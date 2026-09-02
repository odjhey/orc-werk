---
id: DFS-014
type: scenario
status: current
authority: informative
description: "orc dispatch --wait's blocking-poll internalization: wake on movement (exit 3), wake on timeout (exit 4), and --timeout without --wait rejected (exit 2)."
---

# DFS-014: `dispatch --wait` blocking poll

## Concern tags

`wait`

## Intent

`SCN-017` (issue #210) lets an operator or agent block on `orc dispatch
--wait` instead of re-invoking `dispatch` on a timer. This scenario checks
the three exit-code-distinguishing behaviors a human actually relies on:
a `--wait` invocation wakes and returns the moment the run's pending
fingerprint moves (a settlement recorded from a second shell mid-wait);
an unchanged fingerprint past `--timeout` seconds exits distinctly (`4`,
not `3` or `0`); and `--timeout` supplied without `--wait` is rejected
up front rather than silently ignored.

## Setup

Uses this directory's `config.json` (`{}`, no attempts) so the first
dispatch starts `work-1` and stops cleanly pending its execution outcome
-- the same pending-mode entry point as `DFS-013`/the CLI reference's
own `--wait` walkthrough. No pre-built fixture beyond that.

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-014"

# Stage 1: ordinary (non-wait) dispatch establishes the baseline pending
# state -- EXECUTING, awaiting execution-outcome.
PYTHONPATH=src python3 -m orc_werk.cli dispatch "wait demo" \
  --config dogfood/scenarios/DFS-014-wait-blocking-poll/config.json \
  --run-id wait-demo \
  --journal "$JOURNAL_DIR"

# Stage 2: start --wait in the background; from a "second shell" (here,
# the same script, staged after a short sleep) mutate the run's persisted
# config mid-wait to add the outcome + a scripted candidate for work-1's
# attempt. --wait must wake on the very next internal pass that observes
# the mutated config, printing that pass's ordinary report and exiting 3.
PYTHONPATH=src python3 -m orc_werk.cli dispatch --run-id wait-demo --journal "$JOURNAL_DIR" \
  --wait --timeout 30 --poll-interval 1 > /tmp/dfs014-wait-out.txt 2>&1 &
WAIT_PID=$!
sleep 2
python3 - "$JOURNAL_DIR/wait-demo/config.json" <<'PY'
import json, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg.setdefault("attempts", {}).setdefault("work-1", [{}])
cfg["attempts"]["work-1"][0]["outcome"] = "completed"
cfg["attempts"]["work-1"][0]["candidate"] = {"label": "hello"}
json.dump(cfg, open(p, "w"), indent=2)
PY
wait "$WAIT_PID"
echo "wait exit=$?"
cat /tmp/dfs014-wait-out.txt

# Stage 3: re-run --wait with a short --timeout and nothing changed --
# distinct wait-timeout exit.
PYTHONPATH=src python3 -m orc_werk.cli dispatch --run-id wait-demo --journal "$JOURNAL_DIR" \
  --wait --timeout 2 --poll-interval 0.3
echo "timeout exit=$?"

# Stage 4: --timeout without --wait is a validation error, not a silent
# no-op.
PYTHONPATH=src python3 -m orc_werk.cli dispatch --run-id wait-demo --journal "$JOURNAL_DIR" --timeout 5
echo "novalidate exit=$?"
```

## Expected observable outcomes

- Stage 1: exit `3`, `work work-1: state=EXECUTING attempts=1
  candidate_fingerprint=- pending=true awaiting=execution-outcome
  attempt=1`.
- Stage 2: the backgrounded `--wait` process prints nothing until it wakes
  (silence during every internal pass that observes no movement, per
  `SCN-017`), then wakes with exit `3` on the pass immediately after the
  mid-wait config mutation lands, printing the same report shape a
  non-`--wait` dispatch observing that resting state would: `work work-1:
  state=ASSURING attempts=1 candidate_fingerprint=fp-30dd7c8c1f588de26f8f26c8
  pending=true awaiting=assurance-verdict attempt=1`, with the usual
  `next:` block (record the assurance verdict, `--abandon-work` recovery
  affordance, re-run command). The candidate fingerprint is deterministic
  across runs of this exact config.
- Stage 3: exit `4`, the same `ASSURING`/`assurance-verdict` pending report
  as stage 2 (since nothing moved) plus a trailing `wait timeout: --timeout
  2.0s elapsed with the pending fingerprint unchanged (SCN-017 step 8) --
  the run is exactly as pending as before; re-invoking (with or without
  --wait) is always safe` line.
- Stage 4: exit `2`, canonical `ERR-VALIDATION` JSON: `{"error":
  "ERR-VALIDATION", "message": "--timeout requires --wait (SCN-017);
  --wait alone waits indefinitely", ...}` with a `next` field naming both
  fixes (add `--wait`, or drop `--timeout`) -- `--timeout` is never
  silently ignored.

## Judgment notes

The interesting failure mode here is not the exit codes themselves (those
are asserted exactly, `tests/scenarios` territory) but *legibility*: does
a human watching stage 2's backgrounded process understand that the long
silence before it wakes is correct behavior (`SCN-017`'s "nothing is
printed for a pass that finds no movement") rather than a hang? The
`next:` block on wake should be enough on its own, without needing to
read this scenario, to tell an operator what happened and what to do
next.

## Verification

Executed against `master` (worktree `docs-dogfood-frictions`) on
2026-09-03 in a `/tmp` sandbox (`/tmp/dfs014-scratch`), run verbatim from
the repo root with `DOGFOOD_SCRATCH=/tmp/dfs014-scratch`: stage 1 exit `3`
as expected; stage 2's backgrounded `--wait` woke with exit `3` and the
`ASSURING`/`assurance-verdict` report (`candidate_fingerprint=
fp-30dd7c8c1f588de26f8f26c8`, matching the CLI reference doc's own
captured fingerprint for the same `{"label": "hello"}` candidate byte-for-
byte -- deterministic candidate identity confirmed); stage 3 exit `4` with
the `wait timeout:` trailer; stage 4 exit `2` with the exact
`ERR-VALIDATION` JSON above. Confirmed known-good.
