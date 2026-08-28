---
id: PLAYBOOK-CLI-USAGE
type: playbook
status: current
authority: informative
description: Living guide for using the orc CLI day-to-day, including the known-issues ledger consulted while dogfooding live.
---

# CLI usage guide

Living operational guide for the `orc` CLI. This document evolves with the tool: the **Known issues** section is updated the moment a defect or footgun is found (before the fix ships) and pruned when fixes merge, so anyone using the CLI live knows what to route around. Informative only — canonical semantics live in the contracts.

## Quickstart

```bash
# from the repo root (or pip install -e . for a real `orc` command)
alias orc='PYTHONPATH=src python3 -m orc_werk.cli'

orc dispatch "<intent text>" --config cfg.json [--journal DIR] [--max-attempts N]
orc status  <journal.jsonl | run-id | dir>
orc history <journal.jsonl | run-id | dir>
```

- Journals default to `./.orc/<run_id>.jsonl` (gitignored — durable run artifacts never belong in version control). A bare run id passed to `status`/`history` resolves against `./.orc`.
- Exit codes: `0` all work ACCEPTED · `1` any work BLOCKED (or other non-accepted terminal) · `2` usage/config error (canonical error JSON on stderr) · `3` run non-terminal, pending operator input (`TASK-M1-002`, `SCN-007`) — a work is resting at `EXECUTING`/`ASSURING` because its current attempt's outcome has not been recorded yet; `dispatch`/`status` output names which work(s) and what they're awaiting (`execution-outcome` or `assurance-verdict`).
- Re-running the same `dispatch` over an existing journal is a safe no-op resume (idempotent by effect key); it is also the crash-recovery mechanism — just run the same command again.
- **Pending/incremental mode is the default (M1a).** A config whose `attempts` entry for a work's next attempt is missing or absent entirely is not an error: `dispatch` starts that attempt, journals `FACT-EXEC-STARTED`, and stops cleanly at exit `3` with nothing fabricated for the missing settlement. Record the real outcome (and, once known, the assurance verdict) into the config's `attempts` entry for that work and re-run the identical `dispatch` command — it resumes via ordinary idempotent replay, no separate "resume" command. Fully scripted configs (every outcome supplied up front, as in the Config section below) remain supported unchanged as the opt-in simulation/testing mode.

## Config in one minute

```json
{ "run_id": "optional-id",
  "max_attempts": 3,
  "resume_capability": null,
  "execution_capabilities": [],
  "plan": {"works": [{"work_id": "a", "deps": []},
                      {"work_id": "b", "deps": [{"work_id": "a", "condition": "accepted"}]}]},
  "attempts": {"a": [{"outcome": "completed",
                       "candidate": {"any": "portable json"},
                       "assurance": {"verdict": "accepted"}}],
               "b": [{"outcome": "failed"},
                      {"outcome": "completed", "candidate": {"v": 2}, "assurance": {"verdict": "accepted"}}]} }
```

Omit `plan` for a single work (`work-1`). Attempts are consumed in order; verdicts are `accepted | rejected | inconclusive`. Full schema: `src/orc_werk/cli/config.py` module docstring (CLI-owned, non-normative).

## Reading a run

- `status` — per-work terminal state, attempt count, current candidate fingerprint.
- `history` — the full seq-ordered fact/decision/effect record; this is where root causes live today: look at effect records' `dispatch_result.error` and decisions' `basis`.
- The raw `.jsonl` is portable JSON (one envelope per line, `schema_version` on each) — `jq`/plain `json.loads` work with no orc-werk imports.

## Known issues (live ledger)

Update this table when found; remove rows when the fix merges. "Workaround" is what to do while using the CLI live.

| Issue | Symptom | Workaround | Status |
|---|---|---|---|

No open rows as of `TASK-M1-003` (#16, #17, #18, #23 all closed by that task's PR).

## Evolution rules

- Any user or dogfood-checker finding lands here (with workaround) the same day it is found — an unrecorded rough edge is a defect (`DELIVERY-STANCE`).
- Rows link an issue or the in-flight fix PR; merged fixes delete their row.
- Deterministic regressions graduate into `tests/` or `dogfood/` scenarios; this ledger is for the humans in the loop, not the machines.
