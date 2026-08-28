---
id: ADR-0004
type: decision
status: current
authority: informative
description: Keep specialized provider and workflow semantics outside the core through versioned extensions.
---

# ADR-0004 — Versioned extensions for specialized semantics

## Status

Accepted.

## Context

Orc Werk needs to remain useful beyond code review while still allowing opinionated workflows to exchange richer structured data. Code-review findings are a concrete example: severity, disposition, category, confidence, lifecycle, source location, and evidence are valuable for review routing, but they are not required by every assurance provider or every delivery domain.

Baking these dimensions into the generic core would make the domain code-review-specific. Leaving them as unstructured prose would force policy to parse text and would couple behavior to individual providers.

## Options

1. Add review-finding fields directly to the canonical Assurance/Evidence domain.
2. Leave provider-specific structured results entirely opaque and unstandardized.
3. Define a generic versioned extension envelope and standardize specialized schemas independently.

## Decision

Choose option 3.

Orc Werk defines `CONTRACT-EXTENSIONS` as the generic transport/compatibility contract. Specialized schemas live under `docs/extensions/` and may be normative for that extension without becoming mandatory core semantics.

The first registered extension is `EXT-REVIEW-FINDINGS-V1` with wire identifier `review-findings/v1`.

The generic core records the canonical assurance verdict and candidate binding. It does not inspect review-finding payloads to derive those canonical facts. Extension-aware policy may interpret the structured findings after the canonical observation is recorded.

## Consequences

Positive:

- Orc Werk remains domain-generic.
- Review policy can consume structured findings without depending on no-mistakes or another specific provider.
- New specialized semantics can evolve with independent schema versions.
- Unknown extensions can be safely ignored by generic consumers.
- A future Go implementation can consume the same JSON-compatible extension payloads.

Costs:

- Extension schemas require their own compatibility discipline and conformance tests.
- Adapters may need explicit mapping code from provider-native finding formats.
- Policy must declare when a named extension is required instead of assuming every assurance provider emits it.

## Related contract IDs

- `CONTRACT-EXTENSIONS`
- `PORT-ASSURANCE`
- `CAP-ASSURE-STRUCTURED-FINDINGS`
- `INV-013`
- `P-001`
- `P-002`
- `P-009`
