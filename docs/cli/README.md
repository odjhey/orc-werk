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
  dogfooding live, real `acp`/`git` port wiring, and the full journal-layout
  discussion.
- `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) -- ship-agent /
  verification-agent seat discipline for recording settlements and verdicts.
- `.agents/skills/orc-ledger/SKILL.md` -- the fresh-session onboarding
  skill: orient via bare `orc`, resume-don't-duplicate, seat discipline,
  recording mechanics.

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
orc history demo-run-1                # the full seq-ordered fact/decision/effect record
orc report demo-run-1                 # self-contained HTML report at .orc/demo-run-1/report.html
```

A bare run id resolves against `$ORC_JOURNAL_DIR` or `./.orc`; pass an
explicit journal directory or file path instead when working outside the
default location.

## Commands

### `orc` (bare, no arguments)

Prints a live text index of the default journal directory -- run id,
per-work state, attempts, pending flags, one line per run,
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
demo-pending: work-1=ACCEPTED attempts=1
demo-run-1: work-1=ACCEPTED attempts=1
orc status <run-id> for next-step guidance on one run; orc report --index for the full unpaginated HTML index over /abs/path/.orc.
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

### `orc dispatch`

```text
usage: orc dispatch [-h] [--config CONFIG] [--journal JOURNAL]
                     [--max-attempts MAX_ATTEMPTS] [--run-id RUN_ID]
                     [intent]
```

Dispatch an intent and run the delivery state machine to a resting point
(terminal, or pending awaiting operator-recorded input).

| Flag | Default | Notes |
|---|---|---|
| `intent` (positional) | required for new runs | the intent text to submit; optional with `--run-id` naming an existing run whose journal holds its durable intent |
| `--config` | none (empty scripted config) | path to a portable JSON dispatch config; see "Config schema" below. Omittable on a **later** dispatch of a run that already has a persisted config (see "Config persistence" below) |
| `--journal` | `$ORC_JOURNAL_DIR` or `./.orc` | journal directory |
| `--max-attempts` | policy default `3` | overrides the run's retry budget |
| `--run-id` | derived deterministically from the intent text | explicit `delivery_run_id` |

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
pending: run is non-terminal, awaiting operator-recorded input for: work-1
next:
  - record the execution outcome for work(s): work-1
  - then re-run: orc dispatch 'pending demo' --config /abs/path/.orc/demo-pending/config.json --journal /abs/path/.orc --run-id demo-pending
```

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

**Real `acp`/`git` execution** (a real agent driven over ACP, a real git
worktree fingerprinted as the candidate) is config-driven the same way --
see `docs/playbooks/cli-usage.md`'s "Real execution" section for the
`execution`/`candidate` config blocks and the full walkthrough. Provider
vocabulary (ACP session semantics, git diff fingerprinting) lives in the
adapters' own mapping docs: `docs/adapters/acp/mapping.md`,
`docs/adapters/git/mapping.md`.

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

### `orc history`

```text
usage: orc history [-h] [--journal JOURNAL] [--limit LIMIT]
                   [--since-seq SINCE_SEQ]
                   target
