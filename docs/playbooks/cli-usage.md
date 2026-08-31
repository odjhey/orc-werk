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

orc [--limit N] [--before RUN_ID]                               # live text index of ./.orc (issue #43)
orc config-schema                                               # full dispatch config reference
orc record <run-id> --work <work-id> --verdict <accepted|rejected> [recording options]
                                                                   # preferred validated recording sugar; see `orc record -h`
orc dispatch "<intent text>" --config cfg.json [--journal DIR] [--max-attempts N]
orc dispatch --run-id <id> [--journal DIR]                       # resume existing run
orc dispatch --run-id <id> --abandon-work <work_id> --abandon-reason "<why>" [--abandon-by "<who>"]
                                                                   # operator: abandon a stuck attempt (TASK-M3B-001)
orc status  <journal.jsonl | run-id | dir> [--journal DIR]
orc history <journal.jsonl | run-id | dir> [--journal DIR] [--limit N] [--since-seq SEQ] [--before-seq SEQ]
orc show    <journal.jsonl | run-id | dir> [work] [--journal DIR]                # the run narrative: asked/executed/produced/judged, per attempt (TASK-M3C-001)
orc refs    <journal.jsonl | run-id | dir> [--journal DIR]                       # resolvable references + resolve commands
orc refs    <journal.jsonl | run-id | dir> --resolve <N|kind[:substring]>        # execute one ref's resolve command inline (TASK-M3C-002)
orc refs    <journal.jsonl | run-id | dir> --resolve-all                         # execute every ref's resolve command inline, headered
orc onboard --path <adopting-repo-dir> [--force]                                 # scaffold an adopting repo (TASK-M3D-001)
orc onboard --print-agents-block                                                 # print the agents-onboarding block only, writes nothing
```

- Journals default to `./.orc/<run_id>/journal.jsonl` (gitignored — durable run artifacts never belong in version control; issue #55 H1 per-run directory layout — see "Journal layout" below). A bare run id passed to `status`/`history` resolves against the same default. **Journal dir precedence (issue #55 H2):** `--journal` flag > `ORC_JOURNAL_DIR` env var > `./.orc`.
- **Bare `orc` (no subcommand)** prints a live text index of the default journal dir instead of an argparse usage error (`orc --help` remains the unchanged command reference): run id, per-work state, attempts, and pending flags, one line per run, most-recently-active first, truncated to the last 30 with a definitive `... showing last N of M runs` hint (`orc report --index` renders the full, unpaginated set as HTML). `--before RUN_ID` selects the page older than that run in index order. An empty/missing journal dir prints a definitive `0 runs in <abs dir>` plus a dispatch affordance.
- Exit codes: `0` all work ACCEPTED · `1` any work BLOCKED (or other non-accepted terminal) · `2` usage/config error (canonical error JSON on stderr) · `3` run non-terminal, pending operator input (`TASK-M1-002`, `SCN-007`) — a work is resting at `EXECUTING`/`ASSURING` because its current attempt's outcome has not been recorded yet; `dispatch`/`status` output names which work(s) and what they're awaiting (`execution-outcome` or `assurance-verdict`), followed by a `next:` block naming the exact runnable next command(s) (issue #43 — see "Design principles" below).
- **`history` is paginated**: last 30 records by default (`--limit 0` for all; `--since-seq SEQ` filters in the newer direction and `--before-seq SEQ` selects the page in the older direction), with a definitive `... showing last N of M` hint whenever the output was truncated — never an ambiguous "...more".
- Re-running `dispatch` over an existing journal is a safe no-op resume (idempotent by effect key); it is also the crash-recovery mechanism. The blessed concise form is `orc dispatch --run-id <id>` (plus `--journal DIR` when non-default); the original positional-intent form remains supported.
- **Agents recording their own observations (M1a+ push mode):** see `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) for ship-agent/verification-agent protocol, role separation, and the independent-derivation rule — this document remains the reference for commands, config shape, and the exit-code contract.
- **Pending/incremental mode is the default (M1a).** A config whose `attempts` entry for a work's next attempt is missing or absent entirely is not an error: `dispatch` starts that attempt, journals `FACT-EXEC-STARTED`, and stops cleanly at exit `3` with nothing fabricated for the missing settlement. Record the real outcome (and, once known, the assurance verdict) into the config's `attempts` entry for that work and re-run the identical `dispatch` command — it resumes via ordinary idempotent replay, no separate "resume" command. Fully scripted configs (every outcome supplied up front, as in the Config section below) remain supported unchanged as the opt-in simulation/testing mode.
- **Repo-default config profile (`TASK-M4A-001`).** Put a plain JSON dispatch-config object at `<resolved-journal-dir>/profile.json` (normally `<repo>/.orc/profile.json`). Discovery is exact: resolve the journal directory using `--journal` > `ORC_JOURNAL_DIR` > `./.orc`, then append `profile.json`; the CLI does not search cwd or ancestors. Effective precedence is `--config` (deep-merged over lower layers) > the run's persisted `config.json` > `.orc/profile.json` > `{}`. Nested objects compose, so an explicit `execution.model` override retains profile-provided `execution.cwd`, `assurance`, and `mirror` defaults. `--max-attempts` still overrides the merged config's `max_attempts`. `orc onboard` writes an empty `{}` starter under its never-clobber/`--force` discipline.
- **Config persistence / resume.** On a run's first `dispatch`, the effective config is durably copied into that run's own directory, `<journal-dir>/<run_id>/config.json`. Resume with `orc dispatch --run-id <id>` (and `--journal DIR` when needed): both positional `intent` and `--config` are optional when that id names an existing run with a journaled intent, and the config resolves from the run dir. The existing `orc dispatch "<intent>" --run-id <id>` form remains valid; its fresh intent text is ignored by replay. An explicit `--config` on a later dispatch still wins and refreshes the persisted copy. To prevent accidental stray runs, a new dispatch whose intent text exactly matches an existing run id is rejected with `ERR-VALIDATION`; use `--run-id <id>` to resume or reword genuinely new work. `next:` re-dispatch affordances name the durable in-run-dir config path once it exists, never the caller's ephemeral path.
- **Onboarding an adopting repo (`TASK-M3D-001`).** `orc onboard [--path DIR]` mechanizes the adopting-repo scaffold `PRODUCT-ADOPTION` used to describe as hand-work: a `.orc/` `.gitignore` entry, the orc-ledger skill installed and resolvable under `.claude/skills` (content sourced from THIS installed package -- one canonical origin), a copy-pasteable `## Delivery ledger (orc)` block written into `AGENTS.md` (or printed only, via `--print-agents-block`, writing nothing), and an honest install-verification report (`orc` on `$PATH` vs. module form, journal dir resolution, optional `bd` presence). Idempotent re-run; an operator-modified target is skip-with-note unless `--force`. See `docs/cli/README.md`'s `orc onboard` reference for the full flag/output detail.
- **Operator cancel (`SCN-011`).** `orc cancel <run-id> --work <work-id> --reason "<why>" [--journal <dir>]` records operator-attributed `DEC-CANCEL` followed by `FACT-WORK-CANCELLED`, closing `READY`, `EXECUTING`, or `ASSURING` Work directly as terminal `CANCELLED`. This is journal-only (no port Effect), never fabricates an assurance verdict, and is rejected with `ERR-CONFLICT` from `ACCEPTED`, `BLOCKED`, or `CANCELLED`. `--work` and `--reason` are required; attribution defaults to `$USER`/`whoami`. This operator power is never part of the ship/verify agent path.
- **Operator abandon (`TASK-M3B-001`, issues #76/#95).** `--abandon-work <work_id> --abandon-reason "<why>" [--abandon-by "<who>"]` on `orc dispatch` records `DEC-ABANDON-ATTEMPT`/`FACT-ATTEMPT-ABANDONED` (`STATE-DELIVERY` item 9) for the named work, then continues the same dispatch pass — an ordinary retry or block follows immediately. Legal only when that work is currently resting at an unresolved candidate-observation conflict, at `EXECUTING` after a completed Execution settled with no bound Candidate, or at `ASSURING` with its current attempt still unsettled (exit `3`'s `pending, awaiting=assurance-verdict`) and the operator knows, out-of-band, it will never settle (issue #95's adapter-owned in-flight case) — anything else is rejected with `ERR-VALIDATION` and a `next` pointer at `orc status <run>`. `--abandon-by` defaults to `$USER`/`whoami`; a flag, not a config-entry, is the chosen recording surface for this operator-only power (see the PR body's design rationale) — it is never available to the ship/verify agent seats `docs/playbooks/agent-cli-usage.md` governs.

## Design principles

This CLI's help/output conventions follow the [axi 10 principles](https://github.com/kunchenguid/axi#the-10-principles) as an agent-native benchmark (`orc`'s users are agents in push mode, and the operator; `--help` must be self-sufficient for both). What this CLI **adopts**: content-first bare invocation (no args prints a live index, never a usage error — axi #8); per-subcommand help with copy-pasteable examples and stated defaults (axi #10); definitive empty states and truncation hints — exact counts, an escape hatch (`--limit 0`, or `report --index`) always one step away, never an ambiguous "...more" (axi #3, #5); structured canonical errors, idempotent mutations, and no interactive prompts, all stated once in the top-level epilog (axi #6); contextual next-step disclosure via the `next:` block below. What it **consciously skips**: the TOON output format (axi #1) — format churn not worth it at this scale; ambient-context integrations (axi #7) — out of scope for a reference CLI.

**The listing-surfaces convention.** Any stdout surface that can emit an unbounded number of rows provides the uniform `--limit N` control, defaults to the shared bounded window, and treats `--limit 0` as all rows. Truncation always reports definitive shown and total counts and names the same-surface `--limit 0` escape hatch first; a different medium such as `report --index` may be named only as a secondary pointer. Truncated listings print the next-page cursor command; paging is affordance-driven, never stateful. Exemptions are documented here rather than rediscovered. `refs` is currently exempt because each of its reference sources is bounded per run; revisit that exemption if any source can emit unboundedly many rows per run. `report --all` is also not a stdout listing: stdout is an artifact manifest of paths written, while `--match` is the volume control for generated reports.

**The affordance rule.** `dispatch`/`status` output ends with a `next:` block naming the exact runnable command(s) legal from the run's *current* state — fully parameterized with real absolute paths and run ids — derived from a single per-state mapping (`orc_werk.cli.affordances`) cited to the delivery state machine (`STATE-DELIVERY`, `docs/domain/state-machines/delivery.md`): the state machine IS the hypermedia map, and this CLI is a stateless client over durable journal state, so HATEOAS (hypermedia-as-the-engine-of-application-state) applies natively. A new transition in that state machine forces the affordance question — there is no hand-scattered `next:` string anywhere else in this CLI. Affordances state what the *run* needs (e.g. "record the assurance verdict"), never *who* may supply it — role separation (a different agent must record a verdict than recorded the settlement) stays playbook discipline, `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`), not a CLI-enforced rule. **The affordance rule extends to errors** (issue #94): errors are states too, so a canonical error without next-step guidance is a defect (the same `DELIVERY-STANCE` spirit as an unrecorded rough edge) — every canonical error this CLI emits carries an additive `next` field alongside `error`/`message`/`details`, a list of 1-3 runnable or navigational strings naming where to find what is missing or what to run to inspect the failure.

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

Omit `plan` for a single work (`work-1`). Attempts are consumed in order; verdicts are `accepted | rejected | inconclusive`. The same schema applies to `.orc/profile.json`; use it for repo defaults and a smaller `--config` overlay for per-run changes. Run `orc config-schema` for the full schema; it prints the `src/orc_werk/cli/config.py` module docstring verbatim (CLI-owned, non-normative), so the reference has exactly one source.

### Scripted assurance entry

An `attempts.<work_id>[n].assurance` entry accepts `verdict`, `states`, `evidence_refs`, `extensions`, and the optional `derived_identity` introduced by issue #180. `derived_identity` is a non-empty portable-JSON object containing only identity fields; an `extensions` key inside it or an empty object is `ERR-VALIDATION`. At verdict-binding time the CLI compares every asserted key with the bound candidate's durable `subject_identity` from the run's `FX-IDENTIFY-CANDIDATE` effect record. Each key must exist there and its uninterpreted JSON value must be equal. Detection is bounded by the fields asserted: omitted fields are not corroborated, while supplying the complete identity gives full-payload corroboration. This is a pure comparison of config input with durable journal state—no adapter invocation or re-derivation.

A failed subset comparison returns `ERR-CONFLICT` and exit `2` before journaling any Fact; the canonical error's `next` affordances carry both identity payloads. The verdict does not bind, and the run remains pending at `ASSURING`: fix the entry and re-dispatch, or ask the operator to use `DEC-ABANDON-ATTEMPT` when the bound candidate is genuinely stale. A match records the verdict exactly as before, with no provenance echo. Omitting `derived_identity` preserves the prior behavior byte-for-byte. See `CONF-ASSURE-005` and `SCN-013`.

## Real execution: `acp`/`git` config (`TASK-M1-005` CLI wiring)

The config above uses the `scripted` adapters (both `execution`/`candidate` default to `"scripted"`) — deterministic test doubles, useful for CI and simulation. To have `orc dispatch` hand work to a real agent (Pi, over ACP) and fingerprint a real git worktree instead, add `execution`/`candidate` blocks:

```json
{ "execution": {"adapter": "acp", "cwd": "/abs/path/to/worktree", "agent": "pi",
                 "thought_level": "low", "model": null, "approve_all": false},
  "candidate": {"adapter": "git", "repo_path": "/abs/path/to/worktree"} }
```

- `execution.adapter: "acp"` selects `orc_werk.adapters.acp.execution.AcpExecution` (`docs/adapters/acp/mapping.md`) — keyed to exactly what that constructor accepts: `cwd` (REQUIRED — the worktree the agent runs in), `agent` (default `pi`), `thought_level` (default `low`), `approve_all` (default `false` — fail-closed; see the mapping doc's `--approve-all` footgun before ever setting `true`), and `model` (not a constructor parameter — this is the default injected into the per-call prompt request; see below). `execution_capabilities` (the existing top-level key) is reused to constrain `AcpExecution`'s advertised capability set — there is no separate `execution.capabilities` field.
- `candidate.adapter: "git"` selects `orc_werk.adapters.git.candidate.GitDiffCandidate` (`docs/adapters/git/mapping.md`) fingerprinting `repo_path` (REQUIRED)'s real `HEAD`/worktree diff instead of scripted content.
- **Constraint**: `execution.adapter == "acp"` REQUIRES `candidate.adapter == "git"` — rejected otherwise (a real execution's outcome cannot be matched to a config-scripted candidate).
- **Per-work `briefs` become prompts.** `orc_werk.app.Orchestrator` calls `ExecutionPort.start()` with the work id and an opaque, empty `execution_request`. A CLI-local wrapper fills in `execution_request["prompt"]` from the optional top-level `briefs` mapping (`{"briefs": {"work-a": "prompt for work a"}}`) before it reaches `AcpExecution`; a work with no briefs entry falls back to the run's own intent text (`orc dispatch "<fallback prompt>" ...`), preserving single-work behavior. The same briefs also feed Beads mirror issue descriptions when `mirror` is configured.
- **Attempts-merge semantics**: when `candidate.adapter == "git"`, `attempts[work_id]` entries carry no `outcome`/`candidate` — a real port supplies those. When `execution.adapter` is also `"acp"`, an entry may carry **only** `assurance` (the operator/verification agent still records the verdict through the same channel; nothing else is config-scriptable). The candidate's real fingerprint is never authored by hand — it comes from the run's own journal (`orc status`/`orc history` print it as `candidate_fingerprint=fp-...` once observed) and `orc dispatch` matches your recorded verdict to it automatically. The assurance entry may additionally carry issue #180's `derived_identity`, independently authored from the verifier's artifact inspection, to corroborate selected durable `subject_identity` fields before that automatic binding (`CONF-ASSURE-005`, `SCN-013`).

### Real-execution walkthrough

```bash
orc dispatch "reply with the word ping" --config acp-cfg.json --journal ./.orc
# exit 3: work-1 pending=true awaiting=execution-outcome -- Pi is working, nothing to do yet.

orc dispatch "reply with the word ping" --config acp-cfg.json --journal ./.orc   # re-run, identical command
# once Pi's turn settles: exit 3 again, now awaiting=assurance-verdict, and
# candidate_fingerprint=fp-<real hash> is printed -- a real candidate was
# identified and journaled with execution-session/v1 provenance.

# a (different) verification agent preferably records the verdict through the
# validated `orc record` sugar (use the exact command printed by `next:` and
# `orc record -h` for the applicable identity/evidence options):
orc record <run-id> --work work-1 --verdict accepted --journal ./.orc

# Hand-editing remains legal: equivalently edit acp-cfg.json to add
#   "attempts": {"work-1": [{"assurance": {"verdict": "accepted"}}]}
# then validate it with `orc validate`.

orc dispatch "reply with the word ping" --config acp-cfg.json --journal ./.orc   # re-run again
# exit 0: work-1 ACCEPTED.
```

`docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) governs the two-seat discipline (ship agent records the settlement; a *different* verification agent independently derives the candidate and records the verdict) — unchanged for real ports.

## Real assurance: `no-mistakes` config (`TASK-M2-001` CLI wiring)

To automate the verdict seat instead of an operator/verification agent
typing it, add an `assurance` block:

```json
{ "candidate": {"adapter": "git", "repo_path": "/abs/path/to/worktree"},
  "assurance": {"adapter": "no-mistakes", "repo_path": "/abs/path/to/worktree"} }
```

- `assurance.adapter: "no-mistakes"` selects `orc_werk.adapters.no_mistakes.
  assurance.NoMistakesAssurance` (`docs/adapters/no-mistakes/mapping.md`)
  — keyed to its one real constructor parameter, `repo_path` (REQUIRED).
  It is a **read-only judge**: it never lets `no-mistakes` fix findings or
  push, and never records anything itself if it isn't the exact CLI
  invocation's own honest observation.
- **Constraint**: `assurance.adapter == "no-mistakes"` REQUIRES
  `candidate.adapter == "git"` — rejected otherwise (a real verdict
  cannot be bound to a config-scripted candidate). `execution` may stay
  `"scripted"` (assurance only needs real git state to review, not a live
  agent driving it) or be `"acp"` — both combinations are supported.
- **The intent text becomes `--intent`.** Same composition pattern as
  execution's prompt above: a CLI-local wrapper fills in
  `requirements["intent"]` with the run's own intent text before it
  reaches `NoMistakesAssurance`.
- **Attempts-merge semantics**: when `assurance.adapter == "no-mistakes"`,
  `attempts[work_id]` entries may NOT carry `assurance` at all — the
  verdict is automatic; nothing to record by hand.
- **No operator/verification-agent verdict step at all.** Once the
  candidate is observed, `orc dispatch` keeps resting at exit `3`
  (`awaiting=assurance-verdict`) purely by re-polling — no config edit is
  needed between re-dispatches, since a real `no-mistakes` pipeline
  settles entirely on its own (or, for a parked review gate, this adapter
  renders its own verdict from the parked findings without waiting for a
  human at all — see the mapping doc's "Judge-only ruling").

## Generic command assurance config (issue #194)

An adopter may instead make an operator-authored, PR-reviewed in-repository
script the verify seat:

```json
{ "candidate": {"adapter": "git", "repo_path": "/abs/repo"},
  "assurance": {"adapter": "command", "script": "scripts/assure-candidate.sh",
                "cwd": "/abs/repo", "timeout_s": 300} }
```

`script` and `cwd` are required; `timeout_s` is positive and defaults to 300.
No args, environment, or inline-script-text keys exist. Relative scripts resolve
against `cwd`, and the resolved path must remain inside it. The script receives
`command-assurance-input/v1` JSON only on standard input. Clean exit 0 means
`accepted`, clean exit 1 means `rejected`, and every other exit, signal, or
timeout means `inconclusive`. Stdout is optional, bounded enrichment only; it
cannot override verdict, state, or fingerprint. As for no-mistakes, command
assurance requires a git candidate and forbids per-attempt scripted assurance
entries. See `ADAPTER-COMMAND-MAPPING`.

## Reading a run

- `status` — per-work terminal state, attempt count, current candidate fingerprint.
- `history` — the full seq-ordered fact/decision/effect record; this is where root causes live today: look at effect records' `dispatch_result.error` and decisions' `basis`.
- `show <run> [work] [--journal DIR]` (`TASK-M3C-001`) — the terminal narrative view, level two/three of the operator's four-question review staircase (`M3-HARDEN-THE-LOOP` Phase M3c): per work, per attempt, what was asked (derived prompt provenance — `briefs.<work>` vs the run's intent fallback, never guessed, the issue #111 "briefs footgun" lesson), who executed it (provider, session refs, duration from the times sidecar), what was produced (candidate identity), what was judged (verdict, a `review-findings/v1` summary, or a verdict-inheritance basis note per `STATE-DELIVERY` item 8), and where the full content lives (this attempt's own resolve commands, reusing `orc refs`'s row builders). Pure composition of the journal, this run's persisted dispatch config, and the times sidecar — no new recording. See `docs/cli/README.md` for the full command reference and a sample transcript.
- `refs <run> [--journal DIR]` — every resolvable reference the run carries (execution-session/v1 session/resume/transcript refs, assurance `evidence_refs`, candidate identity, the Beads mirror when configured), each with a runnable resolve command -- a pure read-side projection, never a new recording (`CONTRACT-DURABILITY`'s reference-first disposition). A run with none prints a definitive `0 refs for <run>` plus a pointer at `orc status`.
- `report <run-id> [--journal DIR] [--out PATH]` — a self-contained HTML run report (`TASK-M1-008`); by default it lands inside the run's own directory (`<journal-dir>/<run_id>/report.html`, issue #55 H1) for a run on the new layout, or beside the flat journal (`<journal-dir>/<run_id>.report.html`) for a run still on the legacy layout. `report --index` — a small local index page over a journal directory's runs; `report --all [--match GLOB] [--journal DIR] [--out-dir DIR]` — render every run whose `run_id` `fnmatch`es `GLOB` (default `'*'`) to its own file plus a scoped index (issue #40) — `--all`'s per-run output files are always flat under `--out-dir` (or the journal dir), regardless of any individual run's own layout, since `--all`'s whole point is gathering many runs into one place with one shared index. Every path this CLI prints (`journal:`, `report:`, and index-listing lines) is the resolved absolute path, so it's clickable in a terminal regardless of cwd — and, when stdout is a TTY, wrapped in an OSC 8 hyperlink escape sequence (`file://` target, the same plain path as the visible text) so terminals that support it make the path directly clickable (issue #55). When stdout is not a TTY (a pipe, a redirect, or — the common case — an agent capturing this CLI's output programmatically), the plain path prints byte-identical to before, with zero escape bytes: agent-facing output never carries terminal escape sequences.
- The raw journal is portable JSON (one envelope per line, `schema_version` on each) — `jq`/plain `json.loads` work with no orc-werk imports. See "Journal layout" below for exactly where each run's journal, sidecars, and persisted config live on disk.

### Journal layout (issue #55 H1)

Every run created under this code writes the **new per-run directory layout**: `<journal-dir>/<run_id>/` holding `journal.jsonl` (the canonical `JournalPort` file), `times.jsonl` (observed-at sidecar, `CONTRACT-DURABILITY`), `report.html` (this run's default `orc report` output), and `config.json` (the persisted effective dispatch config, issue #55 H2 — see the Config-persistence bullet above). Run lifecycle is directory lifecycle for this layout: a run "exists" once its directory does. (A pre-removal run directory may also still hold a legacy `reports.jsonl` `crew-report/v1` sidecar, `EXT-CREW-REPORT-V1`, superseded, issue #100 part 2 — inert; `orc` no longer reads or writes it.)

A **legacy flat `.orc` directory from before issue #55 keeps working unmodified** — every read path (bare `orc` index, `status`/`history` by bare run id, `report`/`report --index`/`--all`/`--match`, sidecar discovery) accepts both layouts. Writes never migrate a run: once a run has a legacy `<run_id>.jsonl` file, its journal keeps being read from and appended to that exact flat path for the rest of its life — a run's journal never splits across both layouts mid-run. This is decided independently per artifact (journal, times sidecar), each checking only its own legacy filename's existence.

### Run-id namespace convention

`delivery_run_id` becomes a filename/directory-name component, so it is restricted to a safe charset with no path separators (`/` is filename-unsafe and would try to create subdirectories). To organize related runs into groups a glob can select — e.g. all of one milestone's runs — use a **dot-separated namespace prefix** instead of a path: `m1.task-005`, `m1.task-006`, `m2.task-001`. `report --all --match 'm1.*'` then renders exactly that namespace's runs plus a scoped index, without touching runs outside it. This is a CLI/operator convention, not a canonical constraint — any safe run id works — but adopting it consistently is what makes `--match` useful as a grouping tool.

The `+` character remains reserved for **legacy flat-layout** sidecar files (`<run_id>+reports.jsonl`, `<run_id>+times.jsonl`) and can never appear in a run id — it is outside the safe run-id charset (`[A-Za-z0-9_.-]`) — so **any** safe run id works with namespaces: even ids like `m1.times` or `foo.reports` can never be mistaken for a sidecar. Structurally, a legacy-layout run journal is any `*.jsonl` directly under the journal dir whose stem contains no `+`; legacy sidecars are exactly the `+`-suffixed files (the attempt-2 watchtower ruling on PR #46). Inside a **new-layout** run directory this separator rule is moot — every artifact there is disambiguated by directory scope plus a fixed filename (`journal.jsonl`, `times.jsonl`, `reports.jsonl`), not a run-id-derived suffix, so the `+` ruling has nothing left to guard against in that layout; it stays documented here only because legacy directories remain fully supported.

## Known issues (live ledger)

Update this table when found; remove rows when the fix merges. "Workaround" is what to do while using the CLI live.

| Issue | Symptom | Workaround | Status |
|---|---|---|---|
| `no-mistakes` TOON output and step names have no schema/version guard | `assurance.adapter: "no-mistakes"` (`TASK-M2-001`, `NoMistakesAssurance`) parses `axi status` TOON with a small, purpose-built tolerant parser (`orc_werk.adapters.no_mistakes.toon.parse_toon`), reverse-engineered from one CLI version's observed output, and pins the mechanical never-push guarantee to the `push` step name (`--skip push` on every `axi run` spawn). A future `no-mistakes` release that renames/reshapes fields (e.g. `run.status`, the `gate.findings` table columns) would silently parse incorrectly (missing fields read as absent), and one that renames the `push` step would silently regress never-push — neither fails loudly. | Re-probe `axi status`/`axi run` output shape AND `axi logs --help`'s step list against the installed `no-mistakes` version before upgrading it in an environment that uses this adapter; re-run `tests/conformance/test_no_mistakes_assurance_unit.py` (including `ParseToonTest` and `test_every_spawn_passes_skip_push_mechanical_never_push`) and the CONF-ASSURE suite. | Open (recorded at `TASK-M2-001` implementation time; no version pin/guard exists yet — see `docs/adapters/no-mistakes/mapping.md` "TOON parsing"/"Judge-only ruling"/"Limitations"). |
| `orc refs --resolve`'s read-only allowlist is a per-tool argv+flag policy against provider CLI shapes observed at pinned versions | `orc_werk.cli.refs._vet_read_only` (`TASK-M3C-002`) vets every resolve command's argv in TWO layers, both required: (1) a tool+subcommand allowlist (`cat`; `git [-C <path>] show`; `acpx <agent> sessions <history\|show>`; `bd [--json] [-C <path>] <list\|show>`; `no-mistakes axi <status\|logs>` — nothing else), and (2) a **per-tool FLAG policy** (`_vet_flags`) over every token AFTER the subcommand, because vetting the subcommand alone was an arbitrary-file-WRITE hole — `git show --output=<path>` is a documented git write primitive that passed layer 1 (its subcommand is `show`). Layer 2's `_GIT_SHOW_BOOL_FLAGS`/`_BD_*`/`_NOMISTAKES_*`/`_ACPX_*` sets are curated read/render-only options observed against one version each; bd's minimal surface was empirically audited against bd 1.2.2 and permits only the builder-required `--json`/`--label`/`--status` plus read-only `--no-pager`, while `-w`/`--watch` (indefinite execution), `--format` (output-template control), `--db` (arbitrary database-path redirection), `--actor` (audit mutation), and `--global`/`--dolt-auto-commit`/`--ignore-schema-skew` (global database, write/commit, or skew controls) are deliberately EXCLUDED; git's write/exec options (`--output`/`-o`/`-O`, `--ext-diff`, `--textconv`) are likewise deliberately EXCLUDED and thus refused, unknown flags are refused (fail-closed), a value-flag's value is consumed unparsed, and journal-derived interpolated tokens (candidate `head_sha`/`repo_path`, `acpx` agent/session ref) that begin with `-` are refused at BUILD time too (they cannot be minted into a flag position). `git show`'s `<sha>` can't be `--`-guarded — `git show --stat -- <sha>` reads the sha as a pathspec, empirically verified — so that positional relies on the build-time `-`-lead rejection plus the flag policy, not positional separation. Residual fragility: a provider CLI upgrade that adds a NEW writer/exec flag not in the excluded set, renames a subcommand, or reshapes an invocation form would either wrongly REFUSE a legit read-only command (safe: degrades to the manual command, never executes) or — only if a brand-new **writer** flag were introduced with a shape the curated allowlist happened to accept — could regress the containment; bd has no provider-version pin/guard, so an upgrade past the audited 1.2.2 surface still requires a fresh audit. | Re-probe each vetted tool's read-only flag surface against the installed version before relying on `--resolve`/`--resolve-all` in an environment that upgrades `git`/`acpx`/`bd`/`no-mistakes` — especially audit `git help show`/`git help diff` for any newly-added writer/exec option and add it to the exclusion intent (keep the allowlist a curated read-only set); re-run `tests/scenarios/test_cli_refs.py`'s `VetReadOnlyUnitTest`, `VetFlagDepthUnitTest`, `BuilderFlagInjectionGuardUnitTest`, and the `test_git_show_output_write_escape_*` regression tests before trusting execution again. | Open (recorded at `TASK-M3C-002`; bd 1.2.2 audited, but no provider-version pin/guard exists yet, matching the `no-mistakes` row above). |

Prior rows closed as of `TASK-M1-003` (#16, #17, #18, #23, that task's PR). Issue #52 (`JournalPort.load_projection` replaying against the reducer's default `max_attempts` instead of the run's own recorded budget, breaking `status`/`report`/`report --index`/`--all` on a non-default-budget or `BLOCKED` run) closed by recording the effective budget in `FX-CREATE-WORK`'s effect data (`CONTRACT-DURABILITY`, `PORT-JOURNAL-005`, `SCN-008`) — see that fix's PR. Issue #78 (one run's replay `CoreError` aborting the entire `report --index`/`--all` portfolio) is closed: portfolio reports now render a critical placeholder with a `status` affordance and continue healthy runs.

## Evolution rules

- Any user or dogfood-checker finding lands here (with workaround) the same day it is found — an unrecorded rough edge is a defect (`DELIVERY-STANCE`).
- Rows link an issue or the in-flight fix PR; merged fixes delete their row.
- Deterministic regressions graduate into `tests/` or `dogfood/` scenarios; this ledger is for the humans in the loop, not the machines.
