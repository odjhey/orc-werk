---
id: EXTENSION-INDEX
type: index
status: current
authority: normative
description: Registry and rules for optional Orc Werk extensions.
---

# Extensions

Extensions carry specialized semantics that are useful to particular providers or workflows but are not required by the generic Orc Werk delivery state machine.

All extensions MUST satisfy `CONTRACT-EXTENSIONS`.

## Registered extensions

- `EXT-REVIEW-FINDINGS-V1` — structured code-review findings under `review-findings/v1`
- `EXT-EXECUTION-SESSION-V1` — durable provider session/resume provenance under `execution-session/v1`
- `EXT-ASSURANCE-CONTEXT-V1` — audit base/provenance under `assurance-context/v1`
- `EXT-ACP-SETTLEMENT-V1` — ACP adapter-local settlement diagnostics under `acp-settlement/v1`
- `EXT-GIT-CANDIDATE-IDENTIFICATION-V1` — Git adapter-local candidate identification provenance under `git-candidate-identification/v1`

## Superseded extensions

Retained history only — do not build against these; see each for its replacement.

- `EXT-CREW-REPORT-V1` — append-only, claim-only handoff report per execution turn under `crew-report/v1`. Removed (operator ruling, issue #100 part 2, "reference-first narrative doctrine"): narrative content is provider-owned and the ledger journals a resolvable reference instead (`execution-session/v1`, `evidence_refs`, `orc refs`). See [`docs/extensions/crew-report/README.md`](crew-report/README.md).

## Rules

- Core contracts remain authoritative over extension payloads.
- Extension identifiers are stable and versioned.
- Extension payloads are portable JSON-compatible data.
- Unknown extensions do not change canonical orchestration behavior.
- Policy may explicitly require a known extension capability.
