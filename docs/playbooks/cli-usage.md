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

orc                                                             # live text index of ./.orc (issue #43)
orc dispatch "<intent text>" --config cfg.json [--journal DIR] [--max-attempts N]
orc status  <journal.jsonl | run-id | dir>
orc history <journal.jsonl | run-id | dir> [--limit N] [--since-seq SEQ]
```

- Journals default to `./.orc/<run_id>.jsonl` (gitignored — durable run artifacts never belong in version control). A bare run id passed to `status`/`history` resolves against `./.orc`.
- **Bare `orc` (no arguments)** prints a live text index of the default journal dir instead of an argparse usage error (`orc --help` remains the unchanged command reference): run id, per-work state, attempts, and pending flags, one line per run, most-recently-active first, truncated to the last 30 with a definitive `... showing last N of M runs` hint (`orc report --index` renders the full, unpaginated set as HTML). An empty/missing journal dir prints a definitive `0 runs in <abs dir>` plus a dispatch affordance.
- Exit codes: `0` all work ACCEPTED · `1` any work BLOCKED (or other non-accepted terminal) · `2` usage/config error (canonical error JSON on stderr) · `3` run non-terminal, pending operator input (`TASK-M1-002`, `SCN-007`) — a work is resting at `EXECUTING`/`ASSURING` because its current attempt's outcome has not been recorded yet; `dispatch`/`status` output names which work(s) and what they're awaiting (`execution-outcome` or `assurance-verdict`), followed by a `next:` block naming the exact runnable next command(s) (issue #43 — see "Design principles" below).
- **`history`/`crew-report list` are paginated**: last 30 records/reports by default (`--limit 0` for all; `history` also takes `--since-seq SEQ`), with a definitive `... showing last N of M` hint whenever the output was truncated — never an ambiguous "...more".
- Re-running the same `dispatch` over an existing journal is a safe no-op resume (idempotent by effect key); it is also the crash-recovery mechanism — just run the same command again.
- **Agents recording their own observations (M1a+ push mode):** see `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) for ship-agent/verification-agent protocol, role separation, and the independent-derivation rule — this document remains the reference for commands, config shape, and the exit-code contract.
- **Pending/incremental mode is the default (M1a).** A config whose `attempts` entry for a work's next attempt is missing or absent entirely is not an error: `dispatch` starts that attempt, journals `FACT-EXEC-STARTED`, and stops cleanly at exit `3` with nothing fabricated for the missing settlement. Record the real outcome (and, once known, the assurance verdict) into the config's `attempts` entry for that work and re-run the identical `dispatch` command — it resumes via ordinary idempotent replay, no separate "resume" command. Fully scripted configs (every outcome supplied up front, as in the Config section below) remain supported unchanged as the opt-in simulation/testing mode.

## Design principles

This CLI's help/output conventions follow the [axi 10 principles](https://github.com/kunchenguid/axi#the-10-principles) as an agent-native benchmark (`orc`'s users are agents in push mode, and the operator; `--help` must be self-sufficient for both). What this CLI **adopts**: content-first bare invocation (no args prints a live index, never a usage error — axi #8); per-subcommand help with copy-pasteable examples and stated defaults (axi #10); definitive empty states and truncation hints — exact counts, an escape hatch (`--limit 0`, or `report --index`) always one step away, never an ambiguous "...more" (axi #3, #5); structured canonical errors, idempotent mutations, and no interactive prompts, all stated once in the top-level epilog (axi #6); contextual next-step disclosure via the `next:` block below. What it **consciously skips**: the TOON output format (axi #1) — format churn not worth it at this scale; ambient-context integrations (axi #7) — out of scope for a reference CLI.

**The affordance rule.** `dispatch`/`status` output ends with a `next:` block naming the exact runnable command(s) legal from the run's *current* state — fully parameterized with real absolute paths and run ids — derived from a single per-state mapping (`orc_werk.cli.affordances`) cited to the delivery state machine (`STATE-DELIVERY`, `docs/domain/state-machines/delivery.md`): the state machine IS the hypermedia map, and this CLI is a stateless client over durable journal state, so HATEOAS (hypermedia-as-the-engine-of-application-state) applies natively. A new transition in that state machine forces the affordance question — there is no hand-scattered `next:` string anywhere else in this CLI. Affordances state what the *run* needs (e.g. "record the assurance verdict"), never *who* may supply it — role separation (a different agent must record a verdict than recorded the settlement) stays playbook discipline, `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`), not a CLI-enforced rule.

**No CLI framework, by design.** `orc` is built on stdlib `argparse` alone — no third-party CLI framework. This preserves the adoption ladder's rung-1 promise (`PRODUCT-ADOPTION`: the simulator/spec-executor rung needs "Python 3.11+ and this repo — nothing else"), keeping the CLI itself install-free rather than adding a dependency the lowest rung would otherwise have to pull in. Revisit triggers, if any, are recorded in issue #43's thread.

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
| Found dogfooding issue #43's bare-`orc` index | `JournalPort.load_projection` (`JSONLJournal`) does not accept/forward a per-run `max_attempts`, so `reduce()` always replays against its own default. A run `dispatch`ed with a non-default `max_attempts` whose budget-exhaustion transition depends on that value (e.g. `attempt_number` sits between the run's actual budget and the reducer default) can fail a *fresh* replay — `orc status <run>`, `orc report <run>`, `report --index`/`--all`, and the bare-`orc` index — with a canonical `ERR-CONFLICT` ("`FACT-WORK-BLOCKED` illegal from state 'READY'"), even though the live `dispatch` that produced the journal completed and printed the correct terminal state (the in-process orchestrator's own projection, not a `load_projection` replay, is what `dispatch` prints). | None known short of avoiding non-default `max_attempts` for runs you'll later `status`/`report`. The bare-`orc` index (issue #43) degrades this per-run to `<run_id>: (unreadable: ERR-CONFLICT -- see orc status <run_id>)` rather than failing the whole listing; `status`/`report`/`history` on the affected run still exit `2`. | Open — root cause is `core`/`PORT-JOURNAL` (`JournalPort.load_projection`'s signature and `reduce()`'s default), out of scope for a CLI-only task; needs its own task card. |

Prior rows closed as of `TASK-M1-003` (#16, #17, #18, #23, that task's PR).

## Evolution rules

- Any user or dogfood-checker finding lands here (with workaround) the same day it is found — an unrecorded rough edge is a defect (`DELIVERY-STANCE`).
- Rows link an issue or the in-flight fix PR; merged fixes delete their row.
- Deterministic regressions graduate into `tests/` or `dogfood/` scenarios; this ledger is for the humans in the loop, not the machines.
