---
id: TASK-M2-006
type: task-card
status: current
authority: normative
description: Write-only Beads mirror — a live projection of run/work state and briefs into bd issues, per the ratified issue #47 posture (shared label-scoped DB, kernel authoritative, mirror mode first). Authority graduation is explicitly out of scope and stays dormant.
implements: []
verifies: []
---

# TASK-M2-006 — Beads mirror (write-only projection)

## Outcome

**Pulled into M2 scope (operator ruling, M2 reshape, 2026-08-28).** Ship a
write-only Beads mirror per the posture the operator ratified on issue #47
(2026-08-28): a **shared, label-scoped** `bd` database that receives a live
projection of run/work state and per-work briefs, while `MemoryWorkGraph` +
the journal remain the sole authority for `PORT-WORK-GRAPH` semantics
(readiness, claim, dependency-unlock, acceptance). Nothing this adapter
writes is ever read back to drive a dispatch decision — the mirror exists
so a human (or a future portfolio surface) has one place to see run/work
state and briefs across runs, not to replace the kernel's own authority.

This card's design source is issue #47's implementation-shape consensus
and mirror-first phasing, in full — the executing agent inherits a
complete design, not an open debate:

- **Direct CLI invocations, subprocess-per-operation**: `bd --json <verb>`,
  matching the established acp-adapter pattern (`docs/adapters/acp/
  mapping.md`'s "Poll model"/subprocess conventions). Beads is the easier
  instance of this pattern — no daemon, no streams, synchronous ops.
- **Explicit, deterministic, replay-stable ids**: `--id <run_id>--<work_id>`
  on every `bd create` (`bd`'s own generated ids are random and would
  violate `INV-020`'s replay-stable naming if left to default; the
  separator is checked against `bd`'s id charset at implementation time,
  per the issue thread).
- **`--label run:<run_id>`** on every invocation — the shared-DB label
  discipline the ratified posture depends on for isolation between runs
  sharing one `bd` database.
- **Briefs → issue descriptions at `bd create`** — per the PR #49
  adapter-owned-briefs ruling (`docs/contracts/durability-
  responsibilities.md`'s multi-work-brief row): this adapter is where
  multi-work briefs first become durable, once it exists. Until this card
  ships, that row's "until such an adapter exists, briefs are deliberately
  NOT durable" disposition stands unchanged.
- **`bd close --reason accepted`** issued as a mirror of the kernel's own
  `DEC-ACCEPT`/`FACT-WORK-COMPLETED` — a write-only echo, never a trigger.
  Block state is projected via `bd` metadata (label/field, decided at
  implementation time), also write-only.
- **`bd create --graph`** issued after this adapter's own plan-validation
  pre-flight (mirroring `PORT-WORK-001`'s `validate_plan` discipline before
  any external write).
- **Never reach past the CLI into Dolt** (`bd`'s underlying storage) — the
  adapter boundary is the `bd` CLI surface only, matching `INV-014`'s
  provider-vocabulary quarantine.

## Slice boundary — mirror only; authority graduation is OUT

**Explicitly out of scope, and deliberately so: `bd` becoming the live
authority for `PORT-WORK-GRAPH`** (bd-native ready/claim/dependency logic
driving real dispatch decisions). That graduation path is fully designed
and **recorded, dormant, on issue #47** — this card does not resolve or
schedule it:

- the forgery-surface analysis for an out-of-band `bd close` acting as
  acceptance (`INV-003`);
- the mitigation kit if graduation is ever pulled: defensive
  ready-verification cross-checking every unlock against journal-derived
  acceptance (mismatch → `ERR-UNSAFE-STATE` at dispatch), and the slice-2
  hardening spike question (can `bd`'s ready/dependency logic key off a
  custom `accepted` status distinct from `closed`, turning the fence into
  mechanism rather than convention);
- the two-runs-one-db leakage conformance test proving `--label` discipline
  under `INV-015` — relevant once `bd` state can influence dispatch
  eligibility; not applicable to a write-only mirror, which never feeds
  eligibility decisions.

Per `PLAYBOOK-WATCHTOWER`'s dormant-feature lifecycle, this graduation
path's pull trigger is unchanged from the operator's ratification: pulled
only if the mirror view earns it — "M2c-adjacent at the earliest, or
whenever a cross-run portfolio/briefs surface is actually wanted." This
card's own scope stops at the mirror; graduation is a separate, future
card if and when that trigger fires.

## In scope

- adapter implementation under `src/orc_werk/adapters/beads/` — a
  write-only observer, not a `PORT-WORK-GRAPH` implementation (this card
  does not claim `PORT-WORK-GRAPH` conformance; the mirror is a projection
  consumer of journal-derived state, not a provider of the port);
- the `bd --json` subprocess-per-operation invocation model above
  (create/snapshot/ready/complete projection, per the issue's slice-1
  scope), including `--id`/`--label` discipline;
- projecting per-work briefs into `bd` issue descriptions at creation (the
  first durable owner of multi-work briefs, per PR #49);
- projecting run/work status transitions (ready, claimed, executing,
  assuring, blocked, accepted) into `bd`'s own status/label vocabulary,
  write-only;
- `bd close --reason accepted` mirroring `DEC-ACCEPT`, and block-reason
  metadata mirroring `DEC-BLOCK` — both write-only echoes;
- mapping doc: `docs/adapters/beads/mapping.md` (bd vocabulary quarantined
  here and in the adapter, never in `docs/contracts/` or `src/orc_werk/
  core`, per `INV-014`);
- version pin recorded in the mapping doc (`1.2.2` at recon; an
  adapter-local dependency, matching the `acp`/Node precedent — no
  `src/orc_werk/core` impact, `CLAUDE.md` rule 8 unaffected);
- testing: a stub-`bd` `PATH` fake driving the existing `CONF-WORK-001`
  through `CONF-WORK-004` suite's applicable cases, plus one live sandbox
  smoke test against a real `bd` install.

## Out of scope

Authority graduation in full (see "Slice boundary" above) — bd-native
ready/claim/dependency-driven dispatch logic, the ready-verification
tripwire, the custom-status hardening spike, and the two-runs-one-db
leakage conformance test all stay dormant on issue #47, not built here;
`claim`/`block` as `bd`-authoritative operations (mirror only echoes
status, never originates a claim or block decision); any change to
`PORT-WORK-GRAPH` itself (this card consumes journal-derived state, it
does not amend the port).

## Depends on

No M2-internal dependency to start (mirrors independently of
`TASK-M2-001`/`002`/`003`/`005`). `TASK-M2-003` (the real-DAG practice
run) and `TASK-M2-004` (second-repo adoption) both benefit from — and
`TASK-M2-004` is explicitly gated on — this card landing first, so it is
sequenced early among the M2 cards that remain in scope.

## Acceptance

- a real multi-work run's topology and briefs are visible in the shared
  `bd` database, correctly `--label`-scoped, with replay-stable
  `<run_id>--<work_id>` ids;
- `bd close --reason accepted` and block metadata correctly mirror the
  journal's own `DEC-ACCEPT`/`DEC-BLOCK` outcomes, write-only (no `bd`
  state ever feeds back into a dispatch decision);
- the stub-`bd` `PATH` fake drives the applicable `CONF-WORK-001` through
  `CONF-WORK-004` suite cases green, plus one live sandbox smoke test
  passes;
- `docs/adapters/beads/mapping.md`, `capabilities.md`, and
  `conformance.md` are updated from `draft` placeholders to reflect this
  slice's actual, verified mapping (not left as unverified "TBD" rows);
- authority graduation remains unbuilt and undisturbed on issue #47 —
  dormant, with its pull trigger unchanged.
