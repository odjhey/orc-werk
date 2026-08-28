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
    findings: ReviewFinding[]
}

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

## Required fields

Each finding MUST contain:

- `id`;
- `severity`;
- `disposition`;
- `category`;
- `confidence`;
- `status`;
- `evidence`.

`location` is optional because not every valid review finding maps to a source line.

## Location rules

When present:

- `path` MUST be a repository-relative or provider-declared logical path, never assumed to be a local absolute path;
- line numbers are 1-based positive integers;
- `end_line`, when present, MUST be greater than or equal to `start_line`;
- a finding about a whole file MAY omit line fields.

## Evidence rules

`evidence` MUST contain at least one entry.

Evidence SHOULD prefer the strongest available support: an executable test, contract reference, or reproducible observation over unsupported prose.

## Portability

The payload MUST satisfy `EXT-006` and therefore use only portable JSON-compatible values.

## Versioning

Adding a new enum value, changing required fields, or changing field meaning requires a new extension version unless the published compatibility rules explicitly permit it.
