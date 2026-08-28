---
id: ADAPTER-NO-MISTAKES
type: adapter
status: draft
authority: informative
description: Draft no-mistakes assurance adapter slot.
---

# no-mistakes adapter

no-mistakes is a candidate assurance provider, not an Orc Werk core dependency.

The adapter is expected to normalize exact candidate identity, terminal assurance verdict, evidence references, and final candidate identity when the pipeline mutates the subject.

Where no-mistakes exposes sufficiently structured and attributable code-review findings, the adapter may additionally produce the optional `review-findings/v1` extension. That extension is not required for generic assurance and does not make no-mistakes the owner of Orc Werk's review-finding schema.

See:

- [Mapping](mapping.md)
- [Capabilities](capabilities.md)
- [Conformance](conformance.md)
- `EXT-REVIEW-FINDINGS-V1`
