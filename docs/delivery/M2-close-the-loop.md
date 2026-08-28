---
id: M-002
type: milestone
status: current
authority: normative
description: Third milestone — the delivery loop closes itself (automated assurance, real multi-work DAGs through a real adapter) and leaves home (a second real adopting repo).
---

# M2 — Close the loop

## Goal

M1 made orc-werk its own first user: a real, operator-driven delivery ledger,
then a real execution adapter (`acpx` driving Pi) with the operator still
seated as the assurance/verdict authority for every candidate. M2's shape —
"the loop closes itself, and leaves home" — has two parts:

- **Closes itself**: the verdict seat stops being a human typing a
  recorded outcome and becomes a real `PORT-ASSURANCE` provider
  (`no-mistakes`), so a delivery can run start-to-finish — execution
  *and* assurance — without an operator manually recording either side.
  `P-001` (providers as policy) gets a second, harder proof at the same
  time: a second agent lineage through the *same* `acpx` adapter with zero
  adapter code change.
- **Leaves home**: orc-werk stops being validated only against its own
  repository and is put to work as the ledger for a second, independent
  repo — the first real test of `PRODUCT-ADOPTION`'s adoption ladder from
  outside the project that built it.

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

## Phase M2a — No-mistakes AssurancePort + provider-swap proof

Automates the verdict seat and delivers the second cross-provider proof of
`P-001`.

- A real `PORT-ASSURANCE` adapter backed by `no-mistakes` (the operator's
  existing production review/gate driver) replaces the operator as the
  assurance recorder for candidates it is configured to review.
  `review-findings/v1` (`EXT-REVIEW-FINDINGS-V1`, already registered) is
  the structured findings channel the adapter returns via
  `CAP-ASSURE-STRUCTURED-FINDINGS` — no new extension schema, this
  milestone is the first real producer of an already-registered one.
- A `CONF-ASSURE-*` conformance run (`CONF-ASSURE-001` through
  `CONF-ASSURE-004`, `docs/conformance/README.md`) against the real adapter, the same
  bar every scripted/real `PORT-ASSURANCE` implementation already meets —
  no relaxation for being real.
- A second agent driven through the **same** `acpx` `PORT-EXECUTION`
  adapter M1b shipped: `acpx claude` as the P-001 provider-swap proof.
  The task-card acceptance bar is explicit — **zero adapter code change**.
  Only the configured agent binary/session target changes; the port
  contract, the capability advertisement machinery, and the adapter's own
  code are untouched. This is the concrete evidence that `PORT-EXECUTION`
  over ACP is agent-agnostic at the protocol layer, not Claude-specific
  wearing an ACP costume.

## Phase M2b — Multi-work real DAGs

M1b proved one real Work through the acp adapter. M2b proves a real
dependency graph through it — the same diamond/fan-in/fan-out shapes
`SCN-003`/DFS-003 already prove for scripted providers, now with real
candidates and real (or M2a-automated) assurance on every node.

- Real, dependent deliveries dispatched through the `acpx` `PORT-EXECUTION`
  adapter, not scripted providers — multiple Works with `deps`, driven to
  completion by real agent turns.
- Issue #41 (report dependency-tree view for multi-work runs) lands here:
  it was explicitly gated on topology being journal-reconstructable, which
  a real multi-work acp-driven run is the first opportunity to exercise
  end-to-end (plan shape + real per-work journal history, not a synthetic
  fixture).

## Phase M2c — orc as ledger for another repo

The first true adoption test: point a real, independent repository's
delivery work at an orc-werk ledger, with no changes to orc-werk's own
core semantics.

- Pressure-tests `PRODUCT-ADOPTION`: does the adoption ladder actually
  hold for an outside repo, or does it quietly assume orc-werk-repo-shaped
  conventions (this repo's task-card format, its worktree layout, its own
  `AGENTS.md`) that a second repo does not share?
- No new contract is anticipated from this phase by default; if the
  pressure test finds a genuine gap, that gap gets a docs amendment first,
  per `CLAUDE.md` rule 4 — this phase's job is to find gaps, not to
  pre-guess them.

## Phase M2d — Policy parameterization v1

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

## Required contracts

- `PORT-ASSURANCE` (no amendment expected — first real non-scripted
  implementation; conformance-only unless M2a's implementation surfaces a
  genuine gap)
