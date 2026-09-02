---
id: ADAPTER-BEADS-MAPPING
type: adapter-mapping
status: current
authority: informative
description: Write-only Beads (bd) mirror mapping for BeadsMirror (TASK-M2-006).
---

# Beads mapping

Implemented by `src/orc_werk/adapters/beads/mirror.py` (`BeadsMirror`), a
**write-only projection** of one `DeliveryRun`'s journal-derived run/work
state and briefs into a shared, label-scoped `bd` database. All `bd`
vocabulary (CLI flags, id/label discipline, status/metadata mapping) stays
in this document and that module, per `INV-014` and
`docs/adapters/README.md`.

**This is not a `PORT-WORK-GRAPH` implementation.** `BeadsMirror` claims no
conformance to that port and implements none of its interface. It is a
pure observer of `MemoryWorkGraph`/journal-derived state
(`JournalPort.history`, `DeliveryProjection`); nothing it writes to `bd` is
ever read back by this adapter or any caller, and no `bd` state ever feeds
a dispatch decision. `bd`-native ready/claim/dependency logic driving real
dispatch decisions ("authority graduation") is a dormant, unbuilt future
path recorded on issue #47 (`docs/delivery/task-cards/
TASK-M2-006-beads-mirror.md`'s "Slice boundary" section) -- explicitly out
of scope for this adapter.

## Version pin

- `bd version` == `1.2.2` (Homebrew, `/opt/homebrew/bin/bd` at
  implementation time) -- `orc_werk.adapters.beads.mirror.BD_VERSION_PIN`.
  Informative only, matching the version-pin precedent set by the
  since-superseded acp/no-mistakes adapters (`ADR-0005`): this adapter shells out to whatever `bd` is actually
  configured (`mirror.bd_bin`, default `"bd"` resolved via `PATH`), never
  version-gates at runtime.
- `bd` is an adapter-local dependency (`src/orc_werk/core` remains
  stdlib-only and unaffected -- `CLAUDE.md` rule 8; this adapter lives
  entirely under `src/orc_werk/adapters/beads/`).

## Design decisions

### Direct CLI invocations, subprocess-per-operation

`bd --json <verb> -C <workspace> ...`, one process per operation --
matching the subprocess-per-operation pattern the since-superseded
acp/no-mistakes adapters established (`docs/adapters/acp/mapping.md`;
also `docs/adapters/command/mapping.md`'s single-script-subprocess
invocation). `bd` is the "easy instance" of this
pattern (task card): no daemon, no streams, fully synchronous ops. Every
`BeadsMirror.project_run` call re-syncs full current state (create-or-
upsert every Work, then re-issue the status/metadata update for every
Work) rather than diffing against previously-observed state -- see
"Idempotency" below for why this is safe to do on every dispatch,
including a redundant re-poll of an already-fully-mirrored run.

### `--graph` was evaluated and rejected

The task card's inherited design names `bd create --graph` (issued after
this adapter's own plan-validation pre-flight, mirroring
`PORT-WORK-001`'s `validate_plan` discipline) as the intended
graph-creation primitive. Empirically, against real `bd` 1.2.2 (this
task's recon, a disposable sandbox database, never an operator's real
one):

- `bd create --graph <plan.json>`'s graph-plan JSON schema is `{"nodes":
  [{"key": ..., "title": ..., ...}], "edges": [{"from_key": ..., "to_key":
  ..., "type": "blocks"}]}` (reverse-engineered from `bd`'s own error
  messages and a compiled-in hint string, since `--graph --help` is not a
  parseable form -- `--graph` consumes the very next token as its file
  argument).
- A per-node `"id"` field is **silently dropped** (`bd` warns "unknown
  field(s): [id]" and always assigns its own random id) -- there is no way
  to make `bd create --graph` honor an explicit, deterministic id.
- `--parent` and `--id` are **mutually exclusive flags** ("cannot specify
  both --id and --parent flags") -- even a per-Work `bd create --id ...
  --parent <run-level-epic>` combination (a run-level parent/child
  hierarchy this adapter considered and dropped, see "Lossy mappings"
  below) is unavailable together with an explicit id.
- The top-level `--label` this adapter would pass to the `create --graph`
  invocation itself does **not** propagate to the individual nodes it
  creates (confirmed: neither created issue carried the label afterward).

Every one of these is structurally incompatible with two of this card's
OTHER stated non-negotiable requirements -- deterministic
`--id <run_id>--<work_id>` (`INV-020`) and `--label run:<run_id>` on every
`create` (the shared-DB isolation discipline the ratified mirror-mode
posture, issue #47, depends on -- see "Label discipline" below for the
exact create-vs-update/close scoping). Rather than improvise a different
separator or silently drop one of the two conflicting non-negotiable
requirements, this adapter does not use `--graph` at all: it issues one
`bd create --id <run_id>--<work_id> --force --label run:<run_id> --title
<work_id> --description <brief> [--deps <upstream-ids>]` call per Work, in
dependency-first (topological) order, plus a separate `bd update`/`bd
close` call per Work reflecting current projected state -- the exact same
"direct CLI invocation, subprocess-per-operation" model the card
establishes elsewhere, applied to the primitives (`bd create --deps`, `bd
dep add`) that actually support this adapter's id/label discipline
(confirmed empirically: `bd create --id <explicit> --force --label
<label> --deps <other-explicit-id>` preserves both the id and the label,
and the dependency edge, correctly).

### `--id`/`bd`'s id charset (checked at implementation time, per the card)

The `<run_id>--<work_id>` `--` separator does **not** collide with any `bd`
id-charset rule -- confirmed empirically (`bd --json create --id
"run1--work1" --force ...` succeeds, id preserved verbatim). The one real
id-shape constraint `bd` enforces is a `prefix-suffix` structure (an id
with no hyphen at all, e.g. a bare run id with no work-id suffix, is
rejected outright as "invalid ID format", independent of `--force` -- this
is why this adapter never mirrors a bare run-level id; see "Lossy
mappings" below) and a database-prefix-match check that `--force` bypasses
(a `bd`-initialized database has its own configured issue prefix, e.g.
`sbx-`; an externally-supplied id like `<run_id>--<work_id>` will not
match it, so `--force` is REQUIRED on every `create` call, not optional).

### `--force` is mandatory on every `create`

Per the prefix-match finding above: `BeadsMirror._create_work` always
passes `--force`. Omitting it produces `Error: prefix mismatch: database
uses '<prefix>-' but ID '<id>' doesn't match` on every single call, since
this adapter's ids are never shaped like the target database's own
auto-generated ones.

