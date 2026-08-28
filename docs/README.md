---
id: DOCS-ROOT
type: index
status: current
authority: normative
description: Documentation authority, reading order, and maintenance rules.
---

# Documentation system

The documentation is part of the Orc Werk product contract.

## Reading order

1. Product thesis and boundaries
2. Ubiquitous language and invariants
3. State machines and port contracts
4. Facts, decisions, effects, errors, and capabilities
5. Golden scenarios and conformance requirements
6. Architecture/dependency guidance for the current reference implementation
7. Adapter mappings
8. Milestones and task cards
9. Research lineage when deeper design context is needed

## Authority precedence

When documents appear to conflict, treat the conflict as a defect and surface it. Until corrected, use this precedence:

1. `docs/contracts/` invariants and contracts
2. current approved ADRs
3. `docs/domain/` definitions and state machines
4. current milestone/task specifications
5. current normative architecture constraints
6. adapter mapping documents
7. playbooks/reports/research references
8. historical or superseded documents

Research sources explain where ideas came from; they never override current Orc Werk contracts.

## Status

- `current`: active document
- `draft`: under design; not yet binding unless referenced by a current milestone
- `superseded`: retained history; must link to replacement
- `archived`: historical/reference only

## Authority

- `normative`: defines required behavior
- `informative`: explanation, report, research/reference, or implementation note

## Stable ID prefixes

| Prefix | Meaning |
|---|---|
| `P-` | Product principle |
| `INV-` | Invariant |
| `ENT-` | Domain entity |
| `PORT-` | Port |
| `FACT-` | Fact |
| `DEC-` | Decision |
| `FX-` | Effect |
| `CAP-` | Capability |
| `ERR-` | Canonical error |
| `SCN-` | Golden scenario |
| `CONF-` | Conformance requirement |
| `ADR-` | Architecture decision |
| `M-` | Milestone |
| `TASK-` | Delivery task card |
| `ARCH-` | Reference-implementation architecture constraint |

## Authoring rules

- Do not duplicate normative MUST/ONLY/REJECT/REQUIRED prose. Reference its stable ID.
- Provider vocabulary belongs under `docs/adapters/`, not in core contracts.
- ADRs explain why; current contracts define what.
- Architecture docs constrain implementation structure but must not redefine product semantics.
- Delivery plans may reference contracts but must not invent semantics.
- A scenario is an executable specification and should map directly to an automated test.
- Research/reference documents are informative and should explain what Orc Werk learned from each source rather than importing external vocabulary as a hidden contract.
