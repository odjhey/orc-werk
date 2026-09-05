---
id: EXT-ASSURANCE-DEPTH-V1-SCHEMA
type: contract
status: draft
authority: normative
version: 1
description: Portable schema for assurance-depth/v1.
---

# `assurance-depth/v1` schema

**Status: draft proposal** (see `EXT-ASSURANCE-DEPTH-V1`).

The extension payload has this conceptual shape:

```text
AssuranceDepthV1 {
    depth: "live" | "test" | "static"
    surface?: string          # opaque: what was exercised or inspected
    derivation_ref?: string   # opaque: resolvable pointer to how (command, log, run URL)
}
```

These three names are the complete field set for `assurance-depth/v1`; producers MUST NOT add other fields to a v1 payload.

Canonical transport example:

```json
{
  "extensions": {
    "assurance-depth/v1": {
      "depth": "live",
      "surface": "orc CLI against a scratch journal",
      "derivation_ref": "gh-pr:258#issuecomment-verify-transcript"
    }
  }
}
```

The payload transports on the assurance entry's and `FACT-ASSURE-SETTLED` envelope's existing `extensions` slots. It adds no canonical Fact field.

## Required fields

The payload MUST contain `depth`, and `depth` MUST be exactly one of `live`, `test`, or `static`.

The extension itself is optional on an assurance entry. When absent, no depth is inferred or fabricated; in particular absence does NOT mean `static`.

## Optional fields

`surface` and `derivation_ref` are independently optional opaque strings. Their absence supplies no default meaning.

## Field rules

### `depth`

The deepest evaluation method the verifier attests it *completed* against this exact candidate fingerprint:

| Value | Meaning | Ordinal |
|---|---|---|
| `live` | The candidate's behavior was exercised on its real or target surface and the outcome directly observed by the verifier. | 3 |
| `test` | The candidate's behavior was exercised through automated tests the verifier ran, or whose execution output for this exact candidate the verifier directly observed. | 2 |
| `static` | The candidate was inspected without exercising its behavior: reading the diff, type-checking, linting, schema validation, documentation review. | 1 |

The ordinal column defines the documented total order `live > test > static`. Extension-aware policy MAY compare against it ("`test` or better"). The generic core MUST NOT.

Reading a forge's green status badge is `static`: a status is an input to a verdict, not an observation of behavior. `test` requires that the verifier itself ran, or read the execution output of, tests against this fingerprint.

### `surface`

An opaque string naming what was exercised or inspected — a CLI, a rendered page, a service endpoint, a document. It carries no enumerated meaning and MUST NOT be parsed by generic consumers.

### `derivation_ref`

An opaque string the verifier supplies so a later reader can find how the depth was reached: a command line, a log path, a transcript reference, a run URL. It is convenience provenance; the canonical audit trail remains `FACT-ASSURE-SETTLED.evidence_refs`, which this field does not replace (`EXT-007`).

## Opaque-strings rule (`INV-014`)

`surface` and `derivation_ref` are free-form and adapter-generic. Consumers MUST treat them as uninterpreted strings for storage, display, transport, and equality comparison.

## Portability

The payload MUST satisfy `EXT-006` and therefore use only portable JSON-compatible values.

## CONF-EXT obligations

- `CONF-EXT-001`: the payload uses only JSON-compatible strings and objects.
- `CONF-EXT-002` and `CONF-EXT-006`: absent or unknown `assurance-depth/v1` never changes canonical processing or projection.
- `CONF-EXT-003` and `CONF-EXT-008`: lossless transports preserve the payload unchanged from assurance observation through the journal.
- `CONF-EXT-004`: no payload value overrides the canonical verdict or candidate fingerprint. In particular `depth` never promotes, demotes, or qualifies an `accepted`, `rejected`, or `inconclusive` verdict for the kernel.

## Versioning

Adding a `depth` value, adding a required field, or changing a field's meaning requires a new extension version (`assurance-depth/v2`) rather than a silent change to `v1`.
