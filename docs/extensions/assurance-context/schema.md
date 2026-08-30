---
id: EXT-ASSURANCE-CONTEXT-V1-SCHEMA
type: contract
status: current
authority: normative
version: 1
description: Portable schema for assurance-context/v1.
---

# `assurance-context/v1` schema

The extension payload has this conceptual shape:

```text
AssuranceContextV1 {
    base: AuditBase
}

AuditBase {
    identity: string          # resolved immutable identity; opaque
    ref?: string              # optional mutable display name; opaque
    relation?: string         # optional relationship label; opaque
    derivation_ref?: string   # optional resolvable derivation evidence; opaque
    trial_merge?: string      # optional trial result; opaque
}
```

Canonical transport example:

```json
{
  "extensions": {
    "assurance-context/v1": {
      "base": {
        "identity": "0123456789abcdef0123456789abcdef01234567",
        "ref": "master",
        "relation": "merge-base",
        "derivation_ref": "git merge-base origin/master <head_sha>",
        "trial_merge": "clean"
      }
    }
  }
}
```

This transports on the assurance entry's and `FACT-ASSURE-SETTLED` envelope's existing `extensions` slots. It adds no canonical Fact field.

## Required fields

The payload MUST contain `base`. `base` MUST contain `identity`.

The extension itself is optional on an assurance entry. When absent, no audit base is inferred or fabricated.

## Optional fields

`base.ref`, `base.relation`, `base.derivation_ref`, and `base.trial_merge` are independently optional. Their absence supplies no default meaning.

## Field rules

### `base.identity`

An opaque string naming the resolved immutable identity the verifier compared against. It MUST be an immutable value, never a bare mutable reference name. A commit sha is one Git-backed example; the schema does not require Git identity syntax.

### Other `base` fields

All are opaque strings. `ref` may preserve a mutable display name. `relation`, `derivation_ref`, and `trial_merge` preserve verifier-supplied context without defining an enumeration or generic policy meaning. Consumers MUST NOT infer truth merely from their presence.

## Opaque-strings rule (`INV-014`)

Every value in `base` is free-form and adapter-generic. Consumers MUST treat values as uninterpreted strings for storage, display, transport, and equality comparison. Adapter-local or extension-aware policy MAY interpret a known value per `EXT-002`; generic core MUST NOT.

## Portability

The payload MUST satisfy `EXT-006` and therefore use only portable JSON-compatible values.

## CONF-EXT obligations

- `CONF-EXT-001`: the payload uses only JSON-compatible strings and objects.
- `CONF-EXT-002` and `CONF-EXT-006`: absent or unknown `assurance-context/v1` never changes canonical processing or projection.
- `CONF-EXT-003` and `CONF-EXT-007`: lossless transports preserve the payload unchanged from assurance observation through the journal.
- `CONF-EXT-004`: no payload value overrides the canonical verdict or candidate fingerprint.

## Versioning

Adding a required field or changing a field's meaning requires a new extension version (`assurance-context/v2`) rather than a silent change to `v1`.
