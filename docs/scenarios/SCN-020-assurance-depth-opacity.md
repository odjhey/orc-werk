---
id: SCN-020
type: scenario
status: draft
authority: normative
description: assurance-depth/v1 transports losslessly and never changes canonical transitions or projection.
---

# SCN-020 — Assurance depth is opaque provenance

**Status: draft** — proposed alongside `EXT-ASSURANCE-DEPTH-V1`; becomes binding when that extension is registered as current.

## Purpose

Prove that recording *how deeply* a verifier evaluated a candidate is pure provenance: it survives the journal unchanged and has no effect on the delivery state machine.

## Given

- Work A is ready; `max_attempts = 3`.
- Execution 1 produces Candidate C1.
- The verify seat records `accepted` for C1 with `extensions["assurance-depth/v1"] = {"depth": "static", "surface": "docs diff"}`.
- An otherwise identical run records `accepted` for the same candidate content with `depth: live`, and a third with no `assurance-depth/v1` at all.

## When

Each run is dispatched to settlement and then replayed from its journal.

## Then

1. All three runs reach `ACCEPTED` with identical Decision sequences and identical canonical projections (`CONF-EXT-006`).
2. In the first two runs, `FACT-ASSURE-SETTLED.extensions["assurance-depth/v1"]` equals the recorded payload byte-for-byte after replay; in the third, the key is absent and nothing is fabricated (`CONF-EXT-003`, `CONF-EXT-008`).
3. A `rejected` verdict carrying `depth: live` follows the ordinary `DEC-RETRY`/`DEC-BLOCK` path; the depth value neither softens nor hardens the rejection (`CONF-EXT-004`, `INV-009`).
4. When `SCN-009` inheritance applies to a re-observed candidate, the inherited settlement's `assurance-depth/v1` is the original payload; no re-derivation occurs.
5. A payload whose `depth` is not one of `live | test | static` is a producer-conformance failure in the dev gate, not a kernel error: the kernel transports it unchanged (`CONF-EXT-002`).

## Verifies

- `INV-007`
- `INV-009`
- `CONF-EXT-002`
- `CONF-EXT-003`
- `CONF-EXT-004`
- `CONF-EXT-006`
- `CONF-EXT-008`