- `CONTRACT-EXTENSIONS` / `EXT-REVIEW-FINDINGS-V1` (consumed, not amended)
- `P-001` (evidenced, not amended — the provider-swap proof)
- `docs/domain/state-machines/delivery.md` (amended only if M2d's narrow
  (b) triggers: an optional `cause` field on `FACT-EXEC-SETTLED` scoped to
  `ERR-UNSUPPORTED-CAPABILITY` only, plus an amendment to the
  budget-exhaustion transition-table path — docs-first per the prerequisite
  above)
- `SCN-006` (amended only if M2d's narrow (b) triggers — the max-attempts-
  extremes scenario gains a no-retry-on-capability-mismatch case)
- `PRODUCT-ADOPTION` (pressure-tested by M2c; amended only if a real gap is
  found)

## Required scenarios

- `CONF-ASSURE-001` through `CONF-ASSURE-004` re-run against the
  `no-mistakes` `PORT-ASSURANCE` adapter (M2a)
- A new multi-work golden scenario or dogfood corpus entry exercising a
  real DAG through the acp adapter (M2b) — exact form (golden `SCN-*` vs.
  `DFS-*`) decided at `TASK-M2-003` dispatch
- `SCN-001` through `SCN-007` continue to pass unmodified (regression bar)
- If M2d's narrow (b) triggers: an `SCN-006` amendment showing an
  `ERR-UNSUPPORTED-CAPABILITY` dispatch failure declining further retry
  without consuming budget it would not otherwise have consumed —
  `DFS-007` (capability mismatch) is the dogfood-corpus sibling to update
  in step

## Required implementation

- `no-mistakes`-backed `PORT-ASSURANCE` adapter (`TASK-M2-001`)
- `acpx claude` configured as a second agent through the existing acp
  adapter, zero adapter code change (`TASK-M2-002`)
- real multi-work DAG dispatch through the acp adapter; dependency-tree
  view in `orc report` (issue #41) (`TASK-M2-003`)
- a second repo configured to use orc-werk as its delivery ledger
  (`TASK-M2-004`)
- per-work `max_attempts` in the plan/config, once its gate fires
  (`TASK-M2-005` item (a)); the narrow `ERR-UNSUPPORTED-CAPABILITY`
  no-retry path, only if its separate, stricter gate fires and the
  `FACT-EXEC-SETTLED.cause` docs amendment lands first (`TASK-M2-005` item
  (b))

## Acceptance

- **M2a:** a real delivery's candidate is assured by the `no-mistakes`
  adapter with `review-findings/v1` findings and passes `CONF-ASSURE-001`
  through `-004`; a second, distinct agent (`acpx claude`) completes a
  real Work through the same `PORT-EXECUTION` adapter code that drives Pi,
  with a diffed adapter source tree showing no change.
- **M2b:** a real multi-work DAG (at minimum a fan-in shape matching
  DFS-003's topology) is driven to terminal state through the acp adapter,
  and `orc report` renders its dependency-tree topology from journal-
  reconstructable data alone.
- **M2c:** a second, independent repository has run at least one real
  delivery through an orc-werk ledger, with any gaps found routed to a
  docs amendment rather than worked around silently.
- **M2d (each half conditional on its own gate):** a DAG with
  heterogeneous per-work `max_attempts` respects each Work's own budget
  independently (a); if (b)'s narrower gate also fires, an
  `ERR-UNSUPPORTED-CAPABILITY` dispatch failure declines further retry
  without consuming budget — and no other failure cause, including
  adapter-classified `ERR-PERMANENT`, is ever treated as non-retryable by
  default policy.

## Out of scope

- Rozoro migration/split (explicitly deferred, issue #12 operator ruling);
- attention/AttentionPort machinery activation, unless pulled in by
  observed need during M2a/M2b (per `DELIVERY-STANCE`'s dogfooding-demand
  principle, not scheduled speculatively);
- Go rewrite;
- mutation/property tooling (trigger for promotion unchanged from
  `DELIVERY-STANCE`: post-MVP, dev-only, not moved by this milestone);
- policy profiles, `PolicyPort`/pluggable policy, LLM-as-policy, policy DSL
  (M2d's explicit out-of-scope list above; reserved for a later "who
  decides" milestone).
