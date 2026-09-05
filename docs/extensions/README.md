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
- `EXT-GIT-CANDIDATE-IDENTIFICATION-V1` — Git adapter-local candidate identification provenance under `git-candidate-identification/v1`
- `EXT-EXECUTOR-IDENTITY-V1` — ship- and verify-seat executor provenance under `executor-identity/v1`

## Proposed extensions (draft)

Not yet binding and not yet emitted by any orc code path; listed so the identifier is reserved and reviewable.

- `EXT-ASSURANCE-DEPTH-V1` — verifier-attested evaluation depth (`live | test | static`) under `assurance-depth/v1`. Provenance: `docs/reports/2026-09-05-pstack-graded-verdicts.md`.

## Superseded extensions

Retained history only — do not build against these; see each for its replacement.

- `EXT-CREW-REPORT-V1` — append-only, claim-only handoff report per execution turn under `crew-report/v1`. Removed (operator ruling, issue #100 part 2, "reference-first narrative doctrine"): narrative content is provider-owned and the ledger journals a resolvable reference instead (`execution-session/v1`, `evidence_refs`, `orc refs`). See [`docs/extensions/crew-report/README.md`](crew-report/README.md).
- `EXT-ACP-SETTLEMENT-V1` — ACP adapter-local settlement diagnostics under `acp-settlement/v1`. Removed (operator ruling ADR-0005, issue #214): the `acp` `ExecutionPort` adapter it diagnosed is removed in 0.5.0, pre-1.0, no backward compatibility (last release carrying it: v0.4.1). See [`docs/extensions/acp-settlement/README.md`](acp-settlement/README.md) and `docs/decisions/ADR-0005-push-recording-not-pull-observation.md`.

## Rules

- Core contracts remain authoritative over extension payloads.
- Extension identifiers are stable and versioned.
- Extension payloads are portable JSON-compatible data.
- Unknown extensions do not change canonical orchestration behavior.
- Policy may explicitly require a known extension capability.
