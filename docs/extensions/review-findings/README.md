---
id: EXT-REVIEW-FINDINGS-V1
type: extension
status: current
authority: normative
version: 1
description: Structured code-review finding extension for assurance results.
---

# `review-findings/v1`

`review-findings/v1` is an optional assurance extension for structured code-review findings.

It is intentionally not part of the generic Orc Werk core. A documentation review, research task, deployment check, or other assurance provider can use the canonical assurance contract without ever producing this extension.

## Purpose

Represent review findings in a provider-neutral form so policy can reason about review evidence without parsing prose and without depending on one review product.

## Dimensions

| Dimension | Values | Meaning |
|---|---|---|
| Severity | `critical`, `high`, `medium`, `low`, `info` | Consequence if the finding is real |
| Disposition | `blocking`, `non-blocking` | Whether the candidate may proceed under the producing review policy |
| Category | `correctness`, `security`, `contract`, `reliability`, `performance`, `concurrency`, `data-integrity`, `testing`, `maintainability`, `compatibility`, `docs`, `style` | What is wrong |
| Confidence | `high`, `medium`, `low` | Reviewer confidence that the finding is valid |
| Status | `open`, `fixed`, `accepted`, `false-positive`, `out-of-scope` | Finding lifecycle |
| Location | optional file + line/range | Evidence location |
| Evidence | one or more explanations/tests/contracts/references | Why it is a finding |

## Important independence rules

Severity, disposition, confidence, and status are independent dimensions.

Examples that are valid:

- `severity=high`, `disposition=non-blocking`: serious debt explicitly accepted for this delivery.
- `severity=low`, `disposition=blocking`: small defect that violates a hard contract.
- `confidence=low`, `disposition=blocking`: policy chooses to stop despite uncertainty.

Consumers MUST NOT derive one dimension mechanically from another unless an explicit policy says so.

## Canonical assurance relationship

The producer still returns the canonical `AssuranceObservation.verdict` from `PORT-ASSURANCE`.

The extension explains or enriches that verdict; the generic core does not derive the canonical verdict by inspecting findings.

## Files

- [Schema](schema.md)
- [Semantics](semantics.md)
- [Examples](examples.md)

## Related

- `P-010`
- `CONTRACT-EXTENSIONS`
- `PORT-ASSURANCE`
- `CAP-ASSURE-STRUCTURED-FINDINGS`