### Label discipline: run and optional project namespaces on every `create`

Amended wording (PR #81 fix round; the card's original issue-#47 phrasing
said "on every invocation"): this adapter applies `--label run:<run_id>`
on every `bd create` call. When the optional `mirror.project` config value
is present, it also applies a separate `--label project:<name>` pair on
every create; `bd --label` accepts one value per flag, so these labels are
never comma-joined. Because every dispatch re-issues create as an upsert,
existing mirrored issues gain a newly configured project label on their
next dispatch without a separate backfill operation.

`update`/`close` calls do NOT re-pass either `--label` -- they address the
run-qualified unique `<run_id>--<work_id>` id directly, and `bd update`/`bd
close` do not strip or replace existing labels (verified against real `bd`
1.2.2: labels applied at create persist unchanged through `update
--status`/`--set-metadata` and `close --reason` calls), so both label
namespaces persist with create-time application alone. The card's bullet
carries the same amendment note.

### Workspace guard: `-C` walk-up containment (operator-DB safety)

`bd -C <dir>` does NOT confine itself to `<dir>`: when `<dir>` has no
`.beads` directory of its own, `bd` walks UP the directory tree and
operates on the nearest ancestor's `.beads` database (verified against
real `bd` 1.2.2 -- a `create` issued with `-C` pointing at a child
directory landed in the parent directory's database). For a write-only
mirror whose whole safety posture is "never touch a database the operator
did not explicitly configure", that walk-up is an operator-DB exposure: a
mistyped/not-yet-initialized `mirror.workspace` could silently write into
whatever `.beads` happens to exist above it (e.g. a repo checkout's own
real database).

Guard: before issuing ANY `bd` call, `BeadsMirror.project_run` checks
that `<workspace>/.beads` exists as a directory
(`BeadsMirror._workspace_owns_database`). If it does not, the ENTIRE
projection is treated as degraded -- one synthesized failed
`MirrorCallResult` explaining the guard, zero `bd` subprocesses spawned,
same non-fatal surfacing as any other degraded mirror (stderr note;
dispatch exit code/stdout untouched). A plain directory-existence check
is deliberately sufficient: this adapter's contract is "the operator
already ran `bd init` in `mirror.workspace`" (see `BeadsMirror`'s class
docstring), and `bd init` always creates `<workspace>/.beads`; the guard
fails closed on anything else rather than trying to reproduce `bd`'s own
discovery logic. Exercised by
`tests/conformance/test_beads_mirror_unit.py`'s `WorkspaceGuardTest`
(stub-level: zero invocations recorded) and the live sandbox test
`test_workspace_without_beads_never_writes_to_ancestor_database`
(`tests/conformance/test_beads_mirror_live_smoke.py`: a real ancestor
`.beads` database observably receives nothing).

