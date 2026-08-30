---
id: EXT-ASSURANCE-CONTEXT-V1
type: extension
status: current
authority: normative
version: 1
description: Verifier-attested audit-base provenance extension for assurance settlements.
---

# `assurance-context/v1`

`assurance-context/v1` is an optional extension carrying the audit base a verifier attests it compared a Candidate against. It travels in an assurance entry's existing `extensions` slot and unchanged on `FACT-ASSURE-SETTLED.extensions`; it is not a canonical Fact field.

It is intentionally not part of generic Assurance semantics. The base is provenance supplied by the verifier, not a fact the kernel trusts, derives, or validates.

## Purpose

Make audits performed against different bases distinguishable in journal history and operator reference views without changing candidate binding, verdict meaning, or delivery state.

## Scope rules

- **Verifier-attested observation.** The payload records the verifier's claim about its audit base. The kernel MUST NOT re-derive or validate it.
- **Opaque strings.** Every value in `base` is an opaque string. `base.identity` names a resolved immutable identity; other fields are optional display or provenance context.
- **Adapter-generic.** An immutable commit sha is a Git example, not required vocabulary. Other candidate kinds use their own resolved immutable identity.
- **Optional provenance.** An assurance settlement remains valid without this extension. Git-backed verify seats SHOULD record it per `PLAYBOOK-AGENT-CLI`.
- **No canonical override.** Per `EXT-003` and `EXT-007`, this extension neither overrides nor replaces the canonical verdict, candidate fingerprint, or assurance evidence.

## Files

- [Schema](schema.md)
- [Semantics](semantics.md)
- [Examples](examples.md)

## Related

- `CONTRACT-EXTENSIONS`
- `FACT-ASSURE-SETTLED`
- `PORT-ASSURANCE`
- `SCN-012`
- `CONF-EXT-007`
- `INV-007`
- `INV-008`
- `INV-014`
