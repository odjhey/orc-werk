---
id: M-002
type: milestone
status: current
authority: normative
description: Third milestone (reshaped per operator review) — the no-mistakes assurance seat, a write-only Beads mirror, and a real multi-work DAG practice run close the loop, then a gated second-repo demo leaves home. Second-agent provider swap and policy parameterization are deferred out of M2.
---

# M2 — Close the loop

## Goal (reshaped — operator ruling, M2 reshape, 2026-08-28)

M1 made orc-werk its own first user: a real, operator-driven delivery ledger,
then a real execution adapter (`acpx` driving Pi) with the operator still
seated as the assurance/verdict authority for every candidate. M2, following
an operator review of the original draft below, now ships as: **the
no-mistakes assurance seat + the Beads mirror + a real multi-work DAG
practice run, closing with a gated second-repo demo.**

- **Closes itself**: the verdict seat stops being a human typing a
  recorded outcome and becomes a real `PORT-ASSURANCE` provider
  (`no-mistakes`, `TASK-M2-001`), so a delivery can run start-to-finish —
  execution *and* assurance — without an operator manually recording
  either side. See `TASK-M2-001`'s UX sketch for the operator-reviewed
  dispatch → execute → assure → verdict flow.
- **Gains a portfolio view**: a write-only Beads mirror (`TASK-M2-006`,
  pulled into M2 per the ratified issue #47 posture) projects run/work
  state and briefs into a shared, label-scoped `bd` database — the kernel
  journal remains the sole `PORT-WORK-GRAPH` authority; the mirror is
  observation surface only, not a second source of truth.
- **Practices, and harvests**: a real multi-work DAG is driven through the
  acp adapter with real agents in the seats (`TASK-M2-003`, reframed as a
  practice run) — its point is to exercise and populate the Beads mirror
  and the dependency-tree report view, and to harvest real per-work cost
  and config-demand findings, not to build new capability.
- **Leaves home, last, and gated**: orc-werk is put to work as the ledger
  for a second, independent repo (`TASK-M2-004`) — the first real test of
  `PRODUCT-ADOPTION`'s adoption ladder from outside the project that built
  it — but only once the automatic verdict seat and the portfolio view
  already exist, so the demo shows the loop actually closed rather than an
  operator still filling gaps by hand.

**Deferred out of M2** (see "Deferred (M2 reshape)" below): the second-agent
provider-swap proof (`TASK-M2-002`, `acpx claude`) and policy
parameterization (`TASK-M2-005`). `P-001` (providers as policy) does not get
its second cross-provider proof in this milestone; `acpx pi` alone continues
to carry that evidence until the deferred card's trigger fires.

## Prerequisite — issue #57 (re-poll duplicate prompt)

**Named M2 prerequisite, gating real-agent dogfooding.** Issue #57 (`acp:
re-poll resubmits the prompt`) found that `AcpExecution.start()`'s
idempotency cache is in-process only, so every ordinary poll of an
in-flight real attempt across a fresh `orc dispatch` process resubmits a
duplicate prompt to the agent — duplicated model spend and session noise on
every poll. This is not a theoretical gate: it directly costs real spend on
exactly the real-`acpx`-adapter dogfooding M2's phases below depend on
(`TASK-M2-003`'s practice run, `TASK-M2-001`'s real-candidate assurance
runs, and the cost-harvesting purpose both share). Issue #57 lands
**before or with** M2's execution work — it is not scheduled as a separate
card here because it is a fix to already-shipped M1b adapter behavior, but
no M2 phase that dispatches real, multi-poll `acpx` attempts should proceed
against an un-fixed `start()`.

### Scope note — Rozoro is explicitly deferred

Per the issue #12 watchtower assessment and the subsequent operator ruling
recorded on that issue (2026-08-28, post-M1a+): **the Rozoro migration/split
track is deferred — no Rozoro-replacement milestone is drafted here.**
`execution-session/v1`, `crew-report/v1`, the durability contract, and the
capability-durability rule (all delivered in M1, per that same ruling) are
unaffected and already stand on their own. `docs/contracts/durability-
responsibilities.md`'s retirement ledger and migration-closure rule remain
in place, gating only the eventual migration milestone whenever it is
scheduled — M2 does not schedule it.

## Phase M2a — No-mistakes AssurancePort

Automates the verdict seat (`TASK-M2-001`).

- A real `PORT-ASSURANCE` adapter backed by `no-mistakes` (the operator's
  existing production review/gate driver) replaces the operator as the
  assurance recorder for candidates it is configured to review.
  `review-findings/v1` (`EXT-REVIEW-FINDINGS-V1`, already registered) is
  the structured findings channel the adapter returns via
  `CAP-ASSURE-STRUCTURED-FINDINGS` — no new extension schema, this
  milestone is the first real producer of an already-registered one. See
  `TASK-M2-001`'s UX sketch for the full dispatch → execute → assure →
  verdict flow, including the `evidence_refs`/`review-findings/v1` shape.
- A `CONF-ASSURE-*` conformance run (`CONF-ASSURE-001` through
  `CONF-ASSURE-004`, `docs/conformance/README.md`) against the real adapter, the same
  bar every scripted/real `PORT-ASSURANCE` implementation already meets —
  no relaxation for being real.

**Deferred out of this phase (M2 reshape): the second cross-provider proof
of `P-001`** (`acpx claude` through the same adapter, zero code change) —
see "Deferred (M2 reshape)" below. M2a no longer includes it; `TASK-M2-001`
is the whole of this phase.

## Phase M2a+ — Beads mirror (write-only projection)

Pulled into M2 (operator ruling, M2 reshape): a write-only Beads mirror
(`TASK-M2-006`), per the posture the operator ratified on issue #47
(shared, label-scoped `bd` database; `MemoryWorkGraph` + journal stay
`PORT-WORK-GRAPH`-authoritative; `bd` receives a live projection of run/work
state and briefs; mirror mode first, authority graduation dormant until the
view earns it).

- Direct `bd --json` CLI subprocess invocations, matching the acp adapter's
  established subprocess pattern — no daemon, synchronous ops.
- Deterministic `--id <run_id>--<work_id>` (replay-stable per `INV-020`;
  `bd`'s own generated ids are random) and `--label run:<run_id>` on every
  `bd create` (the shared-DB isolation discipline the ratified posture
  depends on; `update`/`close` address the run-qualified unique id and
  labels persist -- amended at implementation time, PR #81 fix round, see
  the task card and `docs/adapters/beads/mapping.md`).
- Briefs become durable for the first time in a multi-work run (via `bd`
  issue descriptions at create), resolving — for adopters of this adapter
  — the "multi-work briefs are deliberately NOT durable" disposition
  recorded in `docs/contracts/durability-responsibilities.md`'s ownership
  matrix, without requiring a core/journal change.
- Authority graduation (bd-native ready/claim/dependency logic driving real
  dispatch decisions) is explicitly **out of scope and stays dormant** on
  issue #47, with its full mitigation kit (ready-verification tripwire,
  custom-status hardening spike, two-runs-one-db leakage conformance test)
  pre-recorded there for whenever the pull trigger fires.

Sequenced before Phase M2b and Phase M2c below: both benefit from — and
`TASK-M2-004` is explicitly gated on — this phase landing first.

## Phase M2b — Multi-work real DAGs (practice run)

**Reframed (operator ruling, M2 reshape): this phase is a practice run,
not a build.** M1b proved one real Work through the acp adapter. M2b now
drives one real, dependent multi-work plan through it with real agents in
the seats (`TASK-M2-003`) — the same diamond/fan-in/fan-out shape
`SCN-003`/DFS-003 already prove for scripted providers — and treats the run
as an instrument: little new capability is built, the goal is to exercise
and harvest.

- Real, dependent deliveries dispatched through the `acpx` `PORT-EXECUTION`
  adapter, not scripted providers — multiple Works with `deps`, driven to
  completion by real agent turns in the ship/verification seats
  (`PLAYBOOK-AGENT-CLI`).
- **Exercises and populates the Beads mirror** (Phase M2a+) with this run's
  real topology and briefs — the mirror's first real multi-work data.
- Issue #41 (report dependency-tree view for multi-work runs) is exercised
  against this real topology: it was explicitly gated on topology being
  journal-reconstructable, which a real multi-work acp-driven run is the
  first opportunity to prove end-to-end (plan shape + real per-work journal
  history, not a synthetic fixture) — the renderer itself is not new work
  in this phase, only its first real exercise.
- **Harvests findings, not features**: per-work cost data and per-work
  config-demand evidence — the exact evidence `TASK-M2-005` (deferred, see
  below) is gated on — plus any topology/report/mirror gaps found, recorded
  as docs amendments or filed issues per `DELIVERY-STANCE`.

## Phase M2c — orc as ledger for another repo (gated, sequenced last)

The first true adoption test: point a real, independent repository's
delivery work at an orc-werk ledger, with no changes to orc-werk's own
core semantics.

**Gated (operator ruling, M2 reshape): sequenced last, after Phase M2a**
(`TASK-M2-001`, the automatic verdict seat) **and Phase M2a+**
(`TASK-M2-006`, the Beads mirror/portfolio view) **both land.** The demo is
only compelling with both in place — a second-repo delivery running under
an operator still typing verdicts by hand, with no portfolio view to show
for it, undersells what M2 otherwise delivers.

- Pressure-tests `PRODUCT-ADOPTION`: does the adoption ladder actually
  hold for an outside repo, or does it quietly assume orc-werk-repo-shaped
  conventions (this repo's task-card format, its worktree layout, its own
  `AGENTS.md`) that a second repo does not share?
- No new contract is anticipated from this phase by default; if the
  pressure test finds a genuine gap, that gap gets a docs amendment first,
  per `CLAUDE.md` rule 4 — this phase's job is to find gaps, not to
  pre-guess them.

## Phase M2d — Policy parameterization v1 (deferred out of M2)

**Deferred (operator ruling, M2 reshape, 2026-08-28) — removed from M2
scope.** See "Deferred (M2 reshape)" below for the pull trigger (unchanged
from the Gate described in this phase). The design below is recorded
as-is for whenever the gate fires; it is not scheduled in this milestone.

Operator-prompted, watchtower-approved addition. Scope, deliberately
narrow — and narrower still than first proposed, per an operator ruling
grounded in direct production experience (Temporal retry-bug history,
below):

- **(a) Per-work `max_attempts`.** Today's retry budget is one policy
  default applied uniformly (`docs/domain/state-machines/delivery.md`:
  "`max_attempts = 3` is the v0 default policy budget"). A DAG's works
  should not be forced to share one budget — a cheap, low-risk Work and an
  expensive, real-agent-executed Work in the same plan have no reason to
  exhaust retries at the same count. This pairs directly with M2b's real
  DAGs, where the cost asymmetry first becomes real rather than
  hypothetical.
- **(b) A single, kernel-checkable no-retry exception — narrowly scoped,
  conditional.** The *default* policy remains cause-blind-but-bounded,
  permanently: retry-to-budget always, for every failure cause, is not a
  gap to be closed. Bounded budgets plus root-cause-visible `BLOCKED`
  (issue #16's fix, already shipped in M1 — `blocked_reason=
  retry-budget-exhausted (root_cause=...)`) already contain the
  unclassified-permanent-failure mode: a doomed attempt burns bounded
  budget, then blocks with the cause visible, which is a correct and
  legible terminal outcome on its own. Retry-cause classification systems
  introduce their own bug class — misclassification — and the operator's
  own production experience with Temporal is the concrete cautionary
  precedent: unraised/mis-marked non-retryable exceptions there caused
  real retry bugs (permanently-failing work silently never retried, or
  the inverse). Orc-werk does not adopt that risk speculatively.

  **If** observed cost data justifies a no-retry path at all (see Gate,
  below), its scope is restricted to exactly **one** static cause:
  `ERR-UNSUPPORTED-CAPABILITY` at dispatch. This is the sole
  kernel-checkable case — `INV-013`'s capability set is fixed and known
  before the first attempt, so "this Work's configured capability
  requirement cannot be met by this provider" is a decidable theorem the
  kernel itself can verify, not a judgment call an adapter reports about
  its own execution. **`ERR-PERMANENT` (adapter-classified) is explicitly
  out of scope** — an adapter asserting "this failure is not retryable" is
  exactly the unverifiable, misclassification-prone judgment the Temporal
  precedent warns against, and it is not on the table for this milestone
  regardless of what cost data shows.

**Explicit docs-first prerequisite for (b), if triggered:** policy is
currently cause-blind by construction. The reducer folds Facts, and
`FACT-EXEC-SETTLED` carries `outcome` only (`docs/protocol/facts.md`); the
canonical error class lives in the corresponding effect record's
`dispatch_result` (`docs/contracts/ports/journal-port.md`), which never
enters Work state and is therefore invisible to the retry/`DEC-RETRY`/
`DEC-BLOCK` decision logic. Even this narrow, kernel-checkable version
requires a contract decision first — most likely an optional `cause` field
on `FACT-EXEC-SETTLED` scoped to carry only the fixed
`ERR-UNSUPPORTED-CAPABILITY` signal, not an open-ended error-class enum —
and it amends both `SCN-006` (max-attempts extremes) and
`STATE-DELIVERY`'s budget-exhaustion transition-table path
(`docs/domain/state-machines/delivery.md`). This is a protocol change and
gets full docs-first treatment (amended fact shape, amended scenario,
invariant check) before any implementation, per `CLAUDE.md` rules 3–5.
This milestone records the prerequisite; it does not resolve it in advance
of that docs work, and does not pre-commit to (b) shipping at all.

**Gate:** this whole item is gated on observed cost data from the first
real `acpx`-adapter runs (M1b/M2a/M2b) — per `DELIVERY-STANCE`, dogfooding
demand drives scope, not speculation about what policy might someday need.
(a) is gated on DAG-wide budget-starvation evidence; the narrow (b) is
gated on evidence of real spend wasted specifically on statically-doomed
`ERR-UNSUPPORTED-CAPABILITY` retries. If real usage does not show either,
(a) and/or (b) may be deferred past M2 without being a milestone miss —
and (b) may simply never ship if the default cause-blind-but-bounded
policy continues to be sufficient, which is the expected steady state, not
a fallback.

**Explicitly out of scope for M2d** (reserved for the M3+ "who decides"
horizon, or ruled out entirely): policy profiles, any `PolicyPort`/
pluggable policy abstraction, LLM-as-policy, a policy DSL, and — ruled out
for this milestone specifically, not merely deferred — any
adapter-classified `ERR-PERMANENT` retry-skipping. M2d is at most two
narrow, contract-first parameters, not a policy framework, and its retry-
skipping surface is a single decidable theorem, not a classifier.

## Deferred (M2 reshape)

Operator ruling, M2 reshape, 2026-08-28 — consciously deferred, not
implicit, per `PLAYBOOK-WATCHTOWER`'s deferred-decision-ledger discipline.
Each entry's task card records the same trigger inline:

| Deferred item | Card | Pull trigger |
|---|---|---|
| Second-agent provider-swap proof (`acpx claude`, zero adapter code change) | `TASK-M2-002` | Provider-diversity proof wanted, or the first Pi-capability gap encountered. |
| Policy parameterization v1 — per-work `max_attempts` (a) and the narrow `ERR-UNSUPPORTED-CAPABILITY` no-retry exception (b) | `TASK-M2-005` | Observed cost data from real `acpx`-adapter runs: (a) DAG-wide budget-starvation evidence; (b) evidence of real spend wasted specifically on statically-doomed `ERR-UNSUPPORTED-CAPABILITY` retries. Phase M2b's practice run (`TASK-M2-003`) is this milestone's most direct source of that evidence. |

Unchanged from the original draft: Rozoro migration/split remains deferred
per the issue #12 operator ruling (see the scope note above) — that
deferral predates and is independent of this reshape.

## Required contracts

- `PORT-ASSURANCE` (no amendment expected — first real non-scripted
  implementation; conformance-only unless M2a's implementation surfaces a
  genuine gap)
- `CONTRACT-EXTENSIONS` / `EXT-REVIEW-FINDINGS-V1` (consumed, not amended)
- `PRODUCT-ADOPTION` (pressure-tested by M2c; amended only if a real gap is
  found)

`P-001`'s second cross-provider proof and `docs/domain/state-machines/
delivery.md`/`SCN-006`'s conditional amendments (M2d's narrow (b)) are
deferred along with their owning cards (see "Deferred (M2 reshape)" above)
— not required contracts for this milestone as reshaped.

## Required scenarios

- `CONF-ASSURE-001` through `CONF-ASSURE-004` re-run against the
  `no-mistakes` `PORT-ASSURANCE` adapter (M2a)
- A new multi-work golden scenario or dogfood corpus entry exercising a
  real DAG through the acp adapter, driven by real agents (M2b practice
  run) — exact form (golden `SCN-*` vs. `DFS-*`) decided at `TASK-M2-003`
  dispatch
- `SCN-001` through `SCN-007` continue to pass unmodified (regression bar)

The `SCN-006`/`DFS-007` amendment tied to M2d's narrow (b) is deferred
along with `TASK-M2-005` (see "Deferred (M2 reshape)" above).

## Required implementation

- `no-mistakes`-backed `PORT-ASSURANCE` adapter (`TASK-M2-001`)
- write-only Beads mirror — run/work state and briefs projected into a
  shared, label-scoped `bd` database, authority graduation dormant
  (`TASK-M2-006`)
- real multi-work DAG practice run through the acp adapter, with real
  agents in the seats; dependency-tree view in `orc report` (issue #41)
  exercised against real topology (`TASK-M2-003`)
- a second repo configured to use orc-werk as its delivery ledger, gated on
  `TASK-M2-001` and `TASK-M2-006` landing first (`TASK-M2-004`)

`acpx claude` (`TASK-M2-002`) and policy parameterization (`TASK-M2-005`)
are deferred out of M2's required implementation (see "Deferred (M2
reshape)" above).

## Acceptance

- **M2a:** a real delivery's candidate is assured by the `no-mistakes`
  adapter with `review-findings/v1` findings and passes `CONF-ASSURE-001`
  through `-004`.
- **M2a+ (Beads mirror):** a real multi-work run's topology and briefs are
  visible in the shared, label-scoped `bd` database, write-only — no `bd`
  state ever feeds back into a dispatch decision; authority graduation
  remains unbuilt and dormant on issue #47.
- **M2b (practice run):** a real multi-work DAG (at minimum a fan-in shape
  matching DFS-003's topology), driven by real ship/verification agents,
  is driven to terminal state through the acp adapter; `orc report` renders
  its dependency-tree topology from journal-reconstructable data alone; the
  Beads mirror reflects the run's real topology/briefs; harvested per-work
  cost/config-demand findings are recorded, not silently absorbed.
- **M2c (gated, last):** after `TASK-M2-001` and `TASK-M2-006` have landed,
  a second, independent repository has run at least one real delivery
  through an orc-werk ledger, with any gaps found routed to a docs
  amendment rather than worked around silently.

## Out of scope

- Rozoro migration/split (explicitly deferred, issue #12 operator ruling);
- the second-agent provider-swap proof and policy parameterization v1
  (deferred out of M2 by the reshape ruling — see "Deferred (M2 reshape)"
  above; these are deferred, not ruled out, so they remain distinct from
  the items below, which are out of scope more durably);
- attention/AttentionPort machinery activation, unless pulled in by
  observed need during M2a/M2a+/M2b (per `DELIVERY-STANCE`'s
  dogfooding-demand principle, not scheduled speculatively);
- Go rewrite;
- mutation/property tooling (trigger for promotion unchanged from
  `DELIVERY-STANCE`: post-MVP, dev-only, not moved by this milestone);
- policy profiles, `PolicyPort`/pluggable policy, LLM-as-policy, policy DSL
  (M2d's explicit out-of-scope list above; reserved for a later "who
  decides" milestone);
- Beads authority graduation (bd-native ready/claim/dependency-driven
  dispatch) — dormant on issue #47, not scheduled by this milestone; only
  the write-only mirror (`TASK-M2-006`) is in scope.
