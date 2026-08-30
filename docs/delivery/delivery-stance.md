---
id: DELIVERY-STANCE
type: playbook
status: current
authority: informative
description: Current quality bar and complementary delivery goals — dogfood-ready, not golden; what is negotiable at this stage and what never is.
---

# Delivery stance

This document records the current delivery quality bar and the complementary goals that sit alongside the milestone definitions. It is informative delivery policy, revisited at each milestone boundary; it never overrides contracts.

## Current bar: dogfood-ready, not golden

The v0.x target is a system the operator can run real work through and heal while using — not a polished release. Concretely, a change is shippable at this bar when it is contract-faithful, auditable, and self-healing; it is not held for polish.

Rough edges are acceptable when all three hold:

1. they do not violate a normative contract;
2. they are recorded — as a GitHub issue, a deferred-ledger entry, or an "Ambiguities encountered" note in the shipping PR;
3. they cannot corrupt durable state (the journal survives them).

An unrecorded rough edge is not a rough edge; it is a defect.

## Hard bars (never relaxed, even pre-golden)

- **Contract fidelity** — code never diverges from normative docs; when they conflict, the docs are amended first or the code is fixed, and the conflict is surfaced.
- **Journal integrity and portability** — canonical records stay portable JSON with explicit schema versions; append-preserving; replay reconstructs identical projections.
- **Canonical errors at user-facing boundaries** — the CLI and ports surface `CONTRACT-ERRORS` values, never implementation tracebacks.
- **Determinism** — no randomness or wall-clock in canonical data or idempotency keys.
- **Test falsifiability** — scenario tests mirror the scenario docs; suites must demonstrably fail when contracts are violated (mutation smoke at integration gates).

## Soft bars (explicitly deferred, tracked)

- UX polish and diagnostic ergonomics (root-cause surfacing, config schema strictness) — tracked as issues, batched into milestones.
- Performance work of any kind.
- Mutation/property-based testing and lint/typecheck tooling — post-MVP, dev-only (see `tests/README.md`).
- Broad provider/adapter coverage — one real adapter at a time, each rerunning the conformance suites.

## Complementary goals

- **Dogfood feedback is the backlog.** Findings from real usage are filed as issues and triaged into the next milestone; the loop from "it annoyed me" to "it is tracked" should be same-day. A good finding carries a short repro when possible (the exact command plus observed versus expected behavior), the full `orc version` output, and the run id or journal excerpt when ledger-related; the repository issue template asks for exactly these.
- **Contracts lead code** in both directions: ambiguity found during implementation routes to a docs amendment, and behavior invented by code gets legitimized or reverted — never left implicit.
- **Heal-while-using over prevent-all-failure.** Recovery paths (replay, reconciliation, torn-tail healing) get priority over exhaustive input hardening.

## Review cadence

Revisit this stance at each milestone close. Promotions of soft bars to hard bars (e.g. adopting mutation tooling, tightening config validation) are recorded here with the milestone that triggered them.
