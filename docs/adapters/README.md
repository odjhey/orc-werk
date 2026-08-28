---
id: ADAPTERS-README
type: guide
status: current
authority: normative
description: Adapter documentation contract and mapping template.
---

# Adapter documentation contract

Each provider adapter gets its own directory:

```text
adapters/<provider>/
├── README.md
├── mapping.md
├── capabilities.md
└── conformance.md
```

## Mapping document requirements

For each canonical concept/operation document:

- provider concept/command/API;
- direct mapping;
- lossy fields intentionally discarded;
- synthesized fields derived by the adapter;
- impossible mappings;
- canonical error translation;
- idempotency behavior.

Provider vocabulary belongs here, not in core contracts.

## Capability document requirements

List only canonical `CAP-*` guarantees the adapter can actually prove.

## Conformance document requirements

Record pass/fail/unsupported status for each applicable `CONF-*` requirement and link to automated tests/evidence.
