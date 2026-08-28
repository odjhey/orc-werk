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
| `FACT-EXEC-SETTLED` | ExecutionSettled | execution_id, work_id, outcome |
| `FACT-CANDIDATE-OBSERVED` | CandidateObserved | candidate_id, fingerprint, execution_id |
| `FACT-ASSURE-STARTED` | AssuranceStarted | assurance_id, candidate_id |
| `FACT-ASSURE-SETTLED` | AssuranceSettled | assurance_id, candidate_fingerprint, verdict, evidence_refs (optional, portable list of externally resolvable references; absent when the observation carried none - never fabricated) |
| `FACT-WORK-COMPLETED` | WorkCompleted | work_id |
| `FACT-WORK-BLOCKED` | WorkBlocked | work_id, reason |
| `FACT-WORK-CANCELLED` | WorkCancelled | work_id |