```

The full seq-ordered fact/decision/effect record -- root-cause detail
(dispatch-gate errors, decision basis) lives here.

| Flag | Default | Notes |
|---|---|---|
| `target` (positional) | required | journal path (dir or `<run>.jsonl`) or bare run id |
| `--journal` | `$ORC_JOURNAL_DIR` or `./.orc` | journal directory |
| `--limit` | `30` | most-recent records to show; `0` for all |
| `--since-seq` | none | only records with `seq` greater than the given value |

For a bare run id, the journal directory resolves with `--journal` >
`ORC_JOURNAL_DIR` > `./.orc` precedence.

Paginated: a truncated result prints a definitive
`... showing last N of M` hint, never an ambiguous "...more".

```bash
orc history my-run-id
orc history my-run-id --journal ./.orc
orc history my-run-id --limit 0
orc history my-run-id --since-seq 12
```

Sample record line (`jq`-readable JSONL underneath -- see "Journal file
layout" below):

```text
[0007] decision DEC-DISPATCH   {"attempt_number":1,"attribution":{"policy":"v0-deterministic"},"basis":[...],"work_id":"work-1"}
```

### `orc refs`

```text
usage: orc refs [-h] [--journal JOURNAL] target
```

Pure journal projection (no new recording, no new storage -- `CONTRACT-
DURABILITY`'s disposition sentence, "narrative/report content is
provider-owned and the ledger journals resolvable references"): lists
every resolvable reference recorded for one run, one row per reference,
with columns `kind`, `provider`, `value`, and a runnable `resolve`
command. Four independently optional sources, each silently absent when
the run carries none of it -- never fabricated: `execution-session/v1`
session/resume/transcript refs (`EXT-EXECUTION-SESSION-V1-SCHEMA`) off
`FACT-EXEC-SETTLED`; assurance `evidence_refs` off `FACT-ASSURE-SETTLED`
(`PROTOCOL-FACTS`); candidate identity (`head_sha`/`repo_path`/`pr`) off
the journaled `FX-IDENTIFY-CANDIDATE` effect; and the Beads mirror's run
label + workspace, read from the run's own persisted dispatch config when
one configured a `mirror` block. Resolve commands are DISPLAY strings
only -- `orc refs` never shells out to anything.

| Flag | Default | Notes |
|---|---|---|
| `target` (positional) | required | journal path (dir or `<run>.jsonl`) or bare run id |
| `--journal` | `$ORC_JOURNAL_DIR` or `./.orc` | journal directory |

```bash
orc refs my-run-id
orc refs my-run-id --journal ./.orc
```

```text
run: my-run-id
session      acpx-pi          sess-9f2c  (resolve: acpx pi sessions history sess-9f2c)
resume       acpx-pi          resume-ref-9f2c  (resolve: -)
transcript   acpx-pi          /abs/path/transcript.log  (resolve: cat /abs/path/transcript.log)
evidence     -                {"command":"no-mistakes axi status --run r1", ...}  (resolve: no-mistakes axi status --run r1)
candidate    -                {"head_sha":"abc123","repo_path":"/abs/worktree"}  (resolve: git -C /abs/worktree show abc123 --stat)
mirror       beads            label=run:my-run-id workspace=/abs/bd-workspace  (resolve: bd --json -C /abs/bd-workspace list --label run:my-run-id)
```

A run with no resolvable references at all prints a definitive `0 refs
for <run-id>` plus a one-line pointer at `orc status <run-id>` (same
"content first" empty-state convention as bare `orc`/`orc report`).

### `orc report`

```text
usage: orc report [-h] [--index] [--all] [--match MATCH] [--journal JOURNAL]
                   [--out OUT] [--out-dir OUT_DIR]
                   [run]
```

Renders a self-contained HTML run report, or a local index page over a
journal directory's runs (`TASK-M1-008`).

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

## Exit codes

| Code | Meaning |
|---|---|
| `0` | all Work `ACCEPTED` |
| `1` | some Work `BLOCKED` (or another non-accepted terminal state) |
| `2` | usage/config error -- canonical error JSON on stderr: `{"error": "ERR-*", "message": "...", "details": {...}}` |
| `3` | run non-terminal, pending operator-recorded input -- safe to re-check; the current attempt's outcome (`execution-outcome`) or verdict (`assurance-verdict`) has not been recorded yet |

Exit `3`'s semantics -- what "pending" means, why nothing is fabricated for
a missing settlement, and why re-dispatch is the correct and only resume
mechanism -- are normatively specified in `docs/scenarios/SCN-007-pending-settlement.md`
(`SCN-007`); do not treat this table as more than a pointer to it. `dispatch`/
`status` output for a pending run always names which Work is waiting and
for what, followed by a `next:` block naming the exact runnable next
command.

Verified exit codes from this document's own runs (see per-command sections
above for `0` and `3`):

```bash
# exit 1 -- retry budget exhausted, one failed attempt, max_attempts=1
orc dispatch "blocked demo" --config blocked-cfg.json --journal ./.orc --run-id demo-blocked
# work work-1: state=BLOCKED ... blocked_reason=retry-budget-exhausted
# exit=1

# exit 2 -- config path does not exist
orc dispatch "bad" --config does-not-exist.json --journal ./.orc --run-id demo-bad
# {"details": {}, "error": "ERR-NOT-FOUND", "message": "[Errno 2] No such file or directory: '...'"}
# exit=2
```

## Config schema

The `orc dispatch --config <path>` schema (including `execution`,
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
  guide, known-issues ledger, real `acp`/`git` port config, journal-layout
  detail.
- `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) -- ship/verify
  seat discipline for recording settlements, candidates, and verdicts.
- `.agents/skills/orc-ledger/SKILL.md` -- fresh-session onboarding skill.
- `docs/scenarios/SCN-007-pending-settlement.md` (`SCN-007`) -- normative
  spec for exit `3` / pending-settlement behavior.
- `docs/extensions/crew-report/README.md` (`EXT-CREW-REPORT-V1`, superseded)
  -- the removed narrative-report sidecar; historical reference only.
- `src/orc_werk/cli/config.py` -- config schema source of truth.
- `docs/contracts/durability-responsibilities.md` (`CONTRACT-DURABILITY`)
  -- the reference-first doctrine `orc refs` projects
  (`docs/extensions/execution-session/` is the schema its first source
  reads).
