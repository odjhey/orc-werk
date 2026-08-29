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

### Bare `orc` run index

```text
usage: orc [--limit LIMIT]
```

The content-first invocation lists the most-recently-active runs in the
default journal directory. It shows 30 by default; `--limit N` bounds the
listing and `--limit 0` shows all runs. A truncated listing names
`orc --limit 0` first; `orc report --index` is the secondary HTML view.
The journal directory resolves from `ORC_JOURNAL_DIR`, then `./.orc`.

```bash
orc
orc --limit 10
orc --limit 0
```

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
  When `execution.adapter` is not `"acp"` (the default `"scripted"`), no
  prompt is ever sent -- rendered honestly as `scripted execution -- no
  prompt sent to the executor`, never guessed.
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
  EXECUTED: provider=acpx-pi execution_id=acpx-pi:orcw-abc123:work-1
    session: 01a0...
    resume: orcw-abc123
    duration: 41.529s (2026-08-29T00:48:54.006149Z -> 2026-08-29T00:49:35.535384Z)
    outcome: completed
  PRODUCED: candidate=cand-git-abc123 fingerprint=fp-abc123
    head_sha: 9dccd6f...
    repo_path: /abs/worktree
  JUDGED: assurance=assure-xyz verdict=accepted
  NEXT/DEEPER:
    session      acpx-pi          01a0...  (resolve: acpx pi sessions history 01a0...)
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
identity (`head_sha`/`repo_path`/`pr`) off the journaled
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
[1] session      acpx-pi          sess-9f2c  (resolve: acpx pi sessions history sess-9f2c)
[2] resume       acpx-pi          resume-ref-9f2c  (resolve: -)
[3] transcript   acpx-pi          /abs/path/transcript.log  (resolve: cat /abs/path/transcript.log)
[4] evidence     -                {"command":"no-mistakes axi status --run r1", ...}  (resolve: no-mistakes axi status --run r1)
[5] candidate    -                {"head_sha":"abc123","repo_path":"/abs/worktree"}  (resolve: git -C /abs/worktree show abc123 --stat)
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
`docs/adapters/no-mistakes/mapping.md`'s "Judge-only ruling" sets for the
assurance adapter). Vetting has TWO layers, both required: (1) a
tool+subcommand allowlist -- `cat <path>`; `git [-C <path>] show ...` (no
other git subcommand); `acpx <agent> sessions <history|show> ...`; `bd
[--json] [-C <path>] <list|show> ...`; `no-mistakes axi <status|logs>
...`, nothing else; and (2) a **per-tool FLAG policy** over every token
AFTER the subcommand (`_vet_flags`), because vetting the subcommand alone
is an arbitrary-file-WRITE hole -- `git show --output=<path>` is a
documented git write primitive that passes layer 1 (its subcommand is
`show`). Layer 2 refuses git's write/exec options (`--output`/`-o`/`-O`,
`--ext-diff`, `--textconv`) and any unknown flag (fail-closed), while
allowing only curated read/render-only flags (`--stat`, `--numstat`,
`--name-only`, ...); a value-taking flag's value is consumed unparsed so
it can never be re-read as a flag. Journal content is attacker-
influencable input (any executor that filled a seat wrote some of it), so
interpolated identity tokens (candidate `head_sha`/`repo_path`, `acpx`
agent/session ref) that begin with `-` are ALSO rejected at build time --
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
--- [3] transcript (acpx-pi): cat /abs/path/transcript.log ---
<the transcript file's contents, verbatim, capped at 8 KiB>
```

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

### `orc onboard`

```text
usage: orc onboard [-h] [--path PATH] [--print-agents-block] [--force]
                    [--agents-file NAME] [--journal JOURNAL]
```

Mechanically scaffolds an adopting repository (`TASK-M3D-001`) -- the
hand-work `docs/product/adoption.md` (`PRODUCT-ADOPTION`) used to describe
as a manual copy. Four independently idempotent steps, each reported
honestly on its own line:

1. **gitignore** -- ensure a `.orc/` entry exists in `<path>/.gitignore`
   (create the file if absent, append the entry if missing, skip-with-note
   if already present). Append-only: an existing line is never rewritten.
2. **skill install** -- write the orc-ledger skill's content to
   `<path>/.agents/skills/orc-ledger/SKILL.md`, and link
   `<path>/.claude/skills/orc-ledger` to it (a relative symlink,
   `../../.agents/skills/orc-ledger`, resolving correctly from the link's
   own directory -- the issue #63 lesson) so Claude Code's project-skill
   discovery finds it directly. **The content is read from THIS installed
   package** (`orc_werk.skills`, via `importlib.resources`) -- the single
   canonical origin `onboard` copies from; it is never a second,
   hand-maintained copy of the six-rule protocol embedded in this CLI's own
   source.
3. **agents-onboarding block** -- a copy-pasteable `## Delivery ledger
   (orc)` block (the same six-rule content step 2 installs, mechanically
   derived from it -- strip the YAML frontmatter and the H1 title, keep
   everything else verbatim) written into `<path>/<agents-file>` (default
   `AGENTS.md`), wrapped in HTML-comment markers so a re-run can detect and
   compare it. `--print-agents-block` prints this block to stdout and
   performs no other step -- writes nothing at all -- for pasting into
   whatever agent-instructions file a repo already uses.
4. **install verification** -- honestly reports: `orc` on `$PATH`
   (`shutil.which`) vs. this interpreter's own ability to import
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

```bash
orc onboard --path /path/to/adopting-repo
orc onboard --path . --force              # re-run, overwriting operator-modified targets
orc onboard --print-agents-block           # prints only, writes nothing
```

**Idempotent and non-destructive by construction**: every step compares
what it would write against what is already there. An exact match is a
`skip` note (no write). A target that already exists with *different*
content -- the skill file, the `.claude/skills` link, or the agents-block
markers -- is `skip-with-note` by default (never a hard failure) unless
`--force` is given, which overwrites/replaces it in place, also reported.
Errors (`--path` missing or not a directory) are canonical `ERR-VALIDATION`
with `next` guidance (issue #94), exit `2`; every other exit is `0`.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | all Work `ACCEPTED` |
| `1` | some Work `BLOCKED` (or another non-accepted terminal state) |
| `2` | usage/config error -- canonical error JSON on stderr: `{"error": "ERR-*", "message": "...", "details": {...}}`, optionally with the additive `"next": ["next-step guidance", "..."]` field |
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
# {"details": {}, "error": "ERR-NOT-FOUND", "message": "[Errno 2] No such file or directory: 'does-not-exist.json'", "next": ["double check the path was typed correctly", "orc (bare) lists every run id under the default journal dir"]}
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
- `docs/product/adoption.md` (`PRODUCT-ADOPTION`) -- the adoption ladder
  and per-rung mechanical install story `orc onboard` fulfills rung 2 of.
- `docs/scenarios/SCN-007-pending-settlement.md` (`SCN-007`) -- normative
  spec for exit `3` / pending-settlement behavior.
- `docs/extensions/crew-report/README.md` (`EXT-CREW-REPORT-V1`, superseded)
  -- the removed narrative-report sidecar; historical reference only.
- `src/orc_werk/cli/config.py` -- config schema source of truth.
- `docs/contracts/durability-responsibilities.md` (`CONTRACT-DURABILITY`)
  -- the reference-first doctrine `orc refs` projects
  (`docs/extensions/execution-session/` is the schema its first source
  reads).