### Idempotency: `bd create`/`update`/`close` are all safe to re-issue

Confirmed empirically (real `bd` 1.2.2, this task's recon): `bd create
--id <existing-id> ...` is itself an upsert -- re-creating an existing id
updates title/description/labels in place (`updated_at` advances,
`created_at` does not) rather than erroring or duplicating the issue.
`bd update <id> ...` and `bd close <id> --reason accepted` both succeed
(exit 0) when re-issued against an issue already in the target
state/already closed. This is what lets `BeadsMirror.project_run` always
re-sync FULL current state on every call rather than tracking "what did I
already write" -- the same "always re-derive, never trust in-process
memory as the correctness path" discipline `docs/adapters/git/mapping.md`'s
"Idempotency behavior" already establishes for its own reads (`GitDiffCandidate`
re-reads real git state on every call rather than caching identity), applied
here to writes instead of reads.

### Plan-validation pre-flight

`project_run` calls `orc_werk.ports.work_graph.validate_plan` on the
extracted plan before issuing any `bd` call at all -- mirroring
`PORT-WORK-001`'s own pre-flight discipline, per the task card. Unlike
every `bd`-call failure (see "Degraded mirror" below), a `validate_plan`
failure is **not** caught -- a plan that reaches this point already
malformed is a real upstream bug (the orchestrator validates the identical
plan before `project_run` is ever called), not a `bd`-side degradation.

### Never reaches past the CLI into Dolt

`bd`'s underlying storage (Dolt) is never touched directly -- the adapter
boundary is the `bd` CLI surface only, per `INV-014`.

## Operation mapping

| Canonical concept | `bd` operation | Mapping |
|---|---|---|
| Work created (`FACT-WORK-CREATED`, read from the durable `FX-CREATE-WORK` effect record's `data.plan`) | `bd create --id <run_id>--<work_id> --force --label run:<run_id> [--label project:<name>] --title <work_id> --description <brief> [--deps <upstream ids, comma-joined>]` | One call per Work, dependency-first (topological) order so every `--deps` reference already exists. The project label is included when `mirror.project` is configured. |
| Per-work brief (`briefs[work_id]`, CLI-owned config, falls back to the run's intent text) | `--description` at `create` | The first durable owner of multi-work briefs (see "Durability" below). |
| Kernel state -> `bd` status/metadata | `bd update <id> [--status <status>] --set-metadata state=<lower(state)> --set-metadata attempt_number=<n> [--set-metadata claim_ref=<ref>] [--set-metadata blocked_reason=<reason>]` | See the status-vocabulary table below. |
| `DEC-ACCEPT`/`FACT-WORK-COMPLETED` (state `ACCEPTED`) | `bd update <id> --set-metadata ...` then `bd close <id> --reason accepted` | Two calls: metadata first (`close` accepts no `--set-metadata` flag), then the close itself -- a write-only echo, never a trigger. |
| `DEC-BLOCK`/`FACT-WORK-BLOCKED` (state `BLOCKED`) | `bd update <id> --status blocked --set-metadata blocked_reason=<reason> ...` | `bd`'s own builtin `blocked` status (`bd statuses`) is an exact-name match -- no synthesized status needed. Write-only echo, never a trigger; `close` is never called for a blocked Work. |

Mirror reference resolution uses `bd list --status all` because `bd list` defaults to open/in-progress issues and would otherwise hide accepted runs whose issues the mirror closes.

## Status vocabulary (kernel state -> `bd`)

| Kernel state (`docs/domain/state-machines/delivery.md`) | `bd` builtin status | `--set-metadata state=` | Notes |
|---|---|---|---|
| `READY` | `open` | `ready` | Default state; `bd`'s own default status on `create` already matches, this adapter still issues the explicit `update` for the metadata fields (`attempt_number`, `claim_ref` when set). |
| `EXECUTING` | `in_progress` | `executing` | `bd`'s coarse status vocabulary does not distinguish `EXECUTING` from `ASSURING` (both are `bd`'s own "wip" category, `bd statuses`) -- the `--set-metadata state=` field is what carries the exact kernel state a human/portfolio surface can filter on. |
| `ASSURING` | `in_progress` | `assuring` | See above. |
| `BLOCKED` | `blocked` | `blocked` | Plus `blocked_reason=<value>` when the kernel recorded one (e.g. `retry-budget-exhausted`). |
| `ACCEPTED` | `closed` (via `bd close --reason accepted`, not `--status`) | `accepted` | The metadata `update` call runs first, then `close`. |

`claim_ref`, when the kernel has recorded one (`WorkProjection.claim_ref`
-- persists across all retry attempts within one Work lineage, per the
state machine's "claim recording" mechanical rule; it does not itself
transition state), is always mirrored as `--set-metadata
claim_ref=<value>` alongside whatever status/other metadata the current
state produces -- this is the adapter's answer to the task card's "ready,
**claimed**, executing, assuring, blocked, accepted" phrasing: `claimed`
is not a `bd` status of its own, it is an overlay metadata field on top of
whichever status the Work's actual kernel state currently maps to (the
kernel's own mechanical sequencing rule already treats claim the same
way -- an attribute of `READY`, not a state of its own).

## Durability: briefs become durable for the first time (PR #49 ruling)

`docs/contracts/durability-responsibilities.md`'s "Delegated work
specification -- multi-work brief" row records: "Until such an adapter
exists, multi-work briefs are deliberately NOT durable". `BeadsMirror` is
that adapter, once an operator actually configures `mirror` + supplies
`briefs` in the CLI dispatch config (`src/orc_werk/cli/config.py`'s
"Beads mirror" docstring section). This contract amendment is recorded in
`docs/contracts/durability-responsibilities.md` alongside this task's
landing (see that document's own updated row and Rozoro-ledger row).

**Brief-fallback note, honestly recorded**: `PORT-WORK-001`'s canonical
plan shape carries no brief/description field at all (`work_id`/`deps`
only) -- core is untouched by this task (`CLAUDE.md` rule 8/9). `briefs`
is therefore a CLI-owned, non-canonical sibling key to `plan`
(`src/orc_werk/cli/config.py`), keyed by `work_id`. A Work with no entry
in `briefs` falls back to the run's own intent text as its `bd`
description -- never a fabricated or empty description when honest
fallback text is available, but also never a claim that every Work's
description is a genuinely per-work brief: an operator who never supplies
`briefs` gets every Work's description set to the same run-level intent
text, which is exactly the status quo `CONTRACT-DURABILITY`'s row already
describes ("operators who need durable multi-work briefs today should
carry the essentials in the run-level intent text") -- this adapter makes
that existing practice durable in `bd`, and additionally durable makes a
genuinely distinct per-work brief when the config actually supplies one.

## Degraded mirror (non-fatal, by design)

Mirror failures MUST NEVER break the delivery loop (task card). Every
`bd` subprocess invocation's outcome is recorded in a `MirrorCallResult`;
`BeadsMirror.project_run` never raises on a `bd`-call failure (only a
plan-validation failure, a genuine upstream bug, is allowed to raise --
see "Plan-validation pre-flight" above) and always returns a
`MirrorReport` whose `.degraded`/`.errors` record which calls failed. A
failed call does not stop subsequent calls in the same `project_run` --
this is a best-effort desired-state sync, not a transaction.

**Surfacing choice (this adapter's call, recorded per the task card):** a
degraded mirror is reported to **stderr only**, by `orc_werk.cli.main.
cmd_dispatch` -- one summary line (`mirror: degraded (N of M bd call(s)
failed) ...`) plus one detail line per failed call (the exact `bd`
argv and its stderr). It is deliberately **not** written to the journal as
an extension. Two alternatives were considered and rejected:

- **A journal extension** would durably record `bd`'s own error text
  inside the canonical journal -- a provider-vocabulary leak past the
  `INV-014` quarantine this whole adapter exists to respect, and it risks
  a future maintainer being tempted to read that extension back to drive
  a decision, exactly the write-only boundary this task must not blur.
- **A non-zero/altered CLI exit code** would make a degraded mirror
  indistinguishable from a genuine dispatch problem, directly violating
  "mirror failures MUST NEVER break the delivery loop" -- proven at the
  CLI boundary by `tests/scenarios/test_cli_beads_mirror_wiring.py`'s
  `test_degraded_mirror_never_changes_exit_code_or_stdout`.

`stdout` (the canonical `orc dispatch` state/next-block output) is never
touched by a degraded mirror; only stderr gains the note.

## Sandbox/testing notes

- **Unit tests** (`tests/conformance/test_beads_mirror_unit.py`) use a
  small self-contained stub-`bd` Python script (`tests/conformance/
  support_beads_stub.py`), passed directly as `BeadsMirror(bd_bin=<path>)`
  -- no real `bd`/Dolt dependency. Since `BeadsMirror` never parses `bd`'s
  stdout (write-only), the stub only needs to record each invocation's
  argv and optionally fail on command; it does not simulate `bd`'s actual
  JSON response shapes at all.
- **One live sandbox smoke test**
  (`tests/conformance/test_beads_mirror_live_smoke.py`) runs against a
  REAL `bd` 1.2.2 install, `unittest.skipUnless(shutil.which("bd"), ...)`-
  gated -- skipped in `ci-required` (no `bd` on the `ubuntu-latest`
  runner), runs wherever `bd` is actually installed. It provisions its own
  disposable `bd init`-ed workspace under a fresh temp directory and tears
  it down afterward; it NEVER touches any operator-configured `bd`
  database. This task's own recon used exactly this pattern, manually,
  against `/opt/homebrew/bin/bd` in a scratch sandbox directory -- never
  against any pre-existing database.
- Neither test suite ever mutates a real, shared, operator-visible `bd`
  database -- the shared-DB posture this adapter is DESIGNED for
  (label-scoped isolation, issue #47) is an operational/deployment
  concern, not something either test suite provisions itself.

## Lossy mappings

- **No run-level parent/epic bead.** A single bead grouping every Work
  under one run-level parent (via `bd`'s `--parent`/hierarchical
  children) was considered -- it would improve the "one place to see
  run/work state" portfolio view the ratified posture describes. Dropped:
  `--parent` and `--id` are mutually exclusive (see "`--graph` was
  evaluated and rejected" above), and the deterministic-id requirement is
  non-negotiable while a run-level hierarchy bead is not required by this
  card's acceptance criteria (which only ever names `<run_id>--<work_id>`
  ids). Grouping instead has two granularities: `run:<run_id>` selects one
  delivery run, while optional `project:<name>` selects all mirrored work
  for a configured project across runs -- consistent with the ratified
  posture's own framing ("shared, label-scoped `bd` database").
- **`claimed` is metadata, not a `bd` status.** See "Status vocabulary"
  above.
- **No line-level/structured content beyond title+description+labels+
  metadata.** This adapter never attaches comments, attachments, or
  `bd`'s richer relationship types (`tracks`, `discovered-from`, etc.) --
  only `blocks` dependency edges (the one v0 `PORT-WORK-001` dependency
  condition, `accepted`) and the status/metadata vocabulary above.
- **No claim/block origination.** `bd`'s own `claim`/`update --status
  blocked` verbs are never called by a human/other tool through this
  adapter's own API -- this adapter only ever WRITES a projection; a human
  editing the mirrored `bd` issue directly (e.g. manually closing it) has
  no effect on the kernel, and the next `project_run` call will simply
  overwrite that manual edit with the kernel's own current truth (a
  further structural proof of the write-only boundary, not a bug).

## Canonical error translation

`BeadsMirror` is write-only and never raises a canonical `ERR-*` error
from a `bd`-call failure at all (see "Degraded mirror" above) -- there is
no canonical error translation table here the way `docs/adapters/git/
mapping.md`'s "Error translation" or `docs/adapters/command/mapping.md`'s
"Canonical error translation" have one, because this adapter has no `PORT-EXECUTION`/
`PORT-ASSURANCE`/`PORT-WORK-GRAPH` conformance obligation whose contract
requires one. Every `bd`-call failure (non-zero exit, missing binary,
timeout, bad workspace) is uniformly recorded as `MirrorCallResult(ok=
False, ...)` and surfaced per "Degraded mirror" above -- there is exactly
one failure shape at this adapter's boundary, not a taxonomy of canonical
error ids.

## Idempotency behavior

See "Idempotency: `bd create`/`update`/`close` are all safe to re-issue"
above -- every `project_run` call is a full, idempotent, best-effort
re-sync of current journal-derived state, safe to call any number of
times (including a redundant re-poll of an already-fully-mirrored,
fully-terminal run) without erroring or duplicating `bd` state.

## Capability honesty

`BeadsMirror` advertises no `CAP-WORK-*` capability at all (it has no
`capabilities()` method -- it is not a `WorkGraphPort` implementation).
See `docs/adapters/beads/capabilities.md`.

## Related

- `docs/delivery/task-cards/TASK-M2-006-beads-mirror.md`
- `docs/adapters/README.md`
- `docs/adapters/git/mapping.md`
- `docs/adapters/command/mapping.md`
- `docs/contracts/durability-responsibilities.md`
- `docs/contracts/invariants.md` (`INV-014`, `INV-015`, `INV-020`)
- `docs/domain/state-machines/delivery.md`
