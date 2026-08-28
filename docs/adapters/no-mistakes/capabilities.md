---
id: ADAPTER-NO-MISTAKES-CAPABILITIES
type: adapter-capabilities
status: draft
authority: informative
description: Draft no-mistakes assurance capabilities.
---

# no-mistakes capabilities

Expected canonical capabilities to validate during adapter work:

- `CAP-ASSURE-CANDIDATE-BOUND`
- `CAP-ASSURE-STRUCTURED-VERDICT`
- `CAP-ASSURE-MAY-MUTATE-CANDIDATE` when the configured pipeline may change the candidate

Optional capability:

- `CAP-ASSURE-STRUCTURED-FINDINGS` with exact extension support for `review-findings/v1`, only when the adapter can map provider findings to `EXT-REVIEW-FINDINGS-V1-SCHEMA` without ambiguous prose parsing or provenance loss.

Capability claims remain draft until the real adapter passes the corresponding conformance requirements.
