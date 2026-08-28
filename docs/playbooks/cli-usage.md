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
- **Agents recording their own observations (M1a+ push mode):** see `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) for ship-agent/verification-agent protocol, role separation, and the independent-derivation rule — this document remains the reference for commands, config shape, and the exit-code contract.
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
- `report <run-id> [--journal DIR] [--out PATH]` — a self-contained HTML run report (`TASK-M1-008`); `report --index` — a small local index page over a journal directory's runs; `report --all [--match GLOB] [--journal DIR] [--out-dir DIR]` — render every run whose `run_id` `fnmatch`es `GLOB` (default `'*'`) to its own file plus a scoped index (issue #40). Every path this CLI prints (`journal:`, `report:`) is the resolved absolute path, so it's clickable in a terminal regardless of cwd.
- The raw `.jsonl` is portable JSON (one envelope per line, `schema_version` on each) — `jq`/plain `json.loads` work with no orc-werk imports. A run may also have `<run_id>+reports.jsonl` (crew reports, `EXT-CREW-REPORT-V1`) and `<run_id>+times.jsonl` (observed-at times, `CONTRACT-DURABILITY`) beside it — both are adapter-owned sidecars, never part of the canonical journal.

### Run-id namespace convention

`delivery_run_id` becomes a filename component (`<run_id>.jsonl`), so it is restricted to a safe charset with no path separators (`/` is filename-unsafe and would try to create subdirectories). To organize related runs into groups a glob can select — e.g. all of one milestone's runs — use a **dot-separated namespace prefix** instead of a path: `m1.task-005`, `m1.task-006`, `m2.task-001`. `report --all --match 'm1.*'` then renders exactly that namespace's runs plus a scoped index, without touching runs outside it. This is a CLI/operator convention, not a canonical constraint — any safe run id works — but adopting it consistently is what makes `--match` useful as a grouping tool.

The `+` character is reserved for adapter sidecar files (`<run_id>+reports.jsonl`, `<run_id>+times.jsonl`) and can never appear in a run id — it is outside the safe run-id charset (`[A-Za-z0-9_.-]`) — so **any** safe run id works with namespaces: even ids like `m1.times` or `foo.reports` can never be mistaken for a sidecar. Structurally, a run journal is any `*.jsonl` whose stem contains no `+`; sidecars are exactly the `+`-suffixed files (the attempt-2 watchtower ruling on PR #46).

## Known issues (live ledger)

Update this table when found; remove rows when the fix merges. "Workaround" is what to do while using the CLI live.

| Issue | Symptom | Workaround | Status |
|---|---|---|---|

No open rows as of `TASK-M1-003` (#16, #17, #18, #23 all closed by that task's PR).

## Evolution rules

- Any user or dogfood-checker finding lands here (with workaround) the same day it is found — an unrecorded rough edge is a defect (`DELIVERY-STANCE`).
- Rows link an issue or the in-flight fix PR; merged fixes delete their row.
- Deterministic regressions graduate into `tests/` or `dogfood/` scenarios; this ledger is for the humans in the loop, not the machines.
