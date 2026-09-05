---
id: EXT-ASSURANCE-DEPTH-V1
type: extension
status: draft
authority: normative
version: 1
description: Verifier-attested assurance depth (live | test | static) extension for assurance settlements.
---

# `assurance-depth/v1`

**Status: draft proposal.** Not yet binding; not yet emitted by any orc code path. Provenance: `docs/reports/2026-09-05-pstack-graded-verdicts.md`.

`assurance-depth/v1` is an optional extension carrying the *depth* at which a verifier attests it evaluated a Candidate: whether it exercised the candidate's behavior live on its real surface, exercised it through automated tests, or inspected it statically without exercising behavior at all. It travels in an assurance entry's existing `extensions` slot and unchanged on `FACT-ASSURE-SETTLED.extensions`; it is not a canonical Fact field.

It is intentionally not part of generic Assurance semantics. The canonical verdict (`accepted | rejected | inconclusive`) already answers *whether* the candidate passed. This extension answers the separate question *how deeply was that judgment earned*, so that "it type-checks" and "I ran it and watched it work" stop being journaled as the same `accepted`.

## Purpose

Make an `accepted` verdict that rests on static inspection distinguishable, in durable journal history and operator reference views, from one that rests on exercised behavior — without changing candidate binding, verdict meaning, or delivery state. Extension-aware policy MAY then require a minimum depth for a class of work ("behavioral work needs better than static") and treat a shallower `accepted` as insufficient for *its* purposes while the canonical verdict stays exactly what the verifier recorded.

## Scope rules

- **Verifier-attested observation.** The payload records the verifier's claim about what it actually did against this exact candidate. The kernel MUST NOT re-derive, validate, or enforce it.
- **One dimension only.** `depth` describes evaluation method, never outcome. Outcome remains the canonical verdict. A blocked verifier is `inconclusive`; a candidate that failed a live check is `rejected` with `depth: live`. The two dimensions MUST NOT be collapsed into one enumeration (the same independence rule `EXT-REVIEW-FINDINGS-V1` applies to severity/disposition/confidence).
- **Ordered for policy, opaque to the kernel.** `live > test > static` is a documented total order so extension-aware policy can express floors and "or better" comparisons. The generic core MUST NOT branch on it.
- **Adapter-generic.** "Live" is whatever the candidate's real surface is: a running CLI, a rendered document, a deployed service, a UI. No provider or language vocabulary is required.
- **Optional provenance.** An assurance settlement remains valid without this extension. Verify seats SHOULD record it per the amendment to `PLAYBOOK-AGENT-CLI` proposed in the provenance report.
- **No canonical override.** Per `EXT-003` and `EXT-007`, this extension neither overrides nor replaces the canonical verdict, candidate fingerprint, or assurance evidence.

## Files

- [Schema](schema.md)
- [Semantics](semantics.md)
- [Examples](examples.md)

## Related

- `CONTRACT-EXTENSIONS`
- `FACT-ASSURE-SETTLED`
- `PORT-ASSURANCE`
- `EXT-ASSURANCE-CONTEXT-V1` (sibling: *against what base*; this extension: *how deeply*)
- `EXT-REVIEW-FINDINGS-V1` (sibling: *what was found*)
- `SCN-020`
- `CONF-EXT-008`
- `INV-007`
- `INV-009`
- `P-003`
- `P-010`
