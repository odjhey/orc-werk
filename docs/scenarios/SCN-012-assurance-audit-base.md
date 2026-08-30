---
id: SCN-012
type: scenario
status: current
authority: normative
description: Assurance verdicts against different audit bases remain distinguishable while producing identical canonical projection.
---

# SCN-012 — A stale-base audit is distinguishable from a current one

## Purpose

Prove `EXT-ASSURANCE-CONTEXT-V1` closes an assurance-provenance gap without changing the delivery state machine: operators can distinguish verdicts audited against different immutable bases, while the kernel ignores the extension and journal transport preserves it losslessly.

## Given

- Candidate C1 has one canonical fingerprint.
- Verifier A settles a verdict for C1 carrying `assurance-context/v1.base.identity = "base-old-immutable"` and `base.ref = "master"`.
- In a separate otherwise-identical run, Verifier B settles the same canonical verdict for C1 carrying `assurance-context/v1.base.identity = "base-current-immutable"` and the same display `base.ref = "master"`.
- A control run settles the same canonical verdict with no `assurance-context/v1` extension.

## Then

1. `orc history` preserves each verifier-attested payload unchanged, so the old and current immutable base identities remain distinguishable (`CONF-EXT-003`).
2. `orc refs` renders a `base` row containing `base.identity` and `base.ref` when the extension is present. The two audits are therefore distinguishable without interpreting the mutable display ref or dumping full history.
3. The kernel projection is identical across the old-base, current-base, and absent-extension runs. Presence, absence, or payload changes never alter the verdict, Work state, transition, or Decision (`EXT-002`, `EXT-005`, `CONF-EXT-006`, `CONF-EXT-007`).
4. Reading the durable journal returns the `assurance-context/v1` payload canonically unchanged from what the assurance observation supplied (`CONF-EXT-003`).
5. The kernel does not re-derive or validate either base. Each remains a verifier-attested provenance observation, not a core fact field.

## Inherited settlement

If C1 is re-observed under `SCN-009`, verdict inheritance cites the original `FACT-ASSURE-SETTLED`. Its original base remains unchanged; no second assurance Fact or newly derived base is created.

## Mutation check

Removing the `orc refs` assurance-context row makes the old and current bases indistinguishable on that operator surface. Branching the reducer on the payload makes the projection comparison fail. Dropping or rewriting the extension during journal transport makes the round-trip assertion fail.

Verifies: `EXT-002`, `EXT-003`, `EXT-005`, `EXT-006`, `EXT-007`, `CONF-EXT-003`, `CONF-EXT-006`, `CONF-EXT-007`, `INV-007`, `INV-008`, `INV-014`.
