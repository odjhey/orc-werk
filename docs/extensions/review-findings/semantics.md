---
id: EXT-REVIEW-FINDINGS-V1-SEMANTICS
type: contract
status: current
authority: normative
version: 1
description: Behavioral semantics for review-findings/v1.
---

# `review-findings/v1` semantics

## Entry interpretation (string vs. structured)

`findings` entries admit two forms (`schema.md`, additive amendment,
issue #249). A string entry is a **complete, valid, unstructured finding**
in its own right — it is not a partial, deprecated, or degraded structured
finding, and consumers MUST NOT treat its presence as an error, an
incomplete record, or a signal to synthesize missing structured dimensions
(severity, disposition, category, confidence, status) for it.

Consumers of `review-findings/v1` MUST accept both forms in the same
`findings` array and MUST NOT reject a payload, or an individual entry,
solely because it is a string rather than an object (or vice versa). A
consumer that only understands one form and encounters the other should
fall back to treating the entry as opaque (e.g. for display, show the raw
string; for structured-dimension queries such as "list blocking findings",
a string entry simply has no severity/disposition/etc. to match against —
it is neither blocking nor non-blocking, it is unclassified).

## Severity

Severity answers: **what is the consequence if this finding is real?**

It does not itself determine merge eligibility, confidence, or lifecycle.

## Disposition

Disposition answers: **may the candidate proceed under the producing review policy while this finding remains in its current status?**

A provider MAY emit `blocking` or `non-blocking` independently of severity.

## Category

Category identifies the primary defect class. Providers SHOULD choose the narrowest category that best explains the finding rather than duplicating one observation into several categories solely for emphasis.

## Confidence

Confidence answers: **how strongly does the reviewer believe the finding is valid?**

Confidence does not automatically determine disposition.

## Status

- `open`: unresolved finding.
- `fixed`: producing workflow reports that the candidate was changed to address the finding; evidence for the changed candidate still follows Orc Werk's candidate-freshness rules.
- `accepted`: finding is acknowledged and intentionally tolerated by applicable policy/authority.
- `false-positive`: finding was determined not to apply.
- `out-of-scope`: finding may be valid but is outside the current delivery scope.

A status transition does not rewrite prior history. Consumers SHOULD retain prior finding observations when maintaining an audit trail.

## Candidate binding

The extension belongs to an assurance observation that is already bound to an exact candidate fingerprint under `PORT-ASSURANCE` and `INV-007`.

If the candidate changes, the prior structured findings remain historical evidence about the old candidate. They MUST NOT be relabeled as findings produced against the new candidate.

## Canonical verdict

The producing assurance provider or configured assurance policy is responsible for returning the canonical verdict (`accepted`, `rejected`, or `inconclusive`).

The generic Orc Werk core MUST NOT inspect `review-findings/v1` to synthesize that verdict.

An extension-aware policy MAY use findings to choose a next action after the canonical observation is recorded. Examples include:

- route a blocking concurrency finding to a concurrency-focused tester;
- route a blocking contract finding to replanning;
- avoid an expensive rerun for a non-blocking style finding;
- escalate a high-severity, low-confidence security finding for independent review.

These are policy examples, not extension invariants.
