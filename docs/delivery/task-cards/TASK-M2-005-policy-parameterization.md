---
id: TASK-M2-005
type: task-card
status: current
authority: normative
description: Per-work max_attempts, gated on observed cost data; a narrow, separately-gated no-retry exception for the single kernel-checkable ERR-UNSUPPORTED-CAPABILITY cause only — default policy stays cause-blind-but-bounded otherwise.
implements:
  - STATE-DELIVERY
verifies: []
---

# TASK-M2-005 — Policy parameterization v1

### Deferred — removed from M2 scope

**Operator ruling (M2 reshape, 2026-08-28): this card is deferred, out of
M2 scope.** Its two-gate design (below) is unchanged and stands as-is for
whenever either gate fires. Recorded on the milestone's deferred list
(`docs/delivery/M2-close-the-loop.md`, "Deferred (M2 reshape)").

**Pull trigger (named, unchanged from the card's own Gate section):**
observed cost data from real `acpx`-adapter runs — (a) DAG-wide
budget-starvation evidence for per-work `max_attempts`; (b) evidence of
real spend wasted specifically on statically-doomed
`ERR-UNSUPPORTED-CAPABILITY` retries, for the narrower no-retry exception.
`TASK-M2-003`'s reframing as a real-DAG **practice run** (per the M2
reshape) is now this card's most direct source of that evidence — the
practice run's explicit purpose includes harvesting per-work cost data,
which is exactly what this card's gates are waiting on.

## Outcome

Two independently-gated items — deliberately not a policy framework:

- **(a) Per-work `max_attempts`.** The plan/config gains an optional
  per-work retry-budget override, replacing the single uniform policy
  default (`docs/domain/state-machines/delivery.md`) for DAGs where works
  have genuinely different risk/cost profiles.
- **(b) A single, narrow, kernel-checkable no-retry exception —
  conditional on its own stricter gate.** The default policy remains
  cause-blind-but-bounded **permanently**: retry-to-budget always, for
  every failure cause, is the standing default, not a gap to close.
  Bounded budgets plus root-cause-visible `BLOCKED` (issue #16's fix,
  already shipped) already contain the unclassified-permanent-failure
  mode on their own. If (and only if) cost data justifies a no-retry path
  at all, its scope is restricted to exactly one static cause:
  `ERR-UNSUPPORTED-CAPABILITY` at dispatch — the sole cause `INV-013`'s
  fixed capability set makes kernel-decidable (a theorem the kernel can
  verify itself, not adapter judgment). **`ERR-PERMANENT`
  (adapter-classified) retry-skipping is explicitly and permanently out of
  scope for this card and this milestone** — an adapter's own
  classification of "not retryable" is exactly the unverifiable,
  misclassification-prone judgment the operator's own Temporal production
  experience (unraised/mis-marked non-retryable exceptions causing real
  retry bugs) rules out.

## Gate

**(a)'s gate:** observed cost data from real `acpx`-adapter runs (M1b, and
M2a/M2b if landed first) shows DAG-wide budget starvation — one Work's
retries crowding out or being crowded out by a sibling's, where a shared
budget is the wrong default. Per `DELIVERY-STANCE`, this is dogfooding
demand, not speculation; if the data does not show the need, (a) is
deferred past M2, not forced to ship.

**(b)'s gate is stricter and separate from (a)'s:** real, observed spend
wasted specifically on statically-doomed `ERR-UNSUPPORTED-CAPABILITY`
retries (the same shape DFS-007 already demonstrates for the scripted
adapter) — not general dissatisfaction with retry-to-budget as a default.
The expected steady state is that (b) never ships, because the
cause-blind-but-bounded default plus visible root cause on `BLOCKED` is
judged sufficient; that outcome is success, not an incomplete card.

## Docs-first prerequisite for (b)

Policy is currently cause-blind by construction: `FACT-EXEC-SETTLED`
carries `outcome` only; the canonical error class lives in the effect
record's `dispatch_result`, which the retry/`DEC-RETRY`/`DEC-BLOCK`
decision logic never sees. Even this narrow (b) requires a contract
decision first — an optional `cause` field on `FACT-EXEC-SETTLED` scoped
to signal only `ERR-UNSUPPORTED-CAPABILITY`, not an open-ended error-class
enum — authored and reviewed as an amendment to both `STATE-DELIVERY`'s
budget-exhaustion transition-table path and `SCN-006` (max-attempts
extremes), with `DFS-007` updated to match, before any implementation
(`CLAUDE.md` rules 3–5). (a) has no such prerequisite and may proceed
independently once its own gate fires.

## Out of scope

Policy profiles, any `PolicyPort`/pluggable policy abstraction,
LLM-as-policy, a policy DSL (reserved for a later "who decides" milestone,
M3+); any adapter-classified `ERR-PERMANENT` retry-skipping (ruled out for
this card specifically, not merely deferred); any cause other than
`ERR-UNSUPPORTED-CAPABILITY` being treated as non-retryable by default
policy.

## Acceptance

- (a): a DAG with heterogeneous per-work `max_attempts` respects each
  Work's own budget independently, with a regression test showing one
  Work's exhaustion does not affect a sibling's remaining budget;
- (b), only if its stricter gate fires and the docs prerequisite lands
  first: an `ERR-UNSUPPORTED-CAPABILITY` dispatch failure declines further
  retry without consuming budget it would not otherwise have consumed,
  proven by the `SCN-006`/`DFS-007` updates — and no other failure cause is
  ever treated as non-retryable as a side effect of this change.
