---
id: TASK-M5-003
type: task-card
status: current
authority: normative
description: Author docs/adapters/omp/{README,mapping,capabilities,conformance}.md per ADAPTERS-README, and add an OMP example to docs/extensions/executor-identity/v1/examples.md.
implements:
  - ADR-0007
  - ADAPTERS-README
  - EXT-EXECUTOR-IDENTITY-V1
verifies: []
---

# TASK-M5-003 — `docs/adapters/omp/*` and the `executor-identity/v1` OMP example

Design source: `ADR-0007`; `M5-OMP-FIRST-DELIVERY` Phase 1;
`ADAPTERS-README`.

## The gap

OMP is a new provider adapter for orc-werk's own seat machinery, and
`ADAPTERS-README` requires every provider adapter to document its own
directory (`README.md`, `mapping.md`, `capabilities.md`,
`conformance.md`) rather than leaking provider vocabulary into generic
contracts or playbooks. No such directory exists yet for OMP, so the
`executor-identity/v1` field mapping (model resolved from the agent's
`model:` field, `session_ref`/`seat_ref` derived from OMP session/agent
identity, `role` from the agent name) currently has no home other than
prose in `PLAYBOOK-AGENT-CLI`, which `TASK-M5-002` is removing.

## Outcome

`docs/adapters/omp/README.md`, `mapping.md`, `capabilities.md`, and
`conformance.md` exist, following the `ADAPTERS-README` contract exactly:
the mapping document covers OMP concept/command/API → canonical mapping,
lossy fields intentionally discarded, synthesized fields, impossible
mappings, canonical error translation, and idempotency behavior for the
`executor-identity/v1` extension; the capabilities document lists only
the canonical `CAP-*` guarantees OMP-as-adapter can actually prove; the
conformance document records pass/fail/unsupported for each applicable
`CONF-*` requirement, linked to `TASK-M5-001`'s capability-test evidence.
`docs/extensions/executor-identity/v1/examples.md` gains an OMP-sourced
example alongside its existing ship/verify examples.

## In scope

- `docs/adapters/omp/README.md` — directory overview, scope, and what OMP
  is/is not an adapter for (it is a seat-execution harness, not a
  `PORT-EXECUTION`/`PORT-ASSURANCE` adapter that orc drives; orc never
  spawns or observes an OMP task, per `T3`/`ADR-0005`).
- `docs/adapters/omp/mapping.md` — the `executor-identity/v1` field
  mapping table, moved and expanded from the former `PLAYBOOK-AGENT-CLI`
  prose.
- `docs/adapters/omp/capabilities.md` — canonical `CAP-*` guarantees OMP
  genuinely proves, sourced from `TASK-M5-001`'s report.
- `docs/adapters/omp/conformance.md` — pass/fail/unsupported per
  applicable `CONF-*`, linked to `TASK-M5-001`'s evidence.
- `docs/extensions/executor-identity/v1/examples.md` — one added OMP
  example.

## Out of scope

Any change to `executor-identity/v1`'s canonical schema (`EXT-EXECUTOR-
IDENTITY-V1`'s contract itself is unchanged; this card only documents an
adapter's use of it). The agent definitions and hook (`TASK-M5-004`,
`TASK-M5-005`).

## Acceptance

- `docs/adapters/omp/README.md`, `mapping.md`, `capabilities.md`, and
  `conformance.md` all exist and pass `docs_check.py`'s frontmatter and
  stable-ID checks.
- `mapping.md` states, for `executor-identity/v1`, the direct mapping,
  any lossy/synthesized fields, and idempotency behavior — not a
  restatement of the generic extension contract.
- `capabilities.md` lists no `CAP-*` guarantee `TASK-M5-001`'s report does
  not evidence.
- `conformance.md` cites `TASK-M5-001`'s capability-test report for each
  recorded pass/fail.
- `docs/extensions/executor-identity/v1/examples.md` contains an OMP
  example distinguishable from the existing ship/verify examples.
