---
id: DFS-003
type: scenario
status: current
authority: informative
description: Diamond dependency plan a → b,c → d, all accepted — fan-out then fan-in.
---

# DFS-003: diamond DAG `a → b,c → d`

## Concern tags

`dag`

## Intent

`SCN-005` (fan-in) already covers this at the contract-test level; this
scenario checks the same shape through the user-facing CLI surface: does
`status` clearly show four independent works, does dispatch order visibly
respect the dependency edges (`b`/`c` only after `a` accepts, `d` only
after both `b` and `c` accept), and is that legible from `history` without
having to reconstruct the plan from memory.

## Setup

None beyond a scratch journal directory. Uses this directory's
`config.json`: a 4-work plan (`a` → `b`,`c` → `d`, each depending on its
predecessor(s) via `condition: accepted`), each work's single scripted
attempt is `completed`/`accepted`.

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-003"

PYTHONPATH=src python3 -m orc_werk.cli dispatch "diamond dag" \
  --config dogfood/scenarios/DFS-003-diamond-dag-fanin/config.json \
  --run-id s3-diamond \
  --journal "$JOURNAL_DIR"

PYTHONPATH=src python3 -m orc_werk.cli status "$JOURNAL_DIR/s3-diamond.jsonl"
```

## Expected observable outcomes

- `dispatch` exit code `0`.
- `status` lists all four works (`a`, `b`, `c`, `d`, printed sorted by
  `work_id`), each `state=ACCEPTED attempts=1`, each with its own
  candidate fingerprint.
- In `history`, `a`'s full attempt/accept sequence (`FX-START-EXECUTION`
  through `FACT-WORK-COMPLETED` for `work_id: a`) is fully ordered before
  either `b`'s or `c`'s `FX-CLAIM-WORK`/`FACT-WORK-READY` records — `b` and
  `c` cannot become ready until `a`'s acceptance is journaled. Likewise
  `d`'s `FACT-WORK-READY` only appears after both `b` and `c` have
  completed.
- No `blocked_reason` anywhere.

## Judgment notes

`status`'s flat per-work list does not show the dependency edges
themselves — only that all four works ended ACCEPTED. Reconstructing "b and
c both gated on a's acceptance" requires reading `history` and correlating
`work_id`s across records; there is no single line that states the DAG
shape. This is acceptable at the current bar (the CLI does not print the
plan back), but is worth flagging as friction if it gets harder to follow
as plans grow past four works.

## Verification

Not executed as part of this seeding pass (only DFS-001/DFS-002 were
run to confirm the harness works end-to-end); this config is carried over
unmodified from the round-1 dogfooding session, where it ran to the
outcomes above (four works, all `ACCEPTED`, deterministic fingerprints
matching the config's candidate labels).
