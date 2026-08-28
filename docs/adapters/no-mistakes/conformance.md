---
id: ADAPTER-NO-MISTAKES-CONFORMANCE
type: adapter-conformance
status: draft
authority: informative
description: Draft conformance plan for no-mistakes assurance adapter.
---

# no-mistakes conformance

The future adapter must satisfy generic assurance conformance for every capability it advertises.

Minimum expected checks:

- exact candidate fingerprint is preserved through settlement;
- `accepted`, `rejected`, and `inconclusive` stay distinct;
- candidate mutation returns the exact final candidate when advertised;
- stale evidence from a prior candidate cannot satisfy a new candidate.

If the adapter advertises `CAP-ASSURE-STRUCTURED-FINDINGS` with `review-findings/v1`, it must additionally satisfy `CONF-EXT-001` through `CONF-EXT-006`, including schema conformance to `EXT-REVIEW-FINDINGS-V1-SCHEMA` and core ignorance of extension internals.
