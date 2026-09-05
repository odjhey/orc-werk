---
id: EXT-ASSURANCE-DEPTH-V1-SEMANTICS
type: contract
status: draft
authority: normative
version: 1
description: Behavioral semantics for assurance-depth/v1.
---

# `assurance-depth/v1` semantics

**Status: draft proposal** (see `EXT-ASSURANCE-DEPTH-V1`).

## What this extension is for

`assurance-depth/v1` records how deeply the verifier claims it evaluated the candidate. It makes a statically-earned `accepted` distinguishable from a behaviorally-earned one without making evaluation depth part of the generic delivery state machine.

It does not answer what the verdict was, which candidate it binds to, or what was found. Those remain, respectively, the canonical `PORT-ASSURANCE` verdict, the canonical candidate fingerprint (`INV-007`), and `EXT-REVIEW-FINDINGS-V1` — all untouched by this extension (`EXT-003`, `EXT-007`).

## Depth is method, never outcome

The three `depth` values describe *what the verifier did*. They deliberately exclude any outcome-flavored value. The source scheme this extension generalizes from (`docs/reports/2026-09-05-pstack-graded-verdicts.md`) carried "blocked" and "failed" in the same enumeration as its depth grades; Orc Werk already separates those:

| Situation | Canonical verdict | `depth` |
|---|---|---|
| Behavior exercised live, works | `accepted` | `live` |
| Behavior exercised live, broken | `rejected` | `live` |
| Tests run, pass | `accepted` | `test` |
| Tests run, fail | `rejected` | `test` |
| Only inspected/type-checked, looks right | `accepted` | `static` |
| Verifier could not evaluate (environment, tooling, access) | `inconclusive` | omitted, or the deepest method that *did* complete |

A verifier MUST NOT encode a blocked or failed evaluation as a `depth` value, and consumers MUST NOT infer verdict from depth (`INV-009` remains the only rule about which verdicts satisfy acceptance).

## The order exists for policy, not for the kernel

`live > test > static` is a documented total order. Its only purpose is to let extension-aware application policy state and check a floor — for example, "Work whose intent changes runtime behavior requires `test` or better; documentation Work is satisfied by `static`." Such a floor is a policy parameter of the consuming workflow, declared outside this extension, and what policy does when a recorded depth is below its floor (route to a deeper verifier, escalate, refuse to land) is policy's choice made *after* the canonical observation is recorded.

Generic projection and transitions MUST be identical whether the extension is present, absent, unknown, or changed (`EXT-002`, `EXT-005`, `CONF-EXT-006`). An `accepted` with `depth: static` is, to the kernel, exactly `accepted`.

## A verifier-attested observation, never kernel truth

The payload is the verifier's claim. The kernel MUST NOT inspect repository, provider, or runtime state to re-derive, validate, or grade it, and replay preserves the claim unchanged. Tooling MAY help a verifier compose the payload (for example an `orc record --depth` flag, if adopted), but the recorded value remains the seat's attestation.

Depth is not independence. A `live` claim from a seat that also shipped the candidate is still self-assurance; seat discipline stays with `PLAYBOOK-AGENT-CLI`, and `EXT-EXECUTOR-IDENTITY-V1` stays the place seat identity is recorded.

## Candidate-bound like all assurance evidence

Depth describes evidence about one exact candidate fingerprint (`INV-007`). If the candidate changes, the prior depth is historical evidence about the old candidate and MUST NOT be relabeled as describing the new one (`INV-008`, `INV-010`). This is already how the canonical verdict behaves; the extension adds nothing to freshness and takes nothing away.

## Inherited settlements preserve the original observation

When `SCN-009` verdict inheritance applies, the later candidate re-observation cites the original `FACT-ASSURE-SETTLED`; no second assurance Fact is created. The inherited settlement therefore carries the original Fact's `assurance-depth/v1` unchanged. The kernel MUST NOT re-derive or upgrade a depth at inheritance time.

## Missing depth is valid

The extension is optional. Absence does not invalidate an assurance settlement, does not default to `static`, and MUST NOT be fabricated by any consumer. Verify seats SHOULD record it so operators can see the depth distribution across a portfolio, but that practice does not make the extension a core requirement.

## Canonical assurance remains canonical

This payload cannot override the canonical verdict or candidate fingerprint (`EXT-003`). It is never the sole carrier of a canonical verdict, fingerprint, evidence binding, or other information required by `PORT-ASSURANCE` (`EXT-007`). Unknown-extension consumers may ignore it with no canonical behavior change, while lossless transports preserve it unchanged (`EXT-005`, `CONF-EXT-003`).
