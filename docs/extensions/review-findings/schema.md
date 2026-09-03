---
id: EXT-REVIEW-FINDINGS-V1-SCHEMA
type: contract
status: current
authority: normative
version: 1
description: Portable schema for review-findings/v1.
---

# `review-findings/v1` schema

The extension payload has this conceptual shape:

```text
ReviewFindingsV1 {
    findings: ReviewFindingEntry[]
}

ReviewFindingEntry = string | ReviewFinding

ReviewFinding {
    id: string
    severity: critical | high | medium | low | info
    disposition: blocking | non-blocking
    category: correctness | security | contract | reliability |
              performance | concurrency | data-integrity | testing |
              maintainability | compatibility | docs | style
    confidence: high | medium | low
    status: open | fixed | accepted | false-positive | out-of-scope
    location?: ReviewLocation
    evidence: ReviewEvidence[]
}

ReviewLocation {
    path: string
    start_line?: integer
    end_line?: integer
}

ReviewEvidence {
    kind: explanation | test | contract | reference
    summary: string
    ref?: string
}
```

## Entry forms

Each entry in `findings` MUST be either:

- **the unstructured form**: a plain JSON string; or
- **the structured form**: a `ReviewFinding` object, per the required fields
  below.

Both forms are first-class and MAY appear in the same `findings` array
(operator ruling, issue #249, additive in-place amendment to this v1
schema — see "Versioning").

## String form field rules

A string entry MUST be nonblank (not empty and not whitespace-only). It
carries no structured dimensions (no severity, disposition, category,
confidence, status, location, or evidence) — see `semantics.md` for how a
consumer must interpret it.

## Structured form: required fields

Each structured (object) finding MUST contain:

- `id`;
- `severity`;
- `disposition`;
- `category`;
- `confidence`;
- `status`;
- `evidence`.

`location` is optional because not every valid review finding maps to a source line.

## Structured form provenance

Historically the structured object form's primary producer was the
`no-mistakes` assurance adapter; that adapter was descoped by `ADR-0005`
(all-in on incremental mode), so the structured form currently has no live
in-tree producer. It is retained as the richer, still-valid alternative
entry form — not removed — because a future or adopter-provided producer
may emit it, and existing structured historical payloads remain
conforming.

## Location rules (structured form)

When present:

- `path` MUST be a repository-relative or provider-declared logical path, never assumed to be a local absolute path;
- line numbers are 1-based positive integers;
- `end_line`, when present, MUST be greater than or equal to `start_line`;
- a finding about a whole file MAY omit line fields.

## Evidence rules (structured form)

`evidence` MUST contain at least one entry.

Evidence SHOULD prefer the strongest available support: an executable test, contract reference, or reproducible observation over unsupported prose.

## Portability

The payload MUST satisfy `EXT-006` and therefore use only portable JSON-compatible values.

## Versioning

Adding a new enum value, changing required fields, or changing field meaning requires a new extension version unless the published compatibility rules explicitly permit it.

Admitting the string form (issue #249) triggers none of those three: it
adds no enum value, the structured form's required fields are unchanged,
and no existing field's meaning changed. It is therefore an in-place v1
amendment, not a version bump, under this section's own rule.
