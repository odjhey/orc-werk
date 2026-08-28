---
id: ADAPTER-NO-MISTAKES-MAPPING
type: adapter-mapping
status: draft
authority: informative
description: Draft no-mistakes-to-AssurancePort mapping.
---

# no-mistakes mapping

Required mapping questions:

- how submitted candidate identity is proven;
- how final candidate identity is proven when the pipeline mutates it;
- how terminal accepted/rejected/inconclusive verdict is derived without parsing prose;
- how findings/evidence are referenced without copying pipeline internals into core;
- how stale evidence is rejected after candidate changes.

## Structured findings extension

If the no-mistakes adapter can derive structured findings without weakening provenance or parsing ambiguous prose, it SHOULD advertise `CAP-ASSURE-STRUCTURED-FINDINGS` with exact extension support for `review-findings/v1` and map provider findings to `EXT-REVIEW-FINDINGS-V1`.

This is optional. A no-mistakes adapter may satisfy generic `PORT-ASSURANCE` without the extension.

The mapping MUST preserve the separation between:

- canonical assurance verdict (`accepted`, `rejected`, `inconclusive`);
- optional structured review findings;
- exact candidate identity/fingerprint.

The adapter MUST NOT use extension payload fields to override the canonical candidate or verdict after they have been normalized.
