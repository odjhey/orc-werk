---
id: CONTRACT-EXTENSIONS
type: contract
status: current
authority: normative
version: 1
description: Generic versioned extension envelope for specialized provider and workflow semantics.
---

# Extension contract

Extensions let Orc Werk carry specialized semantics without promoting them into the generic orchestration domain.

The core owns the extension transport contract. Individual extensions own their payload semantics.

## Canonical shape

A canonical object that supports extensions MAY include:

```json
{
  "extensions": {
    "review-findings/v1": {
      "findings": []
    }
  }
}
```

An extension key is a stable, versioned identifier. The payload MUST contain only portable JSON-compatible values.

## EXT-001 — Namespaced and versioned

Every extension MUST have a stable identifier containing an explicit schema version, such as `review-findings/v1`.

## EXT-002 — Core ignorance

The generic orchestration core MUST NOT branch on extension payload internals. Policy or extension-aware application code MAY interpret a known extension.

## EXT-003 — No canonical override

An extension MUST NOT redefine, contradict, or override canonical fields such as candidate identity, assurance verdict, execution outcome, work identity, or decision identity.

## EXT-004 — Capability advertisement

A provider MUST NOT claim support for a named extension unless it can produce that extension according to its published schema and semantics. Policy MAY require a named extension and MUST fail explicitly or select another provider when the requirement is unmet.

## EXT-005 — Unknown-extension safety

Consumers that do not understand an extension MUST be able to ignore it without changing canonical behavior. Components that promise lossless canonical round-trip MUST preserve unknown extension keys and payloads unchanged.

## EXT-006 — Portable representation

Extension payloads MUST NOT depend on Python classes, pickle, provider-native object identity, or other language/runtime-specific serialization.

## EXT-007 — Extension evidence does not replace canonical assurance

An assurance extension MAY explain or enrich a canonical verdict, but it MUST NOT be the only representation of the verdict required by `PORT-ASSURANCE`.

## Selection rule

A concept SHOULD be an extension rather than a core field when it is useful to one class of provider or workflow but is not required to execute Orc Werk's generic delivery state machine.

## Related

- `P-001`
- `P-002`
- `P-005`
- `P-009`
- `INV-013`
- `PORT-ASSURANCE`
