---
id: PROTOCOL-FACTS
type: protocol
status: current
authority: normative
description: Canonical immutable facts.
---

# Facts

Facts are immutable canonical observations about what happened.

| ID | Fact | Required data |
|---|---|---|
| `FACT-INTENT-SUBMITTED` | IntentSubmitted | intent_id, text |
| `FACT-WORK-CREATED` | WorkCreated | work_id, delivery_run_id |
| `FACT-WORK-READY` | WorkReady | work_id |
| `FACT-WORK-CLAIMED` | WorkClaimed | work_id, claim_ref |
| `FACT-EXEC-STARTED` | ExecutionStarted | execution_id, work_id |
| `FACT-EXEC-SETTLED` | ExecutionSettled | execution_id, work_id, outcome, artifact_refs (optional, portable list of externally resolvable references; absent when the observation carried none - never fabricated) |
| `FACT-CANDIDATE-OBSERVED` | CandidateObserved | candidate_id, fingerprint, execution_id |
| `FACT-ASSURE-STARTED` | AssuranceStarted | assurance_id, candidate_id |
| `FACT-ASSURE-SETTLED` | AssuranceSettled | assurance_id, candidate_fingerprint, verdict, evidence_refs (optional, portable list of externally resolvable references; absent when the observation carried none - never fabricated) |
| `FACT-WORK-COMPLETED` | WorkCompleted | work_id |
| `FACT-WORK-BLOCKED` | WorkBlocked | work_id, reason |
| `FACT-ATTEMPT-ABANDONED` | AttemptAbandoned | work_id, reason |
| `FACT-WORK-CANCELLED` | WorkCancelled | work_id, reason |

`FACT-ATTEMPT-ABANDONED` (`TASK-M3B-001`, issues #76/#95) records that the operator's `DEC-ABANDON-ATTEMPT` (`PROTOCOL-DECISIONS`) consumed an unresolved candidate-observation conflict or an unsettleable Assurance for the current attempt (`STATE-DELIVERY` mechanical fact sequencing item 9). `reason` is free-form, mirroring `FACT-WORK-BLOCKED`'s shape; the operator's who/why lives on the paired `DEC-ABANDON-ATTEMPT`'s `attribution`/`data` (`INV-011`/`INV-012`), not on this Fact. It is never a verdict: no `FACT-ASSURE-SETTLED` accompanies it (`INV-003`, `INV-009`).

`FACT-WORK-CANCELLED` records operator-driven terminal closure of a Work without acceptance (`STATE-DELIVERY` mechanical fact sequencing item 10). It is paired with `DEC-CANCEL` (`PROTOCOL-DECISIONS`) and is legal from any non-terminal state (`READY`, `EXECUTING`, or `ASSURING`), transitioning and confirming `CANCELLED` in one journal-only step. `reason` is free-form; the operator's who/why lives on the paired Decision's `attribution`/`data` (`INV-011`/`INV-012`). Cancellation is never a verdict and fabricates no `FACT-ASSURE-SETTLED` (`INV-003`, `INV-009`).

**Inherited-settlement basis shape** (`TASK-M3B-001`, `STATE-DELIVERY` mechanical fact sequencing item 8): no new Fact records a re-observed candidate's inherited verdict — no second `FACT-ASSURE-SETTLED` is ever journaled for the same `assurance_id`/candidate. Instead, the *existing* `FACT-ASSURE-SETTLED` Fact from the candidate's original attempt is cited as the `basis` (`INV-012`) of whichever ordinary `DEC-ACCEPT`/`DEC-RETRY`/`DEC-BLOCK` the re-observation resolves to. A basis fact whose own attempt differs from the Decision's current attempt is exactly how an inherited settlement is recognized when reading the journal; this is not a distinct wire shape, only a distinguishing property of an otherwise-ordinary `basis` entry.
