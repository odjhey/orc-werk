---
id: CLI-REFERENCE
type: reference
status: current
authority: informative
description: Command-by-command reference for the orc CLI -- quickstart, per-command flags and examples, exit codes, config schema pointer, and journal file layout.
---

# CLI reference

This is the publishable, command-by-command reference for the `orc` CLI --
what a future docs webpage would be built from. The CLI is a reference
surface, not a contract: nothing here is normative on its own. Where a
behavior needs normative backing, this document cites the owning stable ID
instead of restating its prose (`docs/README.md`'s authoring rules).

This document does not replace the two playbooks it cross-links:

- `docs/playbooks/cli-usage.md` (`PLAYBOOK-CLI-USAGE`) -- the living
  operational guide, including the known-issues ledger consulted while
  dogfooding live, real `git`/command-assurance port wiring, and the full
  journal-layout discussion.
- `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) -- ship-agent /
  verification-agent seat discipline for recording settlements and verdicts.
- `.agents/skills/orc-ledger/SKILL.md` -- the fresh-session onboarding
  skill: orient via bare `orc`, resume-don't-duplicate, seat discipline,
  recording mechanics. `orc onboard` (below) installs this same content
  into an adopting repository.

## Quickstart

Install, or alias the module invocation from a checkout:

```bash
pip install -e .        # gives you a real `orc` command, or:
alias orc='PYTHONPATH=src python3 -m orc_werk.cli'   # from the repo root
```

`orc --help` is self-sufficient: it prints the exit-code contract and every
subcommand in its epilog. Every example below was run and captured against
this CLI (post-issue-#55 surface: per-run `.orc/<run>/` directories,
`--journal` > `ORC_JOURNAL_DIR` > `./.orc` precedence, config persisted into
the run directory, run-id-only re-dispatch, OSC-8 TTY-gated paths).

### First scripted dispatch

The `scripted` adapters (the default) are deterministic test doubles --
no real agent or git repo required, useful for learning the CLI or for CI.
Write a config that declares one work's single attempt outcome up front:

```bash
cat > cfg.json <<'EOF'
{
  "attempts": {
    "work-1": [
      {"outcome": "completed", "candidate": {"label": "hello"},
       "assurance": {"verdict": "accepted"}}
    ]
  }
}
EOF

orc dispatch "ship the widget" --config cfg.json --journal ./.orc --run-id demo-run-1
```

```text
run: demo-run-1
journal: /abs/path/.orc/demo-run-1/journal.jsonl
work work-1: state=ACCEPTED attempts=1 candidate_fingerprint=fp-30dd7c8c1f588de26f8f26c8
next:
  - work(s) accepted: work-1 -- see the full run report: orc report demo-run-1
```

Exit code `0`: every Work reached `ACCEPTED`.

### Reading the run

```bash
orc status demo-run-1                 # per-work terminal state, attempt count, candidate fingerprint
orc verdict demo-run-1                # latest assurance verdict, evidence, and findings per work
orc history demo-run-1                # the full seq-ordered fact/decision/effect record
orc report demo-run-1                 # self-contained HTML report at .orc/demo-run-1/report.html
```

A bare run id resolves against `$ORC_JOURNAL_DIR` or `./.orc`; pass an
explicit journal directory or file path instead when working outside the
default location.

## Commands

### `orc` (bare, no arguments)

Prints a live text index of the default journal directory -- run id,
a per-run state-count rollup with explicit blocked/pending flags, plus
per-work state, attempts, and pending detail, one line per run,
most-recently-active first (truncated to the last 30 with a definitive
`... showing last N of M runs` hint). An empty/missing journal dir prints a
definitive `0 runs in <abs dir>` plus a dispatch affordance. `orc --help`
remains the unchanged argparse usage/reference and is never replaced by the
index.

```bash
orc                          # ./.orc or $ORC_JOURNAL_DIR
ORC_JOURNAL_DIR=./.orc orc   # explicit
```

```text
2 runs in /abs/path/.orc:
demo-pending: states=EXECUTING:1 flags=pending | work-1=EXECUTING attempts=1 pending=execution-outcome
demo-run-1: states=ACCEPTED:1 | work-1=ACCEPTED attempts=1
orc status <run-id> for next-step guidance on one run; orc report --index for the full unpaginated HTML index over /abs/path/.orc.
```

### `orc version`

```text
usage: orc version [-h]
```

Prints the package version, the resolved directory from which `orc_werk` was imported, and the checkout's short git commit when that source is inside a git worktree. A modified worktree adds `+dirty`; a package install without git metadata reports `git: not a checkout` (and an unavailable git executable is reported honestly). The command is read-only, creates no journal, and exits `0`.

```bash
orc version
```

```text
orc 0.1.0 (source /abs/path/src/orc_werk, git 2168b1a+dirty)
```

### `orc config-schema`

```text
usage: orc config-schema [-h]
```

Prints the canonical dispatch config reference to stdout and exits `0`.
The output is the `src/orc_werk/cli/config.py` module docstring verbatim,
not a second copy of the schema.

```bash
orc config-schema
```

### `orc validate`

```text
usage: orc validate [-h] [--journal JOURNAL] [--no-profile] config
```

Composes one portable JSON dispatch config over the repo profile and applies
the same deep-merge precedence and schema validator as `dispatch`. The journal
directory, used only to locate `profile.json`, resolves via `--journal` >
`ORC_JOURNAL_DIR` > `./.orc`. Pass `--no-profile` to deliberately validate the
file alone. A valid config exits `0` and prints a would-ingest preview: the
contributing layers, plan work ids, selected execution/candidate/assurance
adapters, every attempt entry's keys, and any scripted assurance verdict and
extension ids. This is the read-only check to run after editing a per-run
config and before dispatching it.

```bash
orc validate ./.orc/demo-pending/config.json
orc validate run.json --journal ./.orc --no-profile  # standalone file check
```

```text
PASS: run.json
layers: profile: /abs/path/.orc/profile.json (candidate, execution) + config: run.json
plan works: work-1 (default)
adapters: execution=scripted candidate=git assurance=command
```

When no profile is present, validation is identical to standalone behavior
and the layer note names only the config. Invalid JSON or an unknown/malformed
composed config key exits `2` and prints canonical `ERR-VALIDATION` JSON,
including the offending config path. The command reads a profile when present
but never writes run state or creates the journal directory.

### `orc dispatch`

```text
usage: orc dispatch [-h] [--config CONFIG] [--journal JOURNAL]
                     [--max-attempts MAX_ATTEMPTS] [--run-id RUN_ID]
                     [--abandon-work WORK_ID] [--abandon-reason TEXT]
                     [--abandon-by WHO] [--wait] [--timeout SECONDS]
                     [--poll-interval SECONDS]
                     [intent]
```

Dispatch an intent and run the delivery state machine to a resting point
(terminal, or pending awaiting settlement observation or operator-recorded input).

| Flag | Default | Notes |
|---|---|---|
| `intent` (positional) | required for new runs | the intent text to submit; optional with `--run-id` naming an existing run whose journal holds its durable intent |
| `--config` | repo profile/persisted config, then empty scripted config | path to a portable JSON dispatch-config overlay; see "Config schema" below. Deep-merges over lower-precedence config |
| `--journal` | `$ORC_JOURNAL_DIR` or `./.orc` | journal directory |
| `--max-attempts` | policy default `3` | overrides the run's retry budget |
| `--run-id` | derived deterministically from the intent text | explicit `delivery_run_id` |
| `--wait` | off | block, re-dispatching internally, until the run's resting point moves or goes terminal (`SCN-017`, issue #210); see "`orc dispatch --wait`" below |
| `--timeout` | none (wait indefinitely) | with `--wait`: give up after this many seconds of an unchanged pending fingerprint and exit `4`; requires `--wait` |
| `--poll-interval` | `5.0` | with `--wait`: seconds slept between internal passes; never journaled |

```bash
orc dispatch "ship the widget" --config cfg.json
orc dispatch "ship the widget" --config cfg.json --journal ./.orc --max-attempts 3
```

**Pending/incremental mode is the default.** A config with no recorded
outcome for a work's next attempt is not an error: `dispatch` starts that
attempt and stops cleanly at exit `3`, nothing fabricated. Record the real
outcome (and later the verdict) into the config's `attempts` entry and
re-run the identical `dispatch` command -- this is also the crash-recovery
mechanism (`SCN-007`).

```bash
cat > pending-cfg.json <<'EOF'
{}
EOF
orc dispatch "pending demo" --config pending-cfg.json --journal ./.orc --run-id demo-pending
```

```text
run: demo-pending
journal: /abs/path/.orc/demo-pending/journal.jsonl
work work-1: state=EXECUTING attempts=1 candidate_fingerprint=- pending=true awaiting=execution-outcome attempt=1
pending: run is non-terminal, awaiting settlement observation or operator-recorded input for: work-1
next:
  - record the execution outcome for work(s): work-1
  - then re-run: orc dispatch 'pending demo' --config /abs/path/.orc/demo-pending/config.json --journal /abs/path/.orc --run-id demo-pending
```

### `orc dispatch --wait`

`SCN-017` (issue #210): instead of the caller re-invoking `dispatch` on a
timer to poll exit `3`, `--wait` internalizes that loop -- it re-dispatches
(config re-read included) until the run's **pending fingerprint** (the set
of `(work_id, attempt_number, awaiting)` tuples across pending works)
moves from its baseline, or the run goes terminal. Nothing is printed for
an internal pass that observes no movement; only the pass that ends the
wait prints its ordinary report, exactly as a non-`--wait` dispatch
observing that same resting state would. Continuing the pending-demo run
above with `--wait --timeout 60 --poll-interval 1` while a second
terminal records the execution settlement mid-wait:

```bash
orc dispatch --run-id demo-pending --journal ./.orc --wait --timeout 60 --poll-interval 1
# (concurrently, from another shell: edit .orc/demo-pending/config.json to add
#  "attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "hello"}}]})
```

```text
run: demo-pending
journal: /abs/path/.orc/demo-pending/journal.jsonl
work work-1: state=ASSURING attempts=1 candidate_fingerprint=fp-30dd7c8c1f588de26f8f26c8 pending=true awaiting=assurance-verdict attempt=1
pending: run is non-terminal, awaiting settlement observation or operator-recorded input for: work-1
next:
  - record the assurance verdict for work(s): work-1 -- needs a different agent than the one that recorded the settlement (canonical playbook discipline: PLAYBOOK-AGENT-CLI)
  - work work-1's bound assurance is assure-8058cef98e13ac0b (candidate head (unknown)); if it stays pending unexpectedly long, operator recovery is: orc dispatch --run-id demo-pending --journal /abs/path/.orc --config /abs/path/.orc/demo-pending/config.json --abandon-work work-1 --abandon-reason "<why>"
  - then re-run: orc dispatch 'pending demo' --config /abs/path/.orc/demo-pending/config.json --journal /abs/path/.orc --run-id demo-pending
```

Exit `3`: the resting point moved from `EXECUTING`/`execution-outcome` to
`ASSURING`/`assurance-verdict` -- the same distinct in-progress exit code a
non-`--wait` dispatch of this same journal state would report, just
reached without the caller re-invoking anything. A caller that only cares
about terminal states loops on `dispatch --wait`; a watchtower-style caller
instead interposes here (e.g. dispatching an independent verify seat)
because `--wait` returns at the *first* movement rather than running
through to terminal.

Re-running the same command with a short `--timeout` and nothing recorded
demonstrates the distinct wait-timeout exit:

```bash
orc dispatch --run-id demo-pending --journal ./.orc --wait --timeout 1 --poll-interval 0.2
```

```text
run: demo-pending
journal: /abs/path/.orc/demo-pending/journal.jsonl
work work-1: state=ASSURING attempts=1 candidate_fingerprint=fp-30dd7c8c1f588de26f8f26c8 pending=true awaiting=assurance-verdict attempt=1
pending: run is non-terminal, awaiting settlement observation or operator-recorded input for: work-1
next:
  - record the assurance verdict for work(s): work-1 -- needs a different agent than the one that recorded the settlement (canonical playbook discipline: PLAYBOOK-AGENT-CLI)
  - work work-1's bound assurance is assure-8058cef98e13ac0b (candidate head (unknown)); if it stays pending unexpectedly long, operator recovery is: orc dispatch --run-id demo-pending --journal /abs/path/.orc --config /abs/path/.orc/demo-pending/config.json --abandon-work work-1 --abandon-reason "<why>"
  - then re-run: orc dispatch 'pending demo' --config /abs/path/.orc/demo-pending/config.json --journal /abs/path/.orc --run-id demo-pending
wait timeout: --timeout 1.0s elapsed with the pending fingerprint unchanged (SCN-017 step 8) -- the run is exactly as pending as before; re-invoking (with or without --wait) is always safe
```

Exit `4`: the internal passes over that one second found no movement.
Nothing about the wait itself -- not the interval, not the timeout, not
how many internal passes ran -- is journaled (determinism hard bar,
`DELIVERY-STANCE`): re-running this identical journal state as N manual
re-dispatches instead of one `--wait` invocation produces a record-for-
record identical journal (`SCN-017` steps 2, 8, 13). `--timeout` without
`--wait` is `ERR-VALIDATION`, exit `2`; `--wait` without `--timeout` waits
indefinitely; combining `--wait` with `--abandon-work` is also
`ERR-VALIDATION` (`--abandon-work` is a one-shot operator verb, not a wait
semantic). Killing the waiting process (`SIGINT` or otherwise) loses
nothing -- every journaled fact was journaled by a completed ordinary pass
(`SCN-017` step 10).

**Transient config races during a wait (`SCN-017` amendment, issue #216)**:
because each internal pass re-reads the backing config, a concurrent
recorder (`orc record`, or a merge-only hand edit) is the expected wake
mechanism, not a conflict -- recorders should write atomically
(write-temp-then-`os.replace`, the same pattern `orc record`'s own writer
already uses) so a `--wait` pass never observes a torn write. As a safety
net beyond that, `--wait` tolerates up to 3 consecutive internal passes
whose config load/validate fails with unparseable JSON or `ERR-VALIDATION`:
each is skipped silently and retried at the next poll interval. A 4th
consecutive failure fails the wait with the ordinary canonical error, exit
`2` -- identical to what a non-`--wait` dispatch of the same bad config
would report. A failure on the wait's very first internal pass is never
tolerated and fails fast immediately, since a bad config at the moment
`--wait` is invoked is a real config error, not a race.

**Repo profile and precedence (`TASK-M4A-001`)**: the CLI discovers a profile only at `<resolved-journal-dir>/profile.json`--normally `<repo>/.orc/profile.json`. It first resolves the journal directory using `--journal` > `ORC_JOURNAL_DIR` > `./.orc`, then appends `profile.json`; it never searches cwd or ancestors. The profile is a plain JSON object with the same schema as `--config`. Effective precedence is `--config` (deep-merged) > per-run persisted `config.json` > profile > `{}`. Nested objects compose; non-object values replace. At every layer boundary, when a higher layer explicitly selects a different `execution.adapter`, `candidate.adapter`, `assurance.adapter`, or `mirror.adapter` than the composed lower layers, lower-layer keys in that section that are exclusive to the previously selected adapter are dropped (#174). Keys explicitly supplied by the higher layer remain and are validated against the new adapter, while inherited adapter-agnostic keys that are legal for the new adapter continue to compose. The adapter-conditional validator's exclusivity definitions are the single source of truth for which inherited keys are dropped. Selecting the same adapter does not drop any keys. The `--max-attempts` flag retains its existing precedence over the merged config's `max_attempts`.

**Config persistence and run-id-only resume**: on a run's first `dispatch`,
the effective config is durably copied into that run's own directory,
`<journal-dir>/<run_id>/config.json`. The blessed resume form omits both the
redundant positional intent and `--config`; the journal supplies the durable
intent and the run directory supplies the config:

```bash
orc dispatch --run-id demo-pending --journal ./.orc
```

The existing `orc dispatch "pending demo" --run-id demo-pending` form still
works, and replay continues to ignore its fresh intent text. A new dispatch
whose intent text exactly equals an existing run id is rejected with an
actionable `ERR-VALIDATION`: use `orc dispatch --run-id <id>` to resume, or
reword the intent if it is genuinely new work.

The concise resume command produces byte-identical output to the first invocation (still exit `3`,
still resolving the same persisted `config.json`). Editing that persisted
`config.json` to add the real outcome and re-running the same command
advances the run:

```bash
# edit /abs/path/.orc/demo-pending/config.json:
#   "attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "x"},
#                             "assurance": {"verdict": "accepted"}}]}
orc dispatch --run-id demo-pending --journal ./.orc
```

```text
run: demo-pending
journal: /abs/path/.orc/demo-pending/journal.jsonl
work work-1: state=ACCEPTED attempts=1 candidate_fingerprint=fp-a6fd5c0647f98d41b530afc5
next:
  - work(s) accepted: work-1 -- see the full run report: orc report demo-pending
```

Exit `0`. An explicit `--config` on a later dispatch still wins and
refreshes the persisted copy. `next:` re-dispatch affordances always name
the durable in-run-dir config path, never the caller's own ephemeral
`--config` path, once a persisted copy exists.

**Real `git` candidate identification with an external executor** (a real
agent or script driven outside `orc`'s observation, a real git worktree
fingerprinted as the candidate, its outcome pushed in via `orc record` or a
merge-only config edit per `ADR-0005`) is config-driven the same way --
see `docs/playbooks/cli-usage.md`'s "External executors record in
(ADR-0005)" and "Generic command assurance config" sections for the
`candidate`/`assurance` config blocks and the full walkthrough. Provider
vocabulary (git diff fingerprinting, command-assurance invocation) lives in
the adapters' own mapping docs: `docs/adapters/git/mapping.md`,
`docs/adapters/command/README.md`.

### Bare `orc` run index

```text
usage: orc [--limit LIMIT] [--before RUN_ID] [--state active]
```

The content-first invocation lists the most-recently-active runs in the
default journal directory. It shows 30 by default; `--limit N` bounds the
listing, `--limit 0` shows all runs, and `--before RUN_ID` selects runs
older than that cursor in index order. `--state active` includes runs with
blocked or other non-accepted work; omitting it lists every run. An invalid
state filter is canonical `ERR-VALIDATION`. A truncated listing names
`orc --limit 0` and prints an exact next-(older)-page command;
`orc report --index` is the secondary HTML view.
The journal directory resolves from `ORC_JOURNAL_DIR`, then `./.orc`.

```bash
orc
orc --limit 10
orc --limit 10 --before oldest-run-id-from-the-current-page
orc --limit 0
orc --state active
```

### `orc record`

```text
usage: orc record [-h] --work WORK_ID --verdict {accepted,rejected}
                  [--evidence-ref REF] [--finding TEXT]
                  [--derived-identity JSON] [--model M] [--session-ref S]
                  [--seat-ref S] [--journal DIR]
                  run-id
```

Records the current assurance verdict requested for one Work by merge-only,
atomic update of the run's persisted `config.json` (issue #192). It refuses an
unknown run/Work, a Work not currently awaiting `assurance-verdict`, or an
attempt that already carries `assurance`; it never dispatches or advances the
run. Repeated evidence and finding flags become `evidence_refs` and
`review-findings/v1`; model/session/seat flags become an
`executor-identity/v1` payload with `role: verify`; `--derived-identity` must
parse as a JSON object and is checked by the existing config/binding validation.
On success it prints proof of the recorded verdict and the exact
`orc dispatch --run-id ... --journal ...` command as its `next:` affordance.
Hand editing remains a legal equivalent recording path under
`PLAYBOOK-AGENT-CLI`; this command adds validation, not new journal semantics.

```bash
orc record demo-pending --work work-1 --verdict accepted \
  --evidence-ref audit.log --model pi --session-ref sess-1 --seat-ref verify-1
```

### `orc cancel`

```bash
orc cancel <run-id> --work <work-id> --reason "<why>" [--journal <dir>]
```

Operator-only terminal closure. The command records attributed `DEC-CANCEL`
and `FACT-WORK-CANCELLED` without a port Effect, then prints
`state=CANCELLED`. It is legal from `READY`, `EXECUTING`, or `ASSURING` and
conflicts from any terminal state. Both `--work` and `--reason` are required;
the operator identity defaults to `$USER`/`whoami`.

### `orc status`

```text
usage: orc status [-h] [--journal JOURNAL] target
```

Per-work state, attempt count, current candidate fingerprint,
pending/blocked detail, and next-step affordances for one run.

| Flag | Default | Notes |
|---|---|---|
| `target` (positional) | required | journal path (dir or `<run>.jsonl`) or bare run id |
| `--journal` | `$ORC_JOURNAL_DIR` or `./.orc` | journal directory |

For a bare run id, the journal directory resolves with `--journal` >
`ORC_JOURNAL_DIR` > `./.orc` precedence.

```bash
orc status my-run-id
orc status my-run-id --journal ./.orc
orc status ./.orc/my-run-id.jsonl
```

### `orc verdict`

```text
usage: orc verdict [-h] [--journal JOURNAL] target
```

Read-only shortcut for the latest `FACT-ASSURE-SETTLED` per Work. It prints
the verdict, bound candidate fingerprint, evidence references when present,
extension keys, and a compact `review-findings/v1` finding summary using the
same rendering as `orc show`. Work without a settled assurance prints
`(no verdict yet)`. The command only reads the journal and records nothing.

```bash
orc verdict my-run-id
orc verdict my-run-id --journal ./.orc
```

### `orc history`

```text
usage: orc history [-h] [--journal JOURNAL] [--limit LIMIT]
                   [--since-seq SINCE_SEQ] [--before-seq BEFORE_SEQ]
                   target
```

The full seq-ordered fact/decision/effect record -- root-cause detail
(dispatch-gate errors, decision basis) lives here.

| Flag | Default | Notes |
|---|---|---|
| `target` (positional) | required | journal path (dir or `<run>.jsonl`) or bare run id |
| `--journal` | `$ORC_JOURNAL_DIR` or `./.orc` | journal directory |
| `--limit` | `30` | most-recent records to show; `0` for all |
| `--since-seq` | none | only records with `seq` greater than the given value (newer-direction cursor) |
| `--before-seq` | none | select records older than the given sequence cursor |

For a bare run id, the journal directory resolves with `--journal` >
`ORC_JOURNAL_DIR` > `./.orc` precedence.

Paginated: a truncated result prints a definitive
`... showing last N of M` hint and an exact next-(older)-page command,
never an ambiguous "...more". Paging is stateless: copy and run that command.

```bash
orc history my-run-id
orc history my-run-id --journal ./.orc
orc history my-run-id --limit 0
orc history my-run-id --since-seq 12
orc history my-run-id --limit 30 --before-seq 16
```

Sample record line (`jq`-readable JSONL underneath -- see "Journal file
layout" below):

```text
[0007] decision DEC-DISPATCH   {"attempt_number":1,"attribution":{"policy":"v0-deterministic"},"basis":[...],"work_id":"work-1"}
```

### `orc show`

```text
usage: orc show [-h] [--journal JOURNAL] run [work]
```

The terminal narrative view (`TASK-M3C-001`): the operator's four-question
review staircase's levels two ("this run in depth") and three ("briefs and
hand-offs per turn") -- bare `orc` is level one, `orc refs --resolve`
(`TASK-M3C-002`, adapter-native content) is level four. Pure composition of
the journal, this run's persisted dispatch config, and the observed-at
times sidecar -- no new recording, no full-payload dumps. For each work (or
just the one named), per attempt:

- **ASKED** -- the derived prompt provenance: `prompt = briefs.<work>
  (persisted config)` when the run's persisted config has a `briefs`
  entry for that work (the issue #82/#83 precedence rule -- a brief,
  however short, always wins over the intent, the issue #111 "briefs
  footgun" lesson), or `prompt = run intent (fallback)` otherwise; a
  truncated preview of the actual text (`--limit`-style definitive count,
  never dumped in full) with a pointer at where the full text lives (the
  persisted config path for a brief, `orc status <run>` for the intent).
  Since 0.5.0, `execution.adapter` is always `"scripted"` (`ADR-0005`
  removed the `acp` `ExecutionPort` adapter, the only real-executor
  option), so no prompt is ever sent -- rendered honestly as `scripted
  execution -- no prompt sent to the executor`, never guessed.
- **EXECUTED** -- provider, `execution_id`, session/resume refs when the
  attempt carries `execution-session/v1` provenance, duration (the times
  sidecar's started->settled delta -- absent when the sidecar has no
  entry, never fabricated), and outcome.
- **PRODUCED** -- candidate id, fingerprint, and subject identity fields
  (`head_sha`/`pr`/`repo_path`) as present.
- **JUDGED** -- assurance id, verdict, `evidence_refs`, and a
  `review-findings/v1` summary (count, plus id/severity/one-line summary
  per finding, capped at 5 with a definitive count and an `orc history
  <run> --limit 0` pointer for the rest -- never a full payload dump).
  When an attempt re-observes a candidate whose fingerprint already has a
  settled verdict in this work's lineage, no fresh assurance was ever
  requested (`STATE-DELIVERY` item 8, verdict inheritance, the issue
  #76/#115 story) -- rendered as `verdict inherited from attempt N's
  settlement`, citing the inherited findings too, never presented as a
  fresh judgment. An abandoned attempt (`DEC-ABANDON-ATTEMPT`,
  `TASK-M3B-001`) renders who/why instead.
- **NEXT/DEEPER** -- this attempt's own resolvable references (session,
  transcript, evidence, candidate), reusing `orc refs`'s own row builders
  and resolve-command derivation verbatim -- never a second, drifting
  copy of that logic.

A compact run header (intent first line, per-work state+attempts summary)
precedes the per-work sections; each work ends with a state trailer
(`now at <STATE> (attempts=N[, blocked_reason=...])`). The run-level
`next:` affordance (the same shared mapping `status`/`dispatch` use) prints
once, at the very end. Exit code mirrors `status`'s 0/1/3 delivery-state
contract (`refs`/`report` stay unconditional 0, since they carry no
per-work disposition of their own).

| Flag | Default | Notes |
|---|---|---|
| `run` (positional) | required | journal path (dir or `<run>.jsonl`) or bare run id |
| `work` (positional) | none | show only this work id; omit for every work |
| `--journal` | `$ORC_JOURNAL_DIR` or `./.orc` | journal directory |

```bash
orc show my-run-id
orc show my-run-id work-1
orc show my-run-id --journal ./.orc
```

```text
run: my-run-id
intent: ship the widget
works: work-1=ACCEPTED attempts=1
work work-1:
  attempt 1:
  ASKED: prompt = briefs.work-1 (persisted config)
    text: create the widget file and commit it
  EXECUTED: provider=external-agent execution_id=ext-agent:sess-9f2c:work-1
    session: sess-9f2c
    resume: sess-9f2c
    duration: 41.529s (2026-08-29T00:48:54.006149Z -> 2026-08-29T00:49:35.535384Z)
    outcome: completed
  PRODUCED: candidate=cand-git-abc123 fingerprint=fp-abc123
    head_sha: 9dccd6f...
    repo_path: /abs/worktree
  JUDGED: assurance=assure-xyz verdict=accepted
  NEXT/DEEPER:
    session      external-agent   sess-9f2c  (resolve: -)
    candidate    -                {"head_sha":"9dccd6f...","repo_path":"/abs/worktree"}  (resolve: git -C /abs/worktree show 9dccd6f... --stat)
  now at ACCEPTED (attempts=1)
next:
  - work(s) accepted: work-1 -- see the full run report: orc report my-run-id
```

An unknown run or work id is canonical `ERR-NOT-FOUND` with a `next` field
naming the run's actual work ids (or `orc status <run>` when the run itself
is missing).

### `orc refs`

```text
usage: orc refs [-h] [--journal JOURNAL] [--resolve SELECTOR | --resolve-all] target
```

Pure journal projection (no new recording, no new storage -- `CONTRACT-
DURABILITY`'s disposition sentence, "narrative/report content is
provider-owned and the ledger journals resolvable references"): lists
every resolvable reference recorded for one run, one indexed row per
reference, with columns `kind`, `provider`, `value`, and a runnable
`resolve` command. Four independently optional sources, each silently
absent when the run carries none of it -- never fabricated:
`execution-session/v1` session/resume/transcript refs
(`EXT-EXECUTION-SESSION-V1-SCHEMA`) off `FACT-EXEC-SETTLED`; assurance
`evidence_refs` off `FACT-ASSURE-SETTLED` (`PROTOCOL-FACTS`); candidate
identity (`head_sha`/`branch`/`repo_path`/`pr`) off the journaled
`FX-IDENTIFY-CANDIDATE` effect; and the Beads mirror's run label +
workspace, read from the run's own persisted dispatch config when one
configured a `mirror` block. The plain listing never shells out to
anything -- resolve commands are DISPLAY strings only.

| Flag | Default | Notes |
|---|---|---|
| `target` (positional) | required | journal path (dir or `<run>.jsonl`) or bare run id |
| `--journal` | `$ORC_JOURNAL_DIR` or `./.orc` | journal directory |
| `--resolve SELECTOR` | none | execute one ref's resolve command inline (`--resolve`/`--resolve-all` mutually exclusive) |
| `--resolve-all` | off | execute every ref's resolve command inline, each under its own header |

```bash
orc refs my-run-id
orc refs my-run-id --journal ./.orc
orc refs my-run-id --resolve 2            # by the [N] index the plain listing prints
orc refs my-run-id --resolve transcript    # by kind, when exactly one row matches
orc refs my-run-id --resolve-all           # every ref with a resolve command, headered
```

```text
run: my-run-id
[1] session      external-agent   sess-9f2c  (resolve: -)
[2] resume       external-agent   sess-9f2c  (resolve: -)
[3] transcript   external-agent   /abs/path/transcript.log  (resolve: cat /abs/path/transcript.log)
[4] evidence     -                {"exit_code":0,"script":"/abs/repo/assure.sh","script_sha256":"306c6ca7...","timed_out":false} verdict=accepted  (resolve: -)
[5] candidate    -                {"branch":"feature/widget","head_sha":"abc123","repo_path":"/abs/worktree"}  (resolve: git -C /abs/worktree show abc123 --stat)
[6] mirror       beads            label=run:my-run-id workspace=/abs/bd-workspace  (resolve: bd --json -C /abs/bd-workspace list --label run:my-run-id)
```

A run with no resolvable references at all prints a definitive `0 refs
for <run-id>` plus a one-line pointer at `orc status <run-id>` (same
"content first" empty-state convention as bare `orc`/`orc report`).

#### `--resolve`/`--resolve-all` (`TASK-M3C-002`)

Executes the SAME command the listing displays -- one vocabulary, what
you see is what runs. There is no second command string built from
scratch: every row's resolve command is built once, as an argv list, by
the same builder that renders its display string (`ResolveCommand.of`/
`from_raw_text`, `orc_werk.cli.refs`), so a display string and its argv
can never diverge (mutation-honest: change the argv, the display changes
with it).

Every resolve command -- builder-constructed (session, transcript,
candidate, mirror, `candidate-pr`) or carried as journal DATA (an
`evidence_refs` entry's `command`/`*_command` field) -- is vetted against
a hard, per-tool READ-ONLY allowlist at construction time, before it is
ever offered for execution (the same judge-only bar
`docs/adapters/command/mapping.md`'s read-only-judge rule sets for the
command assurance adapter). Vetting has TWO layers, both required: (1) a
tool+subcommand allowlist -- `cat <path>`; `git [-C <path>] show ...` (no
other git subcommand); `acpx <agent> sessions <history|show> ...`; `bd
[--json] [-C <path>] <list|show> ...`; `no-mistakes axi <status|logs>
...`, nothing else; and (2) a **per-tool FLAG policy** over every token
AFTER the subcommand (`_vet_flags`), because vetting the subcommand alone
is an arbitrary-file-WRITE hole -- `git show --output=<path>` is a
documented git write primitive that passes layer 1 (its subcommand is
`show`). **Note (`ADR-0005` ruling A2):** the `acpx`/`no-mistakes` tool
entries above are retained specifically to resolve refs recorded by
historical journals from the now-removed `acp`/`no-mistakes` adapters
(`v0.4.1` and earlier); read-only resolution of a past run's recorded ref
is not pull-observation of a live process, so this allowlist surface
stays live even though those adapters themselves are gone. Layer 2
refuses git's write/exec options (`--output`/`-o`/`-O`,
`--ext-diff`, `--textconv`) and any unknown flag (fail-closed), while
allowing only curated read/render-only flags (`--stat`, `--numstat`,
`--name-only`, ...); a value-taking flag's value is consumed unparsed so
it can never be re-read as a flag. Journal content is attacker-
influencable input (any executor that filled a seat wrote some of it), so
interpolated identity tokens (candidate `head_sha`/`repo_path`, provider
session/agent ref) that begin with `-` are ALSO rejected at build time --
the builder never mints a token that could be read as a flag (`git show
--stat -- <sha>` can't guard the sha positionally: git would read it as a
pathspec, so the guard is build-time `-`-lead rejection plus the flag
policy). Notably `gh pr view <pr>` (the `candidate-pr` row) is NOT in the
allowlist at all, so that row keeps displaying unchanged but never
executes. A command outside either layer -- a mutating one smuggled into a
journal's `evidence_refs` (`git push`, `bd create`, `rm -rf`) OR a write-
flag smuggled onto an allowed subcommand (`git show --output=...`, via an
evidence string or a crafted `head_sha`) -- REFUSES to execute: it prints
`REFUSED: <reason>` plus the manual command, and writes nothing.

Selectors: the `[N]` index the plain listing prints (copy-pasteable
as-is), or `<kind>[:<substring>]` -- every row of that kind, optionally
narrowed by a substring of its `value`, selected only when exactly one
match remains; an out-of-range, absent, or ambiguous selector is
canonical `ERR-VALIDATION` (exit 2) with a `next` pointer (issue #94)
naming the valid range or the matching indices -- never a silent guess.

Execution is bounded (~30s per command, never `shell=True`), and content
is size-capped (8 KiB) with a definitive truncation note plus the manual
command for the full view when exceeded -- resolved content itself is
raw adapter-native passthrough (verbatim stdout), not escaped or
filtered, since it is the thing the operator explicitly asked to see; only
the size cap applies. Resolution FAILURE (refusal, missing binary,
nonzero exit, timeout) is never an `orc refs` run failure -- the ref
itself remains valid even when resolving it did not produce content, so
exit stays `0`; only a bad selector or missing run is a hard usage error.

```text
$ orc refs my-run-id --resolve 3
run: my-run-id
--- [3] transcript (external-agent): cat /abs/path/transcript.log ---
<the transcript file's contents, verbatim, capped at 8 KiB>
```

### `orc report`

```text
usage: orc report [-h] [--index] [--all] [--match MATCH] [--journal JOURNAL]
                   [--out OUT] [--out-dir OUT_DIR]
                   [run]
```

Renders a self-contained HTML run report, or a local index page over a
journal directory's runs (`TASK-M1-008`). The unscoped HTML index uses the
same most-recently-active-first journal-mtime order and per-run state rollup
as bare `orc`; a scoped `--all` index preserves its caller-provided match order.

| Flag | Default | Notes |
|---|---|---|
| `run` (positional) | none | journal path or bare run id; required unless `--index`/`--all` |
| `--index` | off | render an index page over the journal directory's runs instead |
| `--all` | off | render every run whose `run_id` matches `--match` to its own file plus a scoped index |
| `--match` | `'*'` | `fnmatch` glob over `run_id`, used with `--all` (e.g. `'m1.*'` selects a namespace) |
| `--journal` | `$ORC_JOURNAL_DIR` or `./.orc` | journal directory |
| `--out` | announced default (see below) | output HTML path |
| `--out-dir` | the journal directory | output directory for `--all` |

```bash
orc report my-run-id
orc report --index
orc report --all --match 'm1.*'
```

Default `--out` path: `<journal-dir>/<run_id>/report.html` for a run on the
new per-run-directory layout, or `<journal-dir>/<run_id>.report.html` for a
run still on the legacy flat layout; `--index` defaults to
`<journal-dir>/index.html`. `--all`'s per-run output files are always flat
under `--out-dir` (or the journal dir) regardless of any individual run's
own layout -- `--all`'s whole point is gathering many runs into one place
with one shared index.

Every path this CLI prints (`journal:`, `report:`, index-listing lines) is
the resolved absolute path. When stdout is a TTY, it is additionally
wrapped in an OSC 8 hyperlink escape sequence (`file://` target, same plain
path as the visible text) so supporting terminals make it clickable
(issue #55). When stdout is not a TTY -- a pipe, a redirect, or an agent
capturing output programmatically -- the plain path prints byte-identical,
with zero escape bytes.

### `orc onboard`

```text
usage: orc onboard [-h] [--path PATH] [--print-agents-block] [--force]
                    [--agents-file NAME] [--journal JOURNAL]
                    [--agents-block {slim,full}] [--ledger {local,committed}]
```

Mechanically scaffolds an adopting repository (`TASK-M3D-001`, `TASK-M4A-001`, `TASK-M4A-004`) -- the
hand-work `docs/product/adoption.md` (`PRODUCT-ADOPTION`) used to describe
as a manual copy. Four independently idempotent steps, each reported
honestly on its own line:

1. **ledger placement / gitignore** -- `--ledger local` (the default) ensures a
   `.orc/` entry exists in `<path>/.gitignore`. `--ledger committed` writes no
   ignore entry; if one already exists, onboard warns and leaves removal to the
   operator. The report and agents block state the selected placement.
2. **repo-default profile** -- write an empty starter `<path>/.orc/profile.json`; an exact match skips, a mismatch skips-with-note, and `--force` overwrites. This is scaffolding only and never creates or writes a journal.
3. **skill install** -- write the versioned orc-ledger skill and its release
   history to `<path>/.agents/skills/orc-ledger/SKILL.md` and the adjacent
   `CHANGELOG.md`, and link
   `<path>/.claude/skills/orc-ledger` to it (a relative symlink,
   `../../.agents/skills/orc-ledger`, resolving correctly from the link's
   own directory -- the issue #63 lesson) so Claude Code's project-skill
   discovery finds it directly. **The content is read from THIS installed
   package** (`orc_werk.skills`, via `importlib.resources`) -- the single
   canonical origin `onboard` copies from; it is never a second,
   hand-maintained copy of the six-rule protocol embedded in this CLI's own
   source.
4. **agents-onboarding block** -- a copy-pasteable `## Delivery ledger
   (orc)` block written into `<path>/<agents-file>` (default `AGENTS.md`) and
   wrapped in markers for safe comparison. The default `--agents-block slim`
   contains only the profile-derived **MODE DECLARATION**, selected ledger
   locality, and a requirement to load `.claude/skills/orc-ledger` before
   touching the ledger. The skill remains the single protocol copy. Select
   `--agents-block full` only for harnesses without skill support; this form
   mechanically transforms and inlines the packaged skill. `--print-agents-block`
   prints the selected block and writes nothing.
5. **install verification** -- honestly reports the installed orc-ledger
   skill version; `orc` on `$PATH` (`shutil.which`) vs. this interpreter's own ability to import
   `orc_werk` (module form); the journal directory `--journal`/
   `$ORC_JOURNAL_DIR`/`./.orc` precedence would resolve to, anchored at
   `--path`; and the optional `bd` binary's presence (Beads mirror,
   noted-optional, never required). Fabricates nothing -- every line names
   what was checked and its found/absent outcome.

| Flag | Default | Notes |
|---|---|---|
| `--path` | `.` | target repository directory |
| `--print-agents-block` | off | print the agents-onboarding block only; no other step runs, nothing is written |
| `--force` | off | overwrite/replace a target that already exists with different content (default: skip-with-note) |
| `--agents-file` | `AGENTS.md` | agent-instructions file (relative to `--path`) the Delivery ledger block is written into |
| `--journal` | `$ORC_JOURNAL_DIR` or `./.orc` | journal directory the verification step reports on (anchored at `--path`); `onboard` never creates a journal itself |
| `--agents-block` | `slim` | `slim` points to the installed skill; `full` inlines it for harnesses without skill support |
| `--ledger` | `local` | `local` adds the ignore entry and declares operator-machine locality; `committed` leaves gitignore unchanged and declares shared repository state |

```bash
orc onboard --path /path/to/adopting-repo
orc onboard --path . --force              # re-run, overwriting operator-modified targets
orc onboard --print-agents-block           # prints slim block only, writes nothing
orc onboard --ledger committed             # shared ledger, no new ignore entry
orc onboard --agents-block full             # harness cannot load project skills
```

**Joining a shared portfolio:** after onboarding, set `mirror.workspace` and `mirror.project` in the repository's `.orc/profile.json`. Every participating repository uses the same absolute workspace path and a distinct project name:

```json
{
  "mirror": {
    "adapter": "beads",
    "workspace": "/home/alice/orc-portfolio",
    "project": "payments"
  }
}
```

Keep that repository's journal local through `ORC_JOURNAL_DIR` or the local `./.orc` default. The shared workspace is only the write-only mirror destination; read the portfolio with `bd`'s own CLI. See `PLAYBOOK-PORTFOLIO-COCKPIT` for the sanctioned read-back commands and boundary.

**Idempotent and non-destructive by construction**: every step compares
what it would write against what is already there. An exact skill match is
reported with its version and skipped. A differing skill whose content hash
is recorded as a prior release in the packaged changelog is a clean stale
copy, so `orc onboard` upgrades it and its changelog automatically. An
unknown hash is operator-modified and remains `skip-with-note` by default
(never a hard failure) unless `--force` is given. The same never-clobber rule
applies to the `.claude/skills` link, changelog, and agents-block markers.
Errors (`--path` missing or not a directory) are canonical `ERR-VALIDATION`
with `next` guidance (issue #94), exit `2`; every other exit is `0`.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | all Work `ACCEPTED` |
| `1` | some Work `BLOCKED` (or another non-accepted terminal state) |
| `2` | usage/config error -- canonical error JSON on stderr: `{"error": "ERR-*", "message": "...", "details": {...}}`, optionally with the additive `"next": ["next-step guidance", "..."]` field |
| `3` | run non-terminal, pending settlement -- safe to re-check; the current attempt's outcome (`execution-outcome`) or verdict (`assurance-verdict`) has not been observed or recorded yet. Re-dispatch is the poll: for an external executor that pushes its observation in (`ADR-0005`) the re-dispatch pass itself picks up and journals the settlement once it has been recorded -- no hand-recorded `attempts` entry is needed beyond that push (issue #210); operator-recorded inputs (scripted outcomes, assurance verdicts) must be recorded first, then re-dispatched |
| `4` | `dispatch --wait --timeout <T>` only -- `T` seconds elapsed with the pending fingerprint unchanged (`SCN-017`, issue #210); re-invoking (with or without `--wait`) is always safe, the run is exactly as pending as before |

Exit `3`'s semantics -- what "pending" means, why nothing is fabricated for
a missing settlement, and why re-dispatch is the correct and only resume
mechanism -- are normatively specified in `docs/scenarios/SCN-007-pending-settlement.md`
(`SCN-007`); do not treat this table as more than a pointer to it. `dispatch`/
`status` output for a pending run always names which Work is waiting and
for what, followed by a `next:` block naming the exact runnable next
command. Exit `4` and `dispatch --wait`'s semantics -- the pending
fingerprint, baseline computation, and silence-until-exit behavior -- are
normatively specified in `docs/scenarios/SCN-017-wait-resting-point.md`
(`SCN-017`); see "`orc dispatch --wait`" below.

Verified exit codes from this document's own runs (see per-command sections
above for `0` and `3`):

```bash
# exit 1 -- retry budget exhausted, one failed attempt, max_attempts=1
orc dispatch "blocked demo" --config blocked-cfg.json --journal ./.orc --run-id demo-blocked
# work work-1: state=BLOCKED ... blocked_reason=retry-budget-exhausted
# exit=1

# exit 2 -- config path does not exist
orc dispatch "bad" --config does-not-exist.json --journal ./.orc --run-id demo-bad
# {"details": {}, "error": "ERR-NOT-FOUND", "message": "[Errno 2] No such file or directory: 'does-not-exist.json'", "next": ["double check the path was typed correctly", "orc (bare) lists every run id under the default journal dir"]}
# exit=2
```

## Config schema

The `orc dispatch --config <path>` and `.orc/profile.json` schema (including `execution`,
`candidate`, `assurance`, `mirror`, `briefs`, `plan`, and `attempts`) is
CLI-owned composition, not a canonical protocol shape. Run `orc
config-schema` to print it. The command emits the module docstring of
`src/orc_werk/cli/config.py` verbatim; that docstring remains the sole source
of truth, and this reference does not fork it. A one-minute example lives in
`docs/playbooks/cli-usage.md`'s "Config in one minute" section.

## Journal file layout

Every run created under the current code writes the **new per-run
directory layout**: `<journal-dir>/<run_id>/` holding

- `journal.jsonl` -- the canonical `JournalPort` file, one JSON envelope per
  line with `schema_version` on each; portable, `jq`-readable, no
  orc-werk imports required to read it.
- `times.jsonl` -- observed-at sidecar (`CONTRACT-DURABILITY`).
- `report.html` -- this run's default `orc report` output.
- `config.json` -- the persisted effective dispatch config (issue #55 H2;
  see `orc dispatch`'s "Config persistence" section above).

Verified layout from this document's demo run:

```text
$ ls .orc/demo-run-1/
config.json  journal.jsonl  report.html  times.jsonl
```

Run lifecycle is directory lifecycle for this layout: a run "exists" once
its directory does.

A **legacy flat `.orc` directory from before issue #55 keeps working
unmodified** -- every read path (bare `orc` index, `status`/`history` by
bare run id, `report`/`report --index`/`--all`/`--match`, sidecar
discovery) accepts both layouts, and each artifact (journal, times
sidecar) is decided independently per its own legacy filename's
existence. The `+` character (`<run_id>+times.jsonl`) is reserved for
legacy sidecars and cannot appear in a run id (a pre-removal run may also
still hold a legacy `<run_id>+reports.jsonl` `crew-report/v1` sidecar,
`EXT-CREW-REPORT-V1`, superseded, issue #100 part 2 -- inert; `orc` no
longer reads or writes it, but the `+` exclusion still keeps it out of the
run-id sweep). Full detail, including the run-id namespace convention
(`m1.task-005`-style dot-separated prefixes for `--match` grouping), is in
`docs/playbooks/cli-usage.md`'s "Journal layout" and "Run-id namespace
convention" sections -- this reference does not duplicate it.

## Related

- `docs/playbooks/cli-usage.md` (`PLAYBOOK-CLI-USAGE`) -- operational
  guide, known-issues ledger, real `git`/command-assurance port config, journal-layout
  detail.
- `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) -- ship/verify
  seat discipline for recording settlements, candidates, and verdicts.
- `.agents/skills/orc-ledger/SKILL.md` -- fresh-session onboarding skill.
- `docs/product/adoption.md` (`PRODUCT-ADOPTION`) -- the adoption ladder
  and per-rung mechanical install story `orc onboard` fulfills rung 2 of.
- `PLAYBOOK-PORTFOLIO-COCKPIT` -- shared-board setup and bd-native
  portfolio read-back recipes.
- `docs/scenarios/SCN-007-pending-settlement.md` (`SCN-007`) -- normative
  spec for exit `3` / pending-settlement behavior.
- `docs/extensions/crew-report/README.md` (`EXT-CREW-REPORT-V1`, superseded)
  -- the removed narrative-report sidecar; historical reference only.
- `src/orc_werk/cli/config.py` -- config schema source of truth.
- `docs/contracts/durability-responsibilities.md` (`CONTRACT-DURABILITY`)
  -- the reference-first doctrine `orc refs` projects
  (`docs/extensions/execution-session/` is the schema its first source
  reads).
