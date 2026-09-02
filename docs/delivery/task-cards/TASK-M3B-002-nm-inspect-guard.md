---
id: TASK-M3B-002
type: task-card
status: superseded
authority: normative
description: no-mistakes inspect-side identity guard — an already-bound divergent provider run must never settle this candidate's verdict (issue #92 scope extension).
implements: []
verifies: []
---

> **Superseded** (operator ruling ADR-0005, issue #214). The no-mistakes `AssurancePort` adapter this guard protected was **removed** in 0.5.0, pre-1.0, no backward compatibility; the last release carrying it is v0.4.1. See `docs/adapters/command/README.md` (`ADAPTER-COMMAND`) for the push-shaped command assurance adapter and `docs/scenarios/SCN-015-command-assurance.md` (issue #194). Retained as historical reference only.

# TASK-M3B-002 — no-mistakes inspect-side identity guard

## Outcome

PR #98 closed the *adoption*-time hole (request() fails closed on an
unconfirmable or divergent active run). This card closes the
*settlement*-time hole its verifier flagged: `inspect()` re-confirms only
the native run id before settling from the provider run's outcome — it
never re-verifies that the bound run's identity (head/branch/pr) still
matches the candidate. An already-bound divergent run (the xatu incident
shape, bound before #98 existed or via any future identity drift) would
settle a foreign outcome as this candidate's verdict — the exact
`P-004`/`INV-007`..`INV-010` break the adapter exists to prevent.

## Design constraint (from the PR #98 audit)

The assurance id carries no candidate head, so identity must be threaded
to inspect-time from durable state — candidates: the journaled
`FACT-ASSURE-STARTED` (amend its recorded fields, docs-first, mirroring
the #85 facts.md precedent) or the persisted run config. Chosen shape
documented in the mapping doc with the tradeoff.

## Behavior

At inspect(), before treating the bound run's outcome as this
candidate's settlement: positively confirm the run's identity against
the candidate (same precedence as request(): `run_block` head first,
`branch_sync` corroboration when present). Unconfirmable or divergent ⇒
do NOT settle — keep the assurance pending and surface the divergence
(the pending-state affordance/`orc status` output names the bound run
and the mismatch, per the #92 follow-up note). Recovery from that
surfaced state is the operator's seat via TASK-M3B-001's abandon record.

## In scope

Adapter inspect() guard; the identity-threading mechanism (docs-first if
it touches journaled fact fields); stub conformance shapes for
bound-then-divergent and bound-then-unconfirmable; mapping-doc
amendments; pending-assurance divergence surfacing in status output.

## Out of scope

request()-time behavior (shipped, PR #98); any orchestrator/policy
change beyond what identity-threading strictly requires; other adapters.

## Acceptance

- Stub-reproduced xatu shape (bound foreign run reaches terminal
  outcome) does NOT settle the candidate; the divergence is visible in
  `orc status` output.
- Matching-identity regression: a correctly-bound run still settles.
- Mutation check: reverting the guard turns the new conformance shapes
  red. Issue #92 closeable on merge.
